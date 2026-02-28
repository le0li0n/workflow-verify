"""Transpiler suite — converts verified Workflow ASTs to executable code."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from workflow_verify.ast.models import Workflow


class TranspileTarget(str, Enum):
    TYPESCRIPT = "typescript"
    PYTHON = "python"
    TEMPORAL = "temporal"


class TranspileResult(BaseModel):
    target: TranspileTarget
    code: str
    filename: str
    dependencies: list[str]
    instructions: str


def transpile(workflow: "Workflow", target: TranspileTarget) -> TranspileResult:
    """Transpile a verified workflow AST to executable code.

    Raises ValueError if the workflow has not been verified or fails verification.
    """
    from workflow_verify.verify.engine import verify

    result = verify(workflow)
    if not result.passed:
        error_messages = "; ".join(e.message for e in result.errors)
        raise ValueError(
            f"Workflow '{workflow.name}' failed verification and cannot be "
            f"transpiled. Errors: {error_messages}"
        )

    if target == TranspileTarget.TYPESCRIPT:
        from workflow_verify.transpile.typescript import transpile_typescript
        return transpile_typescript(workflow)
    elif target == TranspileTarget.PYTHON:
        from workflow_verify.transpile.python_target import transpile_python
        return transpile_python(workflow)
    elif target == TranspileTarget.TEMPORAL:
        from workflow_verify.transpile.temporal import transpile_temporal
        return transpile_temporal(workflow)
    else:
        raise ValueError(f"Unknown transpile target: {target}")


__all__ = ["TranspileResult", "TranspileTarget", "transpile"]
