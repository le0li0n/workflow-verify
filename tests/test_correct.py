"""Tests for the self-correction protocol."""

import asyncio
import json
from pathlib import Path
from typing import Any

from workflow_verify.ast.models import Workflow
from workflow_verify.correct.loop import (
    CorrectionRequest,
    format_correction_request,
    generate_and_verify,
)
from workflow_verify.verify.engine import verify

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Workflow:
    data = json.loads((FIXTURES / name).read_text())
    return Workflow(**data)


def load_fixture_dict(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# --- Mock LLM client ---


class MockLLMClient:
    """Mock LLM client that returns pre-configured responses in sequence."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._call_count = 0
        self.prompts: list[str] = []

    async def generate_workflow(
        self,
        prompt: str,
        schema: dict,
    ) -> dict[str, Any]:
        self.prompts.append(prompt)
        if self._call_count >= len(self._responses):
            raise RuntimeError("MockLLMClient exhausted all responses")
        response = self._responses[self._call_count]
        self._call_count += 1
        return response


class ErrorMockLLMClient:
    """Mock LLM client that raises on first call, then returns valid response."""

    def __init__(self, error: Exception, fallback: dict[str, Any]) -> None:
        self._error = error
        self._fallback = fallback
        self._call_count = 0
        self.prompts: list[str] = []

    async def generate_workflow(
        self,
        prompt: str,
        schema: dict,
    ) -> dict[str, Any]:
        self.prompts.append(prompt)
        self._call_count += 1
        if self._call_count == 1:
            raise self._error
        return self._fallback


# --- format_correction_request tests ---


class TestFormatCorrectionRequest:
    """Test that correction requests are clear and actionable."""

    def test_type_mismatch_produces_clear_instruction(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        correction = format_correction_request("Build a pipeline", wf, result)

        assert isinstance(correction, CorrectionRequest)
        assert correction.original_prompt == "Build a pipeline"
        assert len(correction.errors) > 0
        assert "TYPE_FLOW_ERROR" in correction.instruction
        assert "phone_number" in correction.instruction

    def test_guard_bad_field_produces_clear_instruction(self):
        wf = load_fixture("invalid_guard_bad_field.json")
        result = verify(wf)
        correction = format_correction_request("Score leads", wf, result)

        assert "GUARD_ERROR" in correction.instruction
        assert "score" in correction.instruction
        assert "filter_leads" in correction.instruction

    def test_missing_schema_produces_clear_instruction(self):
        wf = load_fixture("invalid_missing_schema_ref.json")
        result = verify(wf)
        correction = format_correction_request("Process data", wf, result)

        assert "SCHEMA_ERROR" in correction.instruction
        assert "ProcessedData" in correction.instruction

    def test_duplicate_schema_produces_clear_instruction(self):
        wf = load_fixture("invalid_duplicate_schema.json")
        result = verify(wf)
        correction = format_correction_request("Handle users", wf, result)

        assert "SCHEMA_ERROR" in correction.instruction
        assert "UserData" in correction.instruction
        assert "Duplicate" in correction.instruction

    def test_suggestions_are_populated(self):
        wf = load_fixture("invalid_guard_bad_field.json")
        result = verify(wf)
        correction = format_correction_request("Score leads", wf, result)

        assert len(correction.suggestions) > 0
        assert any("email" in s or "name" in s for s in correction.suggestions)

    def test_instruction_ends_with_regenerate_prompt(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        correction = format_correction_request("Build a pipeline", wf, result)

        assert "regenerate" in correction.instruction.lower()

    def test_warnings_included_in_instruction(self):
        """Warnings should be included as additional context."""
        wf = load_fixture("valid_with_warnings.json")
        result = verify(wf)
        # This workflow passes but has warnings — format_correction_request
        # should still work (even if not typically called for passing workflows)
        # Force it by manually adding an error
        from workflow_verify.verify.results import CheckResult

        fake_result = result.model_copy(
            update={
                "passed": False,
                "errors": [
                    CheckResult(
                        passed=False,
                        check_type="schema",
                        step=None,
                        message="Fake error for testing",
                        severity="error",
                        suggestion="Fix the fake error",
                    )
                ],
            }
        )
        correction = format_correction_request("Test", wf, fake_result)
        assert "warning" in correction.instruction.lower()

    def test_error_count_in_instruction(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        correction = format_correction_request("Build", wf, result)
        error_count = len(result.errors)
        assert f"{error_count} error" in correction.instruction

    def test_original_ast_preserved(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        correction = format_correction_request("Build", wf, result)
        assert correction.original_ast == wf


# --- generate_and_verify loop tests ---


class TestGenerateAndVerifyLoop:
    """Test the full correction loop with mocked LLM clients."""

    def test_converges_on_first_attempt(self):
        """Valid workflow on first try — no correction needed."""
        valid_ast = load_fixture_dict("valid_crm_pipeline.json")
        client = MockLLMClient([valid_ast])

        result = asyncio.run(
            generate_and_verify(
                "Build a CRM pipeline",
                client=client,
                max_attempts=3,
            )
        )

        assert result.converged
        assert result.workflow is not None
        assert result.verification is not None
        assert result.verification.passed
        assert len(result.attempts) == 1
        assert result.attempts[0].attempt_number == 1
        assert result.attempts[0].correction is None

    def test_converges_on_second_attempt(self):
        """Invalid first try, valid second try."""
        invalid_ast = load_fixture_dict("invalid_type_mismatch.json")
        valid_ast = load_fixture_dict("valid_crm_pipeline.json")
        client = MockLLMClient([invalid_ast, valid_ast])

        result = asyncio.run(
            generate_and_verify(
                "Build a pipeline",
                client=client,
                max_attempts=3,
            )
        )

        assert result.converged
        assert len(result.attempts) == 2
        # First attempt should have a correction request
        assert result.attempts[0].correction is not None
        assert not result.attempts[0].verification.passed
        # Second attempt should pass
        assert result.attempts[1].correction is None
        assert result.attempts[1].verification.passed

    def test_max_attempts_exceeded(self):
        """All attempts produce invalid workflows — should not converge."""
        invalid_ast = load_fixture_dict("invalid_type_mismatch.json")
        client = MockLLMClient([invalid_ast, invalid_ast, invalid_ast])

        result = asyncio.run(
            generate_and_verify(
                "Build a pipeline",
                client=client,
                max_attempts=3,
            )
        )

        assert not result.converged
        assert len(result.attempts) == 3
        assert result.workflow is not None  # Last attempt's workflow
        assert result.verification is not None
        assert not result.verification.passed
        assert result.transpiled is None

    def test_correction_prompt_sent_to_llm(self):
        """After failure, the LLM should receive correction context."""
        invalid_ast = load_fixture_dict("invalid_type_mismatch.json")
        valid_ast = load_fixture_dict("valid_crm_pipeline.json")
        client = MockLLMClient([invalid_ast, valid_ast])

        _result = asyncio.run(
            generate_and_verify(
                "Build a pipeline",
                client=client,
                max_attempts=3,
            )
        )

        # Second prompt should contain error context
        assert len(client.prompts) == 2
        second_prompt = client.prompts[1]
        assert "error" in second_prompt.lower()
        assert "previous attempt" in second_prompt.lower() or "previous" in second_prompt.lower()

    def test_parse_error_handled_gracefully(self):
        """If LLM returns unparseable data, loop should continue."""
        bad_response = {"name": "test"}  # Missing required fields
        valid_ast = load_fixture_dict("valid_crm_pipeline.json")
        client = MockLLMClient([bad_response, valid_ast])

        result = asyncio.run(
            generate_and_verify(
                "Build a pipeline",
                client=client,
                max_attempts=3,
            )
        )

        assert result.converged
        assert len(result.attempts) == 2
        assert result.attempts[0].error_message is not None
        assert result.attempts[0].workflow is None

    def test_with_transpile_target(self):
        """When target is specified, result should include transpiled code."""
        valid_ast = load_fixture_dict("valid_crm_pipeline.json")
        client = MockLLMClient([valid_ast])

        result = asyncio.run(
            generate_and_verify(
                "Build a CRM pipeline",
                client=client,
                max_attempts=3,
                target="python",
            )
        )

        assert result.converged
        assert result.transpiled is not None
        assert result.transpiled.target.value == "python"
        assert "class RawLead" in result.transpiled.code

    def test_max_attempts_one(self):
        """Single attempt — should fail immediately if invalid."""
        invalid_ast = load_fixture_dict("invalid_type_mismatch.json")
        client = MockLLMClient([invalid_ast])

        result = asyncio.run(
            generate_and_verify(
                "Build a pipeline",
                client=client,
                max_attempts=1,
            )
        )

        assert not result.converged
        assert len(result.attempts) == 1

    def test_attempt_history_complete(self):
        """Every attempt should be recorded with full context."""
        responses = [
            load_fixture_dict("invalid_guard_bad_field.json"),
            load_fixture_dict("invalid_type_mismatch.json"),
            load_fixture_dict("valid_crm_pipeline.json"),
        ]
        client = MockLLMClient(responses)

        result = asyncio.run(
            generate_and_verify(
                "Build a pipeline",
                client=client,
                max_attempts=5,
            )
        )

        assert result.converged
        assert len(result.attempts) == 3

        # First two should have corrections
        assert result.attempts[0].correction is not None
        assert result.attempts[1].correction is not None
        # Third should pass
        assert result.attempts[2].correction is None
        assert result.attempts[2].verification.passed

    def test_schemas_context_passed_to_llm(self):
        """Pre-defined schemas should be included in the initial prompt."""
        from workflow_verify.ast.models import FieldDef, Schema
        from workflow_verify.ast.types import WFType

        schemas = [
            Schema(
                name="MyLead",
                fields=[FieldDef(name="email", type=WFType.EMAIL)],
                description="A lead record",
            )
        ]
        valid_ast = load_fixture_dict("valid_crm_pipeline.json")
        client = MockLLMClient([valid_ast])

        _result = asyncio.run(
            generate_and_verify(
                "Build a pipeline",
                schemas=schemas,
                client=client,
                max_attempts=1,
            )
        )

        # First prompt should include schema context
        assert "MyLead" in client.prompts[0]
        assert "email" in client.prompts[0]


# --- Edge case tests ---


class TestCorrectionEdgeCases:
    """Test edge cases in the correction protocol."""

    def test_multiple_error_types_in_single_correction(self):
        """A workflow with both schema and guard errors."""
        wf = load_fixture("invalid_guard_bad_field.json")
        result = verify(wf)
        correction = format_correction_request("Test", wf, result)

        # Should have guard error at minimum
        assert "GUARD_ERROR" in correction.instruction

    def test_empty_errors_still_formats(self):
        """Edge case: format_correction_request with empty errors list."""
        wf = load_fixture("valid_crm_pipeline.json")
        _result = verify(wf)
        # Force empty errors
        from workflow_verify.verify.results import VerificationResult

        empty_result = VerificationResult(
            passed=False,
            checks=[],
            effects_manifest=[],
            trace="",
            errors=[],
            warnings=[],
        )
        correction = format_correction_request("Test", wf, empty_result)
        assert "0 errors" in correction.instruction

    def test_correction_request_serializable(self):
        """CorrectionRequest should be JSON serializable."""
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        correction = format_correction_request("Build", wf, result)

        json_str = correction.model_dump_json()
        parsed = json.loads(json_str)
        assert "instruction" in parsed
        assert "errors" in parsed

    def test_correction_result_serializable(self):
        """CorrectionResult should be JSON serializable."""
        valid_ast = load_fixture_dict("valid_crm_pipeline.json")
        client = MockLLMClient([valid_ast])

        result = asyncio.run(generate_and_verify("Test", client=client, max_attempts=1))

        json_str = result.model_dump_json()
        parsed = json.loads(json_str)
        assert "converged" in parsed
        assert "attempts" in parsed
