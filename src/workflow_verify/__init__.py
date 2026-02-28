"""Workflow Verify — Pre-execution verification for LLM-generated agentic workflows."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal

# --- AST models & types ---
from workflow_verify.ast.models import (
    Effect,
    FieldDef,
    Guard,
    Schema,
    Step,
    Workflow,
)
from workflow_verify.ast.schema import (
    get_workflow_json_schema,
    get_workflow_tool_definition,
)
from workflow_verify.ast.types import (
    AnyWFType,
    ListType,
    OptionalType,
    RecordField,
    RecordType,
    WFType,
    is_compatible,
)

# --- Self-correction ---
from workflow_verify.correct import (
    Attempt,
    CorrectionRequest,
    CorrectionResult,
    LLMClient,
    format_correction_request,
    generate_and_verify,
)

# --- Registry ---
from workflow_verify.registry import (
    SchemaLoadError,
    list_categories,
    list_schemas,
    load_schema,
    resolve_schema,
    search_schemas,
)

# --- Trace ---
from workflow_verify.trace.reporter import format_trace

# --- Transpilation ---
from workflow_verify.transpile import (
    TranspileResult,
    TranspileTarget,
    transpile,
)

# --- Verification ---
from workflow_verify.verify import (
    CheckResult,
    VerificationResult,
    verify,
)

if TYPE_CHECKING:
    pass


# --- Convenience functions ---


async def run(
    prompt: str,
    target: str = "python",
    *,
    llm: Literal["anthropic", "openai"] = "anthropic",
    client: LLMClient | None = None,
    schemas: list[Schema] | None = None,
    max_attempts: int = 3,
) -> str:
    """Generate a verified workflow from a prompt and return transpiled code.

    This is the high-level convenience wrapper around generate_and_verify().

    Args:
        prompt: Natural language description of the desired workflow.
        target: Transpile target ("python", "typescript", "temporal").
        llm: LLM provider name (ignored if client is provided).
        client: Optional pre-built LLM client.
        schemas: Optional pre-defined schemas.
        max_attempts: Maximum generation attempts.

    Returns:
        Transpiled code as a string.

    Raises:
        RuntimeError: If the correction loop fails to converge.
    """
    result = await generate_and_verify(
        prompt=prompt,
        schemas=schemas,
        max_attempts=max_attempts,
        llm=llm,
        client=client,
        target=target,
    )
    if not result.converged or result.transpiled is None:
        raise RuntimeError(f"Failed to generate a valid workflow after {max_attempts} attempts")
    return result.transpiled.code


def run_sync(
    prompt: str,
    target: str = "python",
    *,
    llm: Literal["anthropic", "openai"] = "anthropic",
    client: LLMClient | None = None,
    schemas: list[Schema] | None = None,
    max_attempts: int = 3,
) -> str:
    """Synchronous wrapper for run(). See run() for details."""
    return asyncio.run(
        run(
            prompt,
            target,
            llm=llm,
            client=client,
            schemas=schemas,
            max_attempts=max_attempts,
        )
    )


def effects(workflow: Workflow, *, strict: bool = True) -> list[Effect]:
    """Verify a workflow and return its effects manifest.

    Args:
        workflow: The Workflow AST to verify.
        strict: If True, undeclared effects are errors; otherwise warnings.

    Returns:
        List of declared Effect objects from the verification result.

    Raises:
        ValueError: If verification fails with errors.
    """
    result = verify(workflow, strict=strict)
    if not result.passed:
        error_messages = "; ".join(e.message for e in result.errors)
        raise ValueError(f"Workflow verification failed: {error_messages}")
    return result.effects_manifest


__all__ = [
    # AST models
    "Effect",
    "FieldDef",
    "Guard",
    "Schema",
    "Step",
    "Workflow",
    # AST types
    "AnyWFType",
    "ListType",
    "OptionalType",
    "RecordField",
    "RecordType",
    "WFType",
    "is_compatible",
    # AST schema utilities
    "get_workflow_json_schema",
    "get_workflow_tool_definition",
    # Verification
    "CheckResult",
    "VerificationResult",
    "verify",
    # Transpilation
    "TranspileResult",
    "TranspileTarget",
    "transpile",
    # Self-correction
    "Attempt",
    "CorrectionRequest",
    "CorrectionResult",
    "LLMClient",
    "format_correction_request",
    "generate_and_verify",
    # Registry
    "SchemaLoadError",
    "list_categories",
    "list_schemas",
    "load_schema",
    "resolve_schema",
    "search_schemas",
    # Trace
    "format_trace",
    # Convenience
    "effects",
    "run",
    "run_sync",
]
