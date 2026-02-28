"""Tests for the transpiler suite."""

import ast
import json
from pathlib import Path

import pytest

from workflow_verify.ast.models import Workflow
from workflow_verify.transpile import TranspileTarget, transpile

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Workflow:
    data = json.loads((FIXTURES / name).read_text())
    return Workflow(**data)


# --- Verification gate ---


class TestVerificationGate:
    """transpile() must reject unverified/failing workflows."""

    def test_rejects_invalid_workflow(self):
        wf = load_fixture("invalid_type_mismatch.json")
        with pytest.raises(ValueError, match="failed verification"):
            transpile(wf, TranspileTarget.TYPESCRIPT)

    def test_rejects_missing_schema_ref(self):
        wf = load_fixture("invalid_missing_schema_ref.json")
        with pytest.raises(ValueError, match="failed verification"):
            transpile(wf, TranspileTarget.PYTHON)

    def test_rejects_duplicate_schema(self):
        wf = load_fixture("invalid_duplicate_schema.json")
        with pytest.raises(ValueError, match="failed verification"):
            transpile(wf, TranspileTarget.TEMPORAL)

    def test_rejects_guard_bad_field(self):
        wf = load_fixture("invalid_guard_bad_field.json")
        with pytest.raises(ValueError, match="failed verification"):
            transpile(wf, TranspileTarget.TYPESCRIPT)


# --- TypeScript transpiler ---


class TestTypeScriptTranspiler:
    """Test TypeScript code generation."""

    def test_produces_code(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert result.target == TranspileTarget.TYPESCRIPT
        assert len(result.code) > 0

    def test_has_zod_import(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert 'import { z } from "zod"' in result.code

    def test_has_zod_schemas(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "z.object({" in result.code
        assert "z.string().email()" in result.code

    def test_has_step_functions(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "async function fetchLeads" in result.code
        assert "async function enrichLeads" in result.code
        assert "async function scoreLeads" in result.code
        assert "async function pushQualified" in result.code

    def test_has_run_workflow(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "async function runWorkflow" in result.code

    def test_has_effect_comments(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "READ:salesforce" in result.code
        assert "CALL:clearbit" in result.code
        assert "WRITE:salesforce" in result.code

    def test_has_guard_checks(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "score >= 70" in result.code

    def test_has_todo_placeholders(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "TODO" in result.code

    def test_filename_is_ts(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert result.filename.endswith(".ts")

    def test_dependencies_include_zod(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "zod" in result.dependencies

    def test_export_statement(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "export { runWorkflow }" in result.code

    def test_complex_pipeline(self):
        wf = load_fixture("valid_complex_pipeline.json")
        result = transpile(wf, TranspileTarget.TYPESCRIPT)
        assert "async function fetchLeads" in result.code
        assert "async function syncToCrm" in result.code
        # Multiple guards
        assert "score >= 50" in result.code


# --- Python transpiler ---


class TestPythonTranspiler:
    """Test Python code generation."""

    def test_produces_valid_python(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        # Syntax check: ast.parse will raise SyntaxError if invalid
        ast.parse(result.code)

    def test_has_pydantic_models(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert "class RawLead(BaseModel):" in result.code
        assert "class EnrichedLead(BaseModel):" in result.code

    def test_has_step_functions(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert "async def fetch_leads" in result.code
        assert "async def enrich_leads" in result.code
        assert "async def score_leads" in result.code
        assert "async def push_qualified" in result.code

    def test_has_run_workflow(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert "async def run_workflow" in result.code

    def test_has_effect_comments(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert "@effect(read" in result.code
        assert "@effect(call" in result.code
        assert "@effect(write" in result.code

    def test_has_guard_checks(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert "score >= 70" in result.code or "input.score >= 70" in result.code

    def test_has_todo_placeholders(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert "TODO" in result.code

    def test_filename_is_py(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert result.filename.endswith(".py")

    def test_dependencies_include_pydantic(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        assert any("pydantic" in d for d in result.dependencies)

    def test_complex_pipeline_valid_python(self):
        wf = load_fixture("valid_complex_pipeline.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        ast.parse(result.code)

    def test_with_warnings_valid_python(self):
        wf = load_fixture("valid_with_warnings.json")
        result = transpile(wf, TranspileTarget.PYTHON)
        ast.parse(result.code)


# --- Temporal transpiler ---


class TestTemporalTranspiler:
    """Test Temporal workflow code generation."""

    def test_produces_valid_python(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        ast.parse(result.code)

    def test_has_activity_decorators(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "@activity.defn" in result.code

    def test_has_workflow_decorator(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "@workflow.defn" in result.code
        assert "@workflow.run" in result.code

    def test_has_activity_functions(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "async def fetch_leads" in result.code
        assert "async def enrich_leads" in result.code

    def test_has_workflow_class(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "CrmLeadPipelineWorkflow" in result.code
        assert "async def run(self" in result.code

    def test_has_execute_activity_calls(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "workflow.execute_activity(" in result.code
        assert "start_to_close_timeout" in result.code

    def test_has_effect_logging(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "activity.logger.info" in result.code
        assert "READ:salesforce" in result.code

    def test_has_guard_checks(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "score >= 70" in result.code or "input.score >= 70" in result.code

    def test_has_temporalio_imports(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "from temporalio import activity, workflow" in result.code

    def test_filename_has_temporal_suffix(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "_temporal.py" in result.filename

    def test_dependencies_include_temporalio(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        assert "temporalio" in result.dependencies

    def test_complex_pipeline_valid_python(self):
        wf = load_fixture("valid_complex_pipeline.json")
        result = transpile(wf, TranspileTarget.TEMPORAL)
        ast.parse(result.code)


# --- Round-trip tests ---


class TestRoundTrip:
    """Test the full pipeline: parse AST -> verify -> transpile -> syntax check."""

    @pytest.mark.parametrize(
        "fixture",
        [
            "valid_crm_pipeline.json",
            "valid_complex_pipeline.json",
            "valid_with_warnings.json",
        ],
    )
    @pytest.mark.parametrize(
        "target",
        [
            TranspileTarget.TYPESCRIPT,
            TranspileTarget.PYTHON,
            TranspileTarget.TEMPORAL,
        ],
    )
    def test_round_trip(self, fixture: str, target: TranspileTarget):
        # Parse
        data = json.loads((FIXTURES / fixture).read_text())
        wf = Workflow(**data)

        # Transpile (includes verify)
        result = transpile(wf, target)

        # Verify output exists
        assert len(result.code) > 100
        assert result.filename
        assert result.dependencies
        assert result.instructions

        # Syntax check for Python targets
        if target in (TranspileTarget.PYTHON, TranspileTarget.TEMPORAL):
            ast.parse(result.code)
