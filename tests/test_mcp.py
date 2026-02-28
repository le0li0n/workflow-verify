"""Tests for the MCP server tools.

Tests the tool functions directly (not via MCP transport) to verify
they produce correct JSON output for valid/invalid inputs.
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture_json(name: str) -> str:
    return (FIXTURES / name).read_text()


# --- verify_workflow tests ---


class TestVerifyWorkflow:
    def test_valid_workflow_passes(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(verify_workflow(_load_fixture_json("valid_crm_pipeline.json")))
        assert result["passed"] is True
        assert len(result["errors"]) == 0
        assert len(result["effects"]) == 3
        assert "trace" in result
        assert len(result["trace"]) > 0

    def test_invalid_workflow_fails(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(verify_workflow(_load_fixture_json("invalid_type_mismatch.json")))
        assert result["passed"] is False
        assert len(result["errors"]) > 0
        assert result["errors"][0]["message"]

    def test_invalid_json_returns_error(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(verify_workflow("not valid json {{{"))
        assert "error" in result
        assert "Invalid JSON" in result["error"]

    def test_invalid_structure_returns_error(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(verify_workflow('{"not": "a workflow"}'))
        assert "error" in result
        assert "Invalid workflow" in result["error"]

    def test_non_strict_mode(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(
            verify_workflow(_load_fixture_json("valid_with_warnings.json"), strict=False)
        )
        assert result["passed"] is True
        assert len(result["warnings"]) > 0

    def test_with_transpile_target(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(
            verify_workflow(_load_fixture_json("valid_crm_pipeline.json"), target="python")
        )
        assert result["passed"] is True
        assert "transpiled" in result
        assert result["transpiled"]["target"] == "python"
        assert len(result["transpiled"]["code"]) > 0
        assert result["transpiled"]["filename"].endswith(".py")

    def test_with_typescript_target(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(
            verify_workflow(_load_fixture_json("valid_crm_pipeline.json"), target="typescript")
        )
        assert result["transpiled"]["target"] == "typescript"

    def test_with_temporal_target(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(
            verify_workflow(_load_fixture_json("valid_crm_pipeline.json"), target="temporal")
        )
        assert result["transpiled"]["target"] == "temporal"

    def test_transpile_skipped_on_failure(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(
            verify_workflow(
                _load_fixture_json("invalid_type_mismatch.json"),
                target="python",
            )
        )
        assert result["passed"] is False
        assert "transpiled" not in result

    def test_effects_structure(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(verify_workflow(_load_fixture_json("valid_crm_pipeline.json")))
        for effect in result["effects"]:
            assert "kind" in effect
            assert "target" in effect
            assert "description" in effect

    def test_error_structure(self):
        from workflow_verify.mcp_server import verify_workflow

        result = json.loads(verify_workflow(_load_fixture_json("invalid_type_mismatch.json")))
        for error in result["errors"]:
            assert "message" in error
            assert "step" in error
            assert "suggestion" in error


# --- generate_verified_workflow tests ---


class TestGenerateVerifiedWorkflow:
    @pytest.mark.asyncio
    async def test_with_mock_client(self):
        """Test the full generation flow with a mock LLM client."""
        import json as json_mod
        from typing import Any
        from unittest.mock import patch

        from workflow_verify.mcp_server import generate_verified_workflow

        valid_data = json_mod.loads(_load_fixture_json("valid_crm_pipeline.json"))

        class MockClient:
            async def generate_workflow(self, prompt: str, schema: dict) -> dict[str, Any]:
                return valid_data

        # Patch _make_client to return our mock
        with patch("workflow_verify.correct.loop._make_client", return_value=MockClient()):
            result_str = await generate_verified_workflow(
                prompt="Build a CRM pipeline",
                target="python",
            )

        result = json_mod.loads(result_str)
        assert result["converged"] is True
        assert result["attempts"] == 1
        assert "workflow" in result
        assert "verification" in result
        assert result["verification"]["passed"] is True
        assert "transpiled" in result
        assert len(result["transpiled"]["code"]) > 0

    @pytest.mark.asyncio
    async def test_missing_llm_package(self):
        """Test graceful handling when LLM package is not installed."""
        from workflow_verify.mcp_server import generate_verified_workflow

        # anthropic/openai likely not installed in test env
        result = json.loads(
            await generate_verified_workflow(
                prompt="test",
                llm="anthropic",
            )
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_schemas_json(self):
        from workflow_verify.mcp_server import generate_verified_workflow

        result = json.loads(
            await generate_verified_workflow(
                prompt="test",
                schemas_json="not valid json",
            )
        )
        assert "error" in result
        assert "Invalid schemas_json" in result["error"]

    @pytest.mark.asyncio
    async def test_with_schemas(self):
        """Test passing pre-defined schemas."""
        import json as json_mod
        from typing import Any
        from unittest.mock import patch

        from workflow_verify.mcp_server import generate_verified_workflow

        valid_data = json_mod.loads(_load_fixture_json("valid_crm_pipeline.json"))

        class MockClient:
            async def generate_workflow(self, prompt: str, schema: dict) -> dict[str, Any]:
                return valid_data

        schemas = json_mod.dumps(
            [
                {
                    "name": "TestSchema",
                    "fields": [{"name": "id", "type": "Text", "description": "ID"}],
                }
            ]
        )

        with patch("workflow_verify.correct.loop._make_client", return_value=MockClient()):
            result_str = await generate_verified_workflow(
                prompt="Build something",
                schemas_json=schemas,
            )

        result = json_mod.loads(result_str)
        assert result["converged"] is True

    @pytest.mark.asyncio
    async def test_attempt_details_included(self):
        """Test that attempt details are included in the response."""
        import json as json_mod
        from typing import Any
        from unittest.mock import patch

        from workflow_verify.mcp_server import generate_verified_workflow

        valid_data = json_mod.loads(_load_fixture_json("valid_crm_pipeline.json"))

        class MockClient:
            async def generate_workflow(self, prompt: str, schema: dict) -> dict[str, Any]:
                return valid_data

        with patch("workflow_verify.correct.loop._make_client", return_value=MockClient()):
            result_str = await generate_verified_workflow(prompt="test")

        result = json_mod.loads(result_str)
        assert "attempt_details" in result
        assert len(result["attempt_details"]) == 1
        assert result["attempt_details"][0]["attempt"] == 1
        assert result["attempt_details"][0]["passed"] is True
