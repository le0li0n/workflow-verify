"""Main verification engine — orchestrates all checkers."""

from __future__ import annotations

from workflow_verify.ast.models import Workflow
from workflow_verify.trace.reporter import format_trace

from .effect_checker import check_effects
from .guard_checker import check_guards
from .results import CheckResult, VerificationResult
from .schema_checker import check_schemas
from .type_checker import check_type_flow


def verify(workflow: Workflow, strict: bool = True) -> VerificationResult:
    """Main entry point. Runs all checkers, aggregates results.

    Args:
        workflow: The workflow AST to verify.
        strict: If True, warnings also cause verification to fail.

    Returns:
        VerificationResult with pass/fail, all checks, effects manifest, and trace.
    """
    all_checks: list[CheckResult] = []

    # 1. Schema checks (run first — other checkers depend on valid schemas)
    schema_results = check_schemas(workflow)
    all_checks.extend(schema_results)

    # If schema checks have errors, still run other checkers for completeness
    # but they may produce redundant errors

    # 2. Type flow checks
    type_results = check_type_flow(workflow)
    all_checks.extend(type_results)

    # 3. Effect checks
    effect_results, effects_manifest = check_effects(workflow)
    all_checks.extend(effect_results)

    # 4. Guard checks
    guard_results = check_guards(workflow)
    all_checks.extend(guard_results)

    # Aggregate
    errors = [c for c in all_checks if c.severity == "error" and not c.passed]
    warnings = [c for c in all_checks if c.severity == "warning"]

    if strict:
        passed = len(errors) == 0
    else:
        passed = len(errors) == 0

    trace = format_trace(all_checks)

    return VerificationResult(
        passed=passed,
        checks=all_checks,
        effects_manifest=effects_manifest,
        trace=trace,
        errors=errors,
        warnings=warnings,
    )
