"""Self-correction protocol — formats errors for LLM self-repair and drives the correction loop."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from workflow_verify.ast.models import Schema, Workflow
from workflow_verify.ast.schema import get_workflow_json_schema
from workflow_verify.transpile import TranspileResult
from workflow_verify.verify.engine import verify
from workflow_verify.verify.results import CheckResult, VerificationResult

logger = logging.getLogger(__name__)

# --- Error classification ---

_ERROR_TYPE_LABELS: dict[str, str] = {
    "type_flow": "TYPE_FLOW_ERROR",
    "schema": "SCHEMA_ERROR",
    "effect": "EFFECT_WARNING",
    "guard": "GUARD_ERROR",
}


# --- Correction request model ---


class CorrectionRequest(BaseModel):
    """Structured correction request sent to the LLM for self-repair."""

    original_prompt: str
    original_ast: Workflow
    errors: list[CheckResult]
    suggestions: list[str]
    instruction: str


class Attempt(BaseModel):
    """Record of a single generation/verification attempt."""

    attempt_number: int
    workflow: Workflow | None
    verification: VerificationResult | None
    correction: CorrectionRequest | None
    error_message: str | None = None


class CorrectionResult(BaseModel):
    """Final result of the generate-and-verify loop."""

    workflow: Workflow | None
    verification: VerificationResult | None
    transpiled: TranspileResult | None
    attempts: list[Attempt]
    converged: bool


# --- Format correction request ---


def format_correction_request(
    prompt: str,
    ast: Workflow,
    result: VerificationResult,
) -> CorrectionRequest:
    """Format a failed verification into an LLM-friendly correction request."""
    errors = result.errors
    suggestions: list[str] = []

    instruction_parts: list[str] = []
    instruction_parts.append(
        f"The workflow AST you generated has {len(errors)} error{'s' if len(errors) != 1 else ''}:"
    )
    instruction_parts.append("")

    for i, error in enumerate(errors, 1):
        label = _ERROR_TYPE_LABELS.get(error.check_type, error.check_type.upper())
        step_info = f" in step '{error.step}'" if error.step else ""

        instruction_parts.append(f"{i}. {label}{step_info}: {error.message}")

        if error.suggestion:
            instruction_parts.append(f"   FIX: {error.suggestion}")
            suggestions.append(error.suggestion)

        instruction_parts.append("")

    # Add warnings as additional context
    if result.warnings:
        instruction_parts.append(
            f"Additionally, there are {len(result.warnings)} warning{'s' if len(result.warnings) != 1 else ''}:"
        )
        for warning in result.warnings:
            step_info = f" in step '{warning.step}'" if warning.step else ""
            instruction_parts.append(f"  - {warning.message}")
        instruction_parts.append("")

    instruction_parts.append(
        "Please regenerate the workflow AST with these errors fixed. "
        "Return the complete corrected workflow."
    )

    instruction = "\n".join(instruction_parts)

    return CorrectionRequest(
        original_prompt=prompt,
        original_ast=ast,
        errors=errors,
        suggestions=suggestions,
        instruction=instruction,
    )


# --- LLM client protocol ---


class LLMClient(Protocol):
    """Protocol for LLM clients used by the correction loop."""

    async def generate_workflow(
        self,
        prompt: str,
        schema: dict,
    ) -> dict[str, Any]:
        """Generate a workflow AST from a prompt using structured outputs.

        Returns the raw dict that should parse into a Workflow model.
        """
        ...


# --- Built-in LLM clients ---


class AnthropicClient:
    """Anthropic API client for workflow generation."""

    def __init__(self) -> None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install anthropic"
            )
        self._client = anthropic.AsyncAnthropic()

    async def generate_workflow(
        self,
        prompt: str,
        schema: dict,
    ) -> dict[str, Any]:
        import anthropic

        response = await self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            tools=[
                {
                    "name": "generate_workflow",
                    "description": (
                        "Generate a verified workflow AST that defines a "
                        "multi-step agentic pipeline."
                    ),
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "generate_workflow"},
            messages=[{"role": "user", "content": prompt}],
        )

        for block in response.content:
            if block.type == "tool_use":
                return block.input

        raise ValueError("No tool_use block in Anthropic response")


class OpenAIClient:
    """OpenAI API client for workflow generation."""

    def __init__(self) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install openai"
            )
        self._client = openai.AsyncOpenAI()

    async def generate_workflow(
        self,
        prompt: str,
        schema: dict,
    ) -> dict[str, Any]:
        response = await self._client.responses.create(
            model="gpt-4o",
            input=[{"role": "user", "content": prompt}],
            text={"format": {"type": "json_schema", "name": "workflow", "schema": schema}},
        )

        import json as json_mod

        return json_mod.loads(response.output_text)


def _make_client(llm: str) -> LLMClient:
    """Create an LLM client by name."""
    if llm == "anthropic":
        return AnthropicClient()
    elif llm == "openai":
        return OpenAIClient()
    else:
        raise ValueError(f"Unknown LLM provider: {llm}. Use 'anthropic' or 'openai'.")


# --- Correction loop ---


def _build_correction_prompt(
    original_prompt: str,
    correction: CorrectionRequest,
) -> str:
    """Build the prompt for a correction attempt."""
    return (
        f"Original request: {original_prompt}\n\n"
        f"Your previous attempt had errors. Here is the feedback:\n\n"
        f"{correction.instruction}\n\n"
        f"Previous (broken) AST for reference:\n"
        f"{correction.original_ast.model_dump_json(indent=2)}"
    )


async def generate_and_verify(
    prompt: str,
    schemas: list[Schema] | None = None,
    max_attempts: int = 3,
    llm: Literal["anthropic", "openai"] = "anthropic",
    client: LLMClient | None = None,
    target: str | None = None,
) -> CorrectionResult:
    """Full loop: generate -> verify -> (if fail) correct -> re-verify.

    Args:
        prompt: Natural language description of the desired workflow.
        schemas: Optional pre-defined schemas to include in the prompt.
        max_attempts: Maximum generation attempts before giving up.
        llm: Which LLM provider to use (ignored if client is provided).
        client: Optional pre-built LLM client (for testing/custom clients).
        target: Optional transpile target (e.g. "typescript", "python", "temporal").

    Returns:
        CorrectionResult with the final workflow, verification, and attempt history.
    """
    if client is None:
        client = _make_client(llm)

    workflow_schema = get_workflow_json_schema()
    attempts: list[Attempt] = []
    current_prompt = prompt

    # Add schema context if provided
    if schemas:
        schema_context = "\n\nUse these pre-defined schemas:\n"
        for s in schemas:
            schema_context += f"- {s.name}: {s.description or 'No description'}\n"
            for f in s.fields:
                schema_context += f"  - {f.name}: {f.type}\n"
        current_prompt = prompt + schema_context

    last_workflow: Workflow | None = None
    last_verification: VerificationResult | None = None

    for attempt_num in range(1, max_attempts + 1):
        logger.info(f"Attempt {attempt_num}/{max_attempts}")

        # Generate
        try:
            raw = await client.generate_workflow(current_prompt, workflow_schema)
            workflow = Workflow(**raw)
        except Exception as e:
            logger.warning(f"Attempt {attempt_num} failed to parse: {e}")
            attempts.append(
                Attempt(
                    attempt_number=attempt_num,
                    workflow=None,
                    verification=None,
                    correction=None,
                    error_message=str(e),
                )
            )
            # For parse errors, ask LLM to try again with the error
            current_prompt = (
                f"Original request: {prompt}\n\n"
                f"Your previous response could not be parsed into a valid "
                f"Workflow. Error: {e}\n\n"
                f"Please try again, ensuring the output matches the schema exactly."
            )
            continue

        last_workflow = workflow

        # Verify
        result = verify(workflow)
        last_verification = result

        if result.passed:
            logger.info(f"Verification passed on attempt {attempt_num}")

            # Optionally transpile
            transpiled = None
            if target:
                from workflow_verify.transpile import TranspileTarget, transpile

                transpiled = transpile(workflow, TranspileTarget(target))

            attempts.append(
                Attempt(
                    attempt_number=attempt_num,
                    workflow=workflow,
                    verification=result,
                    correction=None,
                )
            )

            return CorrectionResult(
                workflow=workflow,
                verification=result,
                transpiled=transpiled,
                attempts=attempts,
                converged=True,
            )

        # Failed — format correction and retry
        logger.info(
            f"Attempt {attempt_num} failed with {len(result.errors)} errors"
        )
        correction = format_correction_request(prompt, workflow, result)
        attempts.append(
            Attempt(
                attempt_number=attempt_num,
                workflow=workflow,
                verification=result,
                correction=correction,
            )
        )

        current_prompt = _build_correction_prompt(prompt, correction)

    # Exhausted attempts
    logger.warning(f"Failed to converge after {max_attempts} attempts")
    return CorrectionResult(
        workflow=last_workflow,
        verification=last_verification,
        transpiled=None,
        attempts=attempts,
        converged=False,
    )
