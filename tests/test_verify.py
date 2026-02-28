"""Tests for the verification engine and all checkers."""

import json
from pathlib import Path

import pytest

from workflow_verify.ast.models import Workflow
from workflow_verify.verify.engine import verify

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Workflow:
    data = json.loads((FIXTURES / name).read_text())
    return Workflow(**data)


# --- Valid workflow tests ---


class TestValidWorkflows:
    """Verify that valid workflows pass verification."""

    def test_valid_crm_pipeline(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = verify(wf)
        assert result.passed, f"Expected pass, got errors: {[e.message for e in result.errors]}"
        assert len(result.errors) == 0
        assert len(result.effects_manifest) == 3  # read:sf, call:clearbit, write:sf
        assert result.trace  # Non-empty trace

    def test_valid_complex_pipeline(self):
        wf = load_fixture("valid_complex_pipeline.json")
        result = verify(wf)
        assert result.passed, f"Expected pass, got errors: {[e.message for e in result.errors]}"
        assert len(result.errors) == 0
        assert len(result.effects_manifest) == 5  # read, call, call, write, send
        assert len(result.checks) > 0

    def test_valid_with_warnings(self):
        wf = load_fixture("valid_with_warnings.json")
        result = verify(wf)
        assert result.passed
        assert len(result.errors) == 0
        assert len(result.warnings) > 0  # Should have warnings

    def test_valid_with_warnings_has_undeclared_effect_warning(self):
        """Step 1 mentions 'API' and 'Clearbit' but declares no effects."""
        wf = load_fixture("valid_with_warnings.json")
        result = verify(wf)
        warning_messages = [w.message for w in result.warnings]
        has_effect_warning = any(
            "enrich_contact" in msg and ("effect" in msg.lower() or "clearbit" in msg.lower())
            for msg in warning_messages
        )
        assert has_effect_warning, f"Expected undeclared effect warning for enrich_contact. Warnings: {warning_messages}"

    def test_valid_with_warnings_has_unguarded_write_warning(self):
        """Step 2 has a write effect but no guard."""
        wf = load_fixture("valid_with_warnings.json")
        result = verify(wf)
        warning_messages = [w.message for w in result.warnings]
        has_guard_warning = any(
            "save_to_hubspot" in msg and ("guard" in msg.lower() or "write" in msg.lower())
            for msg in warning_messages
        )
        assert has_guard_warning, f"Expected unguarded write warning. Warnings: {warning_messages}"


# --- Invalid workflow tests ---


class TestInvalidTypeMismatch:
    """Test type mismatch detection between steps."""

    def test_catches_type_mismatch(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        assert not result.passed
        assert len(result.errors) > 0

    def test_error_identifies_missing_field(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        type_errors = [e for e in result.errors if e.check_type == "type_flow"]
        assert len(type_errors) > 0
        # Should mention the missing phone_number field
        assert any("phone_number" in e.message for e in type_errors), (
            f"Expected error about 'phone_number'. Errors: {[e.message for e in type_errors]}"
        )

    def test_error_identifies_step(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        type_errors = [e for e in result.errors if e.check_type == "type_flow"]
        assert any(e.step == "send_sms" for e in type_errors)


class TestInvalidMissingSchemaRef:
    """Test missing schema reference detection."""

    def test_catches_missing_schema(self):
        wf = load_fixture("invalid_missing_schema_ref.json")
        result = verify(wf)
        assert not result.passed

    def test_error_identifies_missing_schema_name(self):
        wf = load_fixture("invalid_missing_schema_ref.json")
        result = verify(wf)
        schema_errors = [e for e in result.errors if e.check_type == "schema"]
        assert any("ProcessedData" in e.message for e in schema_errors), (
            f"Expected error about 'ProcessedData'. Errors: {[e.message for e in schema_errors]}"
        )


class TestInvalidDuplicateSchema:
    """Test duplicate schema name detection."""

    def test_catches_duplicate(self):
        wf = load_fixture("invalid_duplicate_schema.json")
        result = verify(wf)
        assert not result.passed

    def test_error_message_has_schema_name(self):
        wf = load_fixture("invalid_duplicate_schema.json")
        result = verify(wf)
        schema_errors = [e for e in result.errors if e.check_type == "schema"]
        assert any("UserData" in e.message and "Duplicate" in e.message for e in schema_errors)


class TestInvalidGuardBadField:
    """Test guard referencing nonexistent field."""

    def test_catches_bad_field(self):
        wf = load_fixture("invalid_guard_bad_field.json")
        result = verify(wf)
        assert not result.passed

    def test_error_identifies_field_and_step(self):
        wf = load_fixture("invalid_guard_bad_field.json")
        result = verify(wf)
        guard_errors = [e for e in result.errors if e.check_type == "guard"]
        assert len(guard_errors) > 0
        assert any(
            "score" in e.message and "filter_leads" in (e.step or "")
            for e in guard_errors
        ), f"Expected guard error about 'score' in 'filter_leads'. Errors: {[e.message for e in guard_errors]}"

    def test_error_lists_available_fields(self):
        wf = load_fixture("invalid_guard_bad_field.json")
        result = verify(wf)
        guard_errors = [e for e in result.errors if e.check_type == "guard"]
        assert any("email" in e.message and "name" in e.message for e in guard_errors)


class TestInvalidUndeclaredEffect:
    """Test undeclared effect detection (heuristic)."""

    def test_warns_about_undeclared_effect(self):
        wf = load_fixture("invalid_undeclared_effect.json")
        result = verify(wf)
        # This is a heuristic warning, not an error — workflow still passes
        assert result.passed
        assert len(result.warnings) > 0

    def test_warning_identifies_step(self):
        wf = load_fixture("invalid_undeclared_effect.json")
        result = verify(wf)
        effect_warnings = [w for w in result.warnings if w.check_type == "effect"]
        assert any(
            w.step == "search_external" for w in effect_warnings
        ), f"Expected warning for 'search_external'. Warnings: {[w.message for w in effect_warnings]}"


# --- Trace tests ---


class TestVerificationTrace:
    """Test that traces are human-readable and informative."""

    def test_valid_workflow_trace_has_pass_marks(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = verify(wf)
        assert "\u2705" in result.trace

    def test_invalid_workflow_trace_has_fail_marks(self):
        wf = load_fixture("invalid_type_mismatch.json")
        result = verify(wf)
        assert "\u274c" in result.trace

    def test_warnings_in_trace(self):
        wf = load_fixture("valid_with_warnings.json")
        result = verify(wf)
        assert "\u26a0\ufe0f" in result.trace

    def test_trace_includes_effects_manifest(self):
        wf = load_fixture("valid_crm_pipeline.json")
        result = verify(wf)
        assert "Effects manifest" in result.trace

    def test_trace_is_multiline(self):
        wf = load_fixture("valid_complex_pipeline.json")
        result = verify(wf)
        lines = result.trace.strip().split("\n")
        assert len(lines) > 5


# --- Engine behavior tests ---


class TestEngineEdgeCases:
    """Test engine behavior for edge cases."""

    def test_step_inherits_previous_output_as_input(self):
        """When input_schema is None, step inherits previous step's output."""
        wf = load_fixture("valid_crm_pipeline.json")
        # First step has input_schema=None, should inherit workflow input
        result = verify(wf)
        assert result.passed

    def test_effects_manifest_aggregation(self):
        wf = load_fixture("valid_complex_pipeline.json")
        result = verify(wf)
        effect_kinds = [e.kind for e in result.effects_manifest]
        assert "read" in effect_kinds
        assert "call" in effect_kinds
        assert "write" in effect_kinds
        assert "send" in effect_kinds

    def test_errors_and_warnings_are_disjoint(self):
        """Errors list and warnings list should not overlap."""
        wf = load_fixture("valid_with_warnings.json")
        result = verify(wf)
        error_messages = {e.message for e in result.errors}
        warning_messages = {w.message for w in result.warnings}
        assert error_messages.isdisjoint(warning_messages)

    def test_suggestion_present_on_errors(self):
        """Actionable suggestions should be present on error results."""
        wf = load_fixture("invalid_guard_bad_field.json")
        result = verify(wf)
        for error in result.errors:
            assert error.suggestion is not None, (
                f"Error missing suggestion: {error.message}"
            )
