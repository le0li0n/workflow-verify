"""Tests for the public API surface — top-level imports and convenience functions."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# --- Import tests ---


class TestTopLevelImports:
    """Verify all symbols are accessible from the top-level package."""

    def test_ast_models(self):
        from workflow_verify import Effect, FieldDef, Guard, Schema, Step, Workflow
        assert all(cls is not None for cls in [Effect, FieldDef, Guard, Schema, Step, Workflow])

    def test_ast_types(self):
        from workflow_verify import AnyWFType, ListType, OptionalType, RecordField, RecordType, WFType, is_compatible
        assert WFType.TEXT is not None
        assert is_compatible is not None

    def test_ast_schema_utils(self):
        from workflow_verify import get_workflow_json_schema, get_workflow_tool_definition
        schema = get_workflow_json_schema()
        assert isinstance(schema, dict)
        tool = get_workflow_tool_definition()
        assert "name" in tool

    def test_verification(self):
        from workflow_verify import CheckResult, VerificationResult, verify
        assert all(cls is not None for cls in [CheckResult, VerificationResult, verify])

    def test_transpilation(self):
        from workflow_verify import TranspileResult, TranspileTarget, transpile
        assert TranspileTarget.PYTHON is not None

    def test_correction(self):
        from workflow_verify import (
            Attempt,
            CorrectionRequest,
            CorrectionResult,
            LLMClient,
            format_correction_request,
            generate_and_verify,
        )
        assert all(cls is not None for cls in [
            Attempt, CorrectionRequest, CorrectionResult,
            LLMClient, format_correction_request, generate_and_verify,
        ])

    def test_registry(self):
        from workflow_verify import (
            SchemaLoadError,
            list_categories,
            list_schemas,
            load_schema,
            resolve_schema,
            search_schemas,
        )
        assert all(fn is not None for fn in [
            SchemaLoadError, list_categories, list_schemas,
            load_schema, resolve_schema, search_schemas,
        ])

    def test_trace(self):
        from workflow_verify import format_trace
        assert format_trace is not None

    def test_convenience_functions(self):
        from workflow_verify import effects, run, run_sync
        assert all(fn is not None for fn in [effects, run, run_sync])


class TestAllCompleteness:
    """Verify __all__ contains the expected symbols."""

    EXPECTED = {
        # AST models
        "Effect", "FieldDef", "Guard", "Schema", "Step", "Workflow",
        # AST types
        "AnyWFType", "ListType", "OptionalType", "RecordField", "RecordType",
        "WFType", "is_compatible",
        # AST schema utilities
        "get_workflow_json_schema", "get_workflow_tool_definition",
        # Verification
        "CheckResult", "VerificationResult", "verify",
        # Transpilation
        "TranspileResult", "TranspileTarget", "transpile",
        # Self-correction
        "Attempt", "CorrectionRequest", "CorrectionResult",
        "LLMClient", "format_correction_request", "generate_and_verify",
        # Registry
        "SchemaLoadError", "list_categories", "list_schemas",
        "load_schema", "resolve_schema", "search_schemas",
        # Trace
        "format_trace",
        # Convenience
        "effects", "run", "run_sync",
    }

    def test_all_contains_expected(self):
        import workflow_verify
        actual = set(workflow_verify.__all__)
        missing = self.EXPECTED - actual
        assert not missing, f"Missing from __all__: {missing}"

    def test_no_unexpected_in_all(self):
        import workflow_verify
        actual = set(workflow_verify.__all__)
        extra = actual - self.EXPECTED
        assert not extra, f"Unexpected in __all__: {extra}"


# --- effects() tests ---


def _load_workflow(name: str):
    from workflow_verify import Workflow
    data = json.loads((FIXTURES / name).read_text())
    return Workflow(**data)


class TestEffects:
    """Test the effects() convenience function."""

    def test_valid_workflow_returns_effects(self):
        from workflow_verify import effects
        wf = _load_workflow("valid_crm_pipeline.json")
        result = effects(wf)
        assert isinstance(result, list)
        assert len(result) == 3  # read:sf, call:clearbit, write:sf

    def test_valid_workflow_with_warnings_non_strict(self):
        from workflow_verify import effects
        wf = _load_workflow("valid_with_warnings.json")
        result = effects(wf, strict=False)
        assert isinstance(result, list)

    def test_invalid_workflow_raises(self):
        from workflow_verify import effects
        wf = _load_workflow("invalid_type_mismatch.json")
        with pytest.raises(ValueError, match="Workflow verification failed"):
            effects(wf)

    def test_empty_effects(self):
        """A workflow with no side effects returns an empty list."""
        from workflow_verify import Schema, FieldDef, Workflow, effects
        # Minimal valid workflow — one schema, no steps, no effects
        wf = Workflow(
            name="empty",
            description="test",
            schemas=[Schema(name="In", fields=[FieldDef(name="x", type="Text")])],
            steps=[],
            input_schema="In",
            output_schema="In",
        )
        result = effects(wf)
        assert result == []


# --- run() / run_sync() tests ---


class _MockLLMClient:
    """Mock LLM client that returns a pre-built workflow."""

    def __init__(self, fixture_name: str = "valid_crm_pipeline.json"):
        self._data = json.loads((FIXTURES / fixture_name).read_text())

    async def generate_workflow(self, prompt: str, schema: dict) -> dict[str, Any]:
        return self._data


class TestRun:
    """Test the run() convenience function."""

    @pytest.mark.asyncio
    async def test_run_python(self):
        from workflow_verify import run
        code = await run("test prompt", target="python", client=_MockLLMClient())
        assert isinstance(code, str)
        assert len(code) > 0

    @pytest.mark.asyncio
    async def test_run_typescript(self):
        from workflow_verify import run
        code = await run("test prompt", target="typescript", client=_MockLLMClient())
        assert isinstance(code, str)
        assert "export" in code or "interface" in code or "function" in code or "const" in code

    @pytest.mark.asyncio
    async def test_run_temporal(self):
        from workflow_verify import run
        code = await run("test prompt", target="temporal", client=_MockLLMClient())
        assert isinstance(code, str)
        assert len(code) > 0

    @pytest.mark.asyncio
    async def test_run_convergence_failure(self):
        """run() raises RuntimeError when correction loop fails to converge."""
        from workflow_verify import run

        client = _MockLLMClient("invalid_type_mismatch.json")
        with pytest.raises(RuntimeError, match="Failed to generate a valid workflow"):
            await run("test prompt", client=client, max_attempts=1)


class TestRunSync:
    """Test the run_sync() convenience function."""

    def test_run_sync_returns_code(self):
        from workflow_verify import run_sync
        code = run_sync("test prompt", target="python", client=_MockLLMClient())
        assert isinstance(code, str)
        assert len(code) > 0
