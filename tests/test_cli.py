"""Tests for the wfv CLI tool."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run the CLI via python -m for realistic testing."""
    return subprocess.run(
        [sys.executable, "-m", "workflow_verify.cli", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


# --- Help ---


class TestHelp:
    def test_no_args_shows_help(self):
        r = run_cli()
        assert r.returncode == 0
        assert "verify" in r.stdout
        assert "transpile" in r.stdout
        assert "registry" in r.stdout
        assert "generate" in r.stdout

    def test_help_flag(self):
        r = run_cli("--help")
        assert r.returncode == 0
        assert "Workflow Verify" in r.stdout

    def test_verify_help(self):
        r = run_cli("verify", "--help")
        assert r.returncode == 0
        assert "--json" in r.stdout
        assert "--no-strict" in r.stdout

    def test_transpile_help(self):
        r = run_cli("transpile", "--help")
        assert r.returncode == 0
        assert "--target" in r.stdout


# --- Verify ---


class TestVerifyCommand:
    def test_valid_workflow_passes(self):
        r = run_cli("verify", str(FIXTURES / "valid_crm_pipeline.json"))
        assert r.returncode == 0
        assert "passed" in r.stdout.lower() or "✅" in r.stdout

    def test_invalid_workflow_fails(self):
        r = run_cli("verify", str(FIXTURES / "invalid_type_mismatch.json"))
        assert r.returncode == 1

    def test_missing_file(self):
        r = run_cli("verify", "/nonexistent/file.json")
        assert r.returncode == 1
        assert "not found" in r.stderr.lower() or "error" in r.stderr.lower()

    def test_json_output(self):
        r = run_cli("verify", str(FIXTURES / "valid_crm_pipeline.json"), "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["passed"] is True
        assert "effects" in data

    def test_json_output_with_errors(self):
        r = run_cli("verify", str(FIXTURES / "invalid_type_mismatch.json"), "--json")
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["passed"] is False
        assert len(data["errors"]) > 0

    def test_effects_shown(self):
        r = run_cli("verify", str(FIXTURES / "valid_crm_pipeline.json"))
        assert r.returncode == 0
        assert "Effects" in r.stdout or "effects" in r.stdout.lower()

    def test_no_strict_mode(self):
        r = run_cli("verify", str(FIXTURES / "valid_with_warnings.json"), "--no-strict")
        assert r.returncode == 0


# --- Transpile ---


class TestTranspileCommand:
    def test_transpile_python(self):
        r = run_cli("transpile", str(FIXTURES / "valid_crm_pipeline.json"), "-t", "python")
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_transpile_typescript(self):
        r = run_cli("transpile", str(FIXTURES / "valid_crm_pipeline.json"), "-t", "typescript")
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_transpile_temporal(self):
        r = run_cli("transpile", str(FIXTURES / "valid_crm_pipeline.json"), "-t", "temporal")
        assert r.returncode == 0
        assert len(r.stdout) > 0

    def test_transpile_output_file(self):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            outpath = f.name
        try:
            r = run_cli(
                "transpile",
                str(FIXTURES / "valid_crm_pipeline.json"),
                "-t",
                "python",
                "-o",
                outpath,
            )
            assert r.returncode == 0
            content = Path(outpath).read_text()
            assert len(content) > 0
        finally:
            Path(outpath).unlink(missing_ok=True)

    def test_transpile_invalid_workflow_fails(self):
        r = run_cli("transpile", str(FIXTURES / "invalid_type_mismatch.json"), "-t", "python")
        assert r.returncode == 1
        assert "error" in r.stderr.lower()

    def test_transpile_missing_file(self):
        r = run_cli("transpile", "/nonexistent.json", "-t", "python")
        assert r.returncode == 1


# --- Registry ---


class TestRegistryCommand:
    def test_list_all(self):
        r = run_cli("registry", "list")
        assert r.returncode == 0
        assert len(r.stdout.strip().split("\n")) > 0

    def test_list_by_category(self):
        r = run_cli("registry", "list", "crm")
        assert r.returncode == 0
        output = r.stdout.strip()
        assert len(output) > 0
        # All results should be from the crm category
        for line in output.split("\n"):
            assert "crm/" in line

    def test_list_nonexistent_category(self):
        r = run_cli("registry", "list", "nonexistent_category_xyz")
        assert r.returncode == 1
        assert "error" in r.stderr.lower()

    def test_search(self):
        r = run_cli("registry", "search", "lead")
        assert r.returncode == 0

    def test_search_no_results(self):
        r = run_cli("registry", "search", "zzz_nonexistent_zzz")
        assert r.returncode == 0
        assert "No schemas" in r.stdout

    def test_show(self):
        # First get a valid schema path
        r_list = run_cli("registry", "list")
        paths = r_list.stdout.strip().split("\n")
        assert len(paths) > 0
        first_path = paths[0].strip()

        r = run_cli("registry", "show", first_path)
        assert r.returncode == 0
        assert "Name:" in r.stdout
        assert "Fields" in r.stdout

    def test_show_nonexistent(self):
        r = run_cli("registry", "show", "nonexistent/schema_path")
        assert r.returncode == 1
        assert "error" in r.stderr.lower()

    def test_registry_no_subcommand(self):
        r = run_cli("registry")
        assert r.returncode == 1


# --- Generate ---


class TestGenerateCommand:
    def test_missing_llm_package(self):
        """Generate should fail gracefully when LLM package is missing."""
        r = run_cli("generate", "test prompt", "--llm", "anthropic")
        # Should fail with an error message, not a raw traceback
        assert r.returncode == 1
        assert "Error:" in r.stderr
        # No raw traceback lines like "Traceback (most recent call last):"
        assert "Traceback" not in r.stderr


# --- Edge cases ---


class TestEdgeCases:
    def test_malformed_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("not valid json {{{")
            tmppath = f.name
        try:
            r = run_cli("verify", tmppath)
            assert r.returncode == 1
            assert "error" in r.stderr.lower()
        finally:
            Path(tmppath).unlink(missing_ok=True)

    def test_valid_json_but_not_workflow(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"not": "a workflow"}, f)
            tmppath = f.name
        try:
            r = run_cli("verify", tmppath)
            assert r.returncode == 1
            assert "error" in r.stderr.lower()
        finally:
            Path(tmppath).unlink(missing_ok=True)
