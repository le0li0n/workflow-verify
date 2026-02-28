"""Schema checker — validates schema definitions themselves."""

from __future__ import annotations

from workflow_verify.ast.models import Workflow

from .results import CheckResult


def check_schemas(workflow: Workflow) -> list[CheckResult]:
    """Validate all schema definitions and references in the workflow."""
    results: list[CheckResult] = []
    schema_names: dict[str, int] = {}

    # 1. Check for duplicate schema names
    for schema in workflow.schemas:
        if schema.name in schema_names:
            results.append(
                CheckResult(
                    passed=False,
                    check_type="schema",
                    step=None,
                    message=(
                        f"Duplicate schema name '{schema.name}'. "
                        f"First defined at index {schema_names[schema.name]}, "
                        f"duplicated at index {workflow.schemas.index(schema)}."
                    ),
                    severity="error",
                    suggestion=f"Rename one of the '{schema.name}' schemas to be unique.",
                )
            )
        else:
            schema_names[schema.name] = workflow.schemas.index(schema)

    # 2. Check for duplicate field names within each schema
    for schema in workflow.schemas:
        field_names: set[str] = set()
        for field in schema.fields:
            if field.name in field_names:
                results.append(
                    CheckResult(
                        passed=False,
                        check_type="schema",
                        step=None,
                        message=(
                            f"Schema '{schema.name}' has duplicate field name '{field.name}'."
                        ),
                        severity="error",
                        suggestion=(
                            f"Remove or rename the duplicate "
                            f"'{field.name}' field in schema "
                            f"'{schema.name}'."
                        ),
                    )
                )
            field_names.add(field.name)

    # 3. Check validate expressions reference 'value'
    for schema in workflow.schemas:
        for field in schema.fields:
            expr = field.validate_expr
            if expr is not None and "value" not in expr:
                results.append(
                    CheckResult(
                        passed=False,
                        check_type="schema",
                        step=None,
                        message=(
                            f"Schema '{schema.name}', field '{field.name}': "
                            f"validation expression '{expr}' does not reference 'value'."
                        ),
                        severity="warning",
                        suggestion=(
                            "Validation expressions should reference 'value', e.g. 'value >= 0'."
                        ),
                    )
                )

    # 4. Check all schema references in steps exist
    for step in workflow.steps:
        if step.input_schema is not None and step.input_schema not in schema_names:
            results.append(
                CheckResult(
                    passed=False,
                    check_type="schema",
                    step=step.name,
                    message=(
                        f"Step '{step.name}' references input schema "
                        f"'{step.input_schema}' which does not exist."
                    ),
                    severity="error",
                    suggestion=(
                        f"Define a schema named '{step.input_schema}' or use one of: "
                        f"{', '.join(sorted(schema_names.keys()))}."
                    ),
                )
            )
        if step.output_schema not in schema_names:
            results.append(
                CheckResult(
                    passed=False,
                    check_type="schema",
                    step=step.name,
                    message=(
                        f"Step '{step.name}' references output schema "
                        f"'{step.output_schema}' which does not exist."
                    ),
                    severity="error",
                    suggestion=(
                        f"Define a schema named '{step.output_schema}' or use one of: "
                        f"{', '.join(sorted(schema_names.keys()))}."
                    ),
                )
            )

    # 5. Workflow-level input/output schema references
    if workflow.input_schema not in schema_names:
        results.append(
            CheckResult(
                passed=False,
                check_type="schema",
                step=None,
                message=(f"Workflow input_schema '{workflow.input_schema}' does not exist."),
                severity="error",
                suggestion=(
                    f"Define a schema named '{workflow.input_schema}' or use one of: "
                    f"{', '.join(sorted(schema_names.keys()))}."
                ),
            )
        )
    if workflow.output_schema not in schema_names:
        results.append(
            CheckResult(
                passed=False,
                check_type="schema",
                step=None,
                message=(f"Workflow output_schema '{workflow.output_schema}' does not exist."),
                severity="error",
                suggestion=(
                    f"Define a schema named '{workflow.output_schema}' or use one of: "
                    f"{', '.join(sorted(schema_names.keys()))}."
                ),
            )
        )

    # Add passing checks for valid schemas
    for schema in workflow.schemas:
        if schema.name in schema_names:
            has_errors = any(not r.passed and schema.name in r.message for r in results)
            if not has_errors:
                validate_count = sum(1 for f in schema.fields if f.validate_expr is not None)
                detail = f"{len(schema.fields)} fields validated"
                if validate_count:
                    rule_s = "s" if validate_count > 1 else ""
                    detail += f", {validate_count} validation rule{rule_s}"
                results.append(
                    CheckResult(
                        passed=True,
                        check_type="schema",
                        step=None,
                        message=f"Schema '{schema.name}' — {detail}.",
                        severity="info",
                    )
                )

    return results
