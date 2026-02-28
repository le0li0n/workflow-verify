"""Guard checker — validates guard conditions are well-formed."""

from __future__ import annotations

import re

from workflow_verify.ast.models import Schema, Workflow
from workflow_verify.ast.types import WFType

from .results import CheckResult

# Operators and the types they're valid for
_NUMERIC_OPS = {">=", "<=", ">", "<"}
_ALL_OPS = {">=", "<=", ">", "<", "==", "!=", "is", "is not"}

_NUMERIC_TYPES = {WFType.INT, WFType.FLOAT}

# Pattern to extract field name and operator from a guard condition
# Handles: "field >= 70", "field is not null", "field == 'value'"
_CONDITION_PATTERN = re.compile(
    r"^(\w+)\s+(>=|<=|>|<|==|!=|is\s+not|is)\s+(.+)$",
    re.IGNORECASE,
)


def _parse_condition(condition: str) -> tuple[str | None, str | None, str | None]:
    """Parse a guard condition into (field, operator, value).

    Returns (None, None, None) if unparseable.
    """
    match = _CONDITION_PATTERN.match(condition.strip())
    if not match:
        return None, None, None
    field = match.group(1)
    op = match.group(2).lower()
    if "is  not" in op:
        op = "is not"
    value = match.group(3).strip()
    return field, op, value


def check_guards(workflow: Workflow) -> list[CheckResult]:
    """Validate guard conditions reference real fields and are well-formed."""
    results: list[CheckResult] = []
    schema_map = {s.name: s for s in workflow.schemas}

    for i, step in enumerate(workflow.steps):
        if not step.guards:
            continue

        # Resolve the step's input schema
        if step.input_schema is not None:
            input_schema = schema_map.get(step.input_schema)
        elif i == 0:
            input_schema = schema_map.get(workflow.input_schema)
        else:
            prev_output = workflow.steps[i - 1].output_schema
            input_schema = schema_map.get(prev_output)

        if input_schema is None:
            # Schema doesn't exist — schema_checker will catch this
            continue

        field_map = {f.name: f for f in input_schema.fields}

        for guard in step.guards:
            field_name, op, value = _parse_condition(guard.condition)

            # 2. Syntactic validity
            if field_name is None:
                results.append(
                    CheckResult(
                        passed=True,
                        check_type="guard",
                        step=step.name,
                        message=(
                            f"Step '{step.name}' guard condition "
                            f"'{guard.condition}' could not be parsed. "
                            f"Expected format: 'field_name operator value'."
                        ),
                        severity="warning",
                        suggestion="Use format like 'score >= 70' or 'email is not null'.",
                    )
                )
                continue

            # 1. Field existence check
            if field_name not in field_map:
                results.append(
                    CheckResult(
                        passed=False,
                        check_type="guard",
                        step=step.name,
                        message=(
                            f"Step '{step.name}' guard references field "
                            f"'{field_name}' which does not exist in input "
                            f"schema '{input_schema.name}'. "
                            f"Available fields: {', '.join(sorted(field_map.keys()))}."
                        ),
                        severity="error",
                        suggestion=(
                            f"Use one of the available fields: "
                            f"{', '.join(sorted(field_map.keys()))}."
                        ),
                    )
                )
                continue

            # 3. Operator/type compatibility
            field_def = field_map[field_name]
            field_type = field_def.type

            if isinstance(field_type, WFType) and op in _NUMERIC_OPS:
                if field_type not in _NUMERIC_TYPES:
                    results.append(
                        CheckResult(
                            passed=True,
                            check_type="guard",
                            step=step.name,
                            message=(
                                f"Step '{step.name}' guard uses numeric operator "
                                f"'{op}' on field '{field_name}' which has type "
                                f"'{field_type.value}'. This may not behave as expected."
                            ),
                            severity="warning",
                            suggestion=(
                                f"Numeric comparisons are intended for Int/Float fields. "
                                f"Consider using '==' or 'is not null' for {field_type.value} fields."
                            ),
                        )
                    )
                    continue

            # Guard is valid
            results.append(
                CheckResult(
                    passed=True,
                    check_type="guard",
                    step=step.name,
                    message=(
                        f"Step '{step.name}' guard '{guard.condition}' "
                        f"references valid field '{field_name}'."
                    ),
                    severity="info",
                )
            )

    # 4. Warn about write effects without guards
    for step in workflow.steps:
        has_write = any(e.kind in ("write", "delete") for e in step.effects)
        if has_write and not step.guards:
            results.append(
                CheckResult(
                    passed=True,
                    check_type="guard",
                    step=step.name,
                    message=(
                        f"Step '{step.name}' has write/delete effects but no "
                        f"guard conditions."
                    ),
                    severity="warning",
                    suggestion=(
                        f"Add a guard to step '{step.name}' to prevent "
                        f"unprotected writes."
                    ),
                )
            )

    return results
