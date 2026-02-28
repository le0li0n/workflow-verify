"""MCP server — exposes workflow-verify as tools for LLMs.

Run with:
    python -m workflow_verify.mcp_server

Or configure in Claude Desktop's claude_desktop_config.json:
    {
      "mcpServers": {
        "workflow-verify": {
          "command": "uv",
          "args": ["--directory", "/path/to/workflow_verify", "run",
                   "python", "-m", "workflow_verify.mcp_server"]
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Literal

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "Error: mcp package required. Install with: pip install 'workflow-verify[mcp]'",
        file=sys.stderr,
    )
    sys.exit(1)

mcp = FastMCP(
    "workflow-verify",
    instructions=(
        "Pre-execution verification for LLM-generated agentic workflows. "
        "Verify workflow ASTs for type safety, schema validity, side effects, "
        "and guard conditions before any code executes."
    ),
)


@mcp.tool()
def verify_workflow(
    workflow_json: str,
    strict: bool = True,
    target: str | None = None,
) -> str:
    """Verify a workflow AST and optionally transpile it to code.

    Takes a workflow AST as a JSON string, runs the full verification
    engine (type flow, schemas, effects, guards), and returns the
    result with a human-readable trace.

    Args:
        workflow_json: The workflow AST as a JSON string.
        strict: If true, undeclared effects are errors. If false, warnings only.
        target: Optional transpile target: "python", "typescript", or "temporal".
    """
    from workflow_verify import (
        TranspileTarget,
        Workflow,
        format_trace,
        transpile,
        verify,
    )

    try:
        data = json.loads(workflow_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    try:
        workflow = Workflow(**data)
    except Exception as e:
        return json.dumps({"error": f"Invalid workflow structure: {e}"})

    result = verify(workflow, strict=strict)

    output: dict = {
        "passed": result.passed,
        "trace": format_trace(result.checks),
        "errors": [
            {"message": c.message, "step": c.step, "suggestion": c.suggestion}
            for c in result.errors
        ],
        "warnings": [{"message": c.message, "step": c.step} for c in result.warnings],
        "effects": [
            {"kind": e.kind, "target": e.target, "description": e.description}
            for e in result.effects_manifest
        ],
    }

    if target and result.passed:
        try:
            transpiled = transpile(workflow, TranspileTarget(target))
            output["transpiled"] = {
                "target": transpiled.target.value,
                "code": transpiled.code,
                "filename": transpiled.filename,
                "dependencies": transpiled.dependencies,
            }
        except ValueError as e:
            output["transpile_error"] = str(e)

    return json.dumps(output, indent=2)


@mcp.tool()
async def generate_verified_workflow(
    prompt: str,
    target: str = "python",
    llm: str = "anthropic",
    max_attempts: int = 3,
    schemas_json: str | None = None,
) -> str:
    """Generate a verified workflow from a natural language prompt.

    Runs the full generate-verify-correct loop: an LLM generates a
    workflow AST, it's verified, and if there are errors the LLM
    self-corrects until the workflow passes or attempts are exhausted.

    Returns the verified workflow AST, transpiled code, and audit trail.

    Args:
        prompt: Natural language description of the desired workflow.
        target: Transpile target: "python", "typescript", or "temporal".
        llm: LLM provider to use: "anthropic" or "openai".
        max_attempts: Maximum correction attempts before giving up.
        schemas_json: Optional JSON array of pre-defined schemas to include.
    """
    from workflow_verify import Schema, format_trace, generate_and_verify

    schemas = None
    if schemas_json:
        try:
            raw_schemas = json.loads(schemas_json)
            schemas = [Schema(**s) for s in raw_schemas]
        except Exception as e:
            return json.dumps({"error": f"Invalid schemas_json: {e}"})

    try:
        llm_provider: Literal["anthropic", "openai"] = (
            "anthropic" if llm == "anthropic" else "openai"
        )
        result = await generate_and_verify(
            prompt=prompt,
            schemas=schemas,
            max_attempts=max_attempts,
            llm=llm_provider,
            target=target,
        )
    except ImportError as e:
        return json.dumps(
            {
                "error": str(e),
                "hint": f"Install the LLM provider: pip install {llm}",
            }
        )
    except Exception as e:
        return json.dumps({"error": f"Generation failed: {e}"})

    output: dict = {
        "converged": result.converged,
        "attempts": len(result.attempts),
    }

    if result.workflow:
        output["workflow"] = json.loads(result.workflow.model_dump_json())

    if result.verification:
        output["verification"] = {
            "passed": result.verification.passed,
            "trace": format_trace(result.verification.checks),
            "errors": [
                {"message": c.message, "step": c.step, "suggestion": c.suggestion}
                for c in result.verification.errors
            ],
            "effects": [
                {"kind": e.kind, "target": e.target, "description": e.description}
                for e in result.verification.effects_manifest
            ],
        }

    if result.transpiled:
        output["transpiled"] = {
            "target": result.transpiled.target.value,
            "code": result.transpiled.code,
            "filename": result.transpiled.filename,
            "dependencies": result.transpiled.dependencies,
        }

    output["attempt_details"] = []
    for attempt in result.attempts:
        detail: dict = {"attempt": attempt.attempt_number}
        if attempt.error_message:
            detail["error"] = attempt.error_message
        if attempt.verification:
            detail["passed"] = attempt.verification.passed
            detail["error_count"] = len(attempt.verification.errors)
        output["attempt_details"].append(detail)

    return json.dumps(output, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
