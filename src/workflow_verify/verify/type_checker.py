"""Type flow checker — validates data flows correctly between pipeline steps."""

from __future__ import annotations

from workflow_verify.ast.models import Schema, Workflow
from workflow_verify.ast.types import RecordField, RecordType, is_compatible

from .results import CheckResult


def _schema_to_record(schema: Schema) -> RecordType:
    """Convert an AST Schema to a RecordType for compatibility checking."""
    return RecordType(
        kind="Record",
        name=schema.name,
        fields=[RecordField(name=f.name, type=f.type, required=True) for f in schema.fields],
    )


def _format_fields(schema: Schema) -> str:
    """Format a schema's fields for error messages."""
    return ", ".join(
        f"{f.name} ({f.type.value if hasattr(f.type, 'value') else f.type})" for f in schema.fields
    )


def check_type_flow(workflow: Workflow) -> list[CheckResult]:
    """Check that data flows correctly between sequential pipeline steps."""
    results: list[CheckResult] = []
    schema_map = {s.name: s for s in workflow.schemas}

    # Resolve each step's effective input/output schemas
    resolved_inputs: list[Schema | None] = []
    resolved_outputs: list[Schema] = []

    for i, step in enumerate(workflow.steps):
        # Resolve output schema (must always exist — schema_checker validates reference)
        out_schema = schema_map.get(step.output_schema)
        resolved_outputs.append(out_schema)  # type: ignore[arg-type]

        # Resolve input schema
        if step.input_schema is not None:
            in_schema = schema_map.get(step.input_schema)
            resolved_inputs.append(in_schema)
        elif i == 0:
            # First step with no explicit input inherits workflow input
            in_schema = schema_map.get(workflow.input_schema)
            resolved_inputs.append(in_schema)
        else:
            # Inherit previous step's output
            resolved_inputs.append(resolved_outputs[i - 1])

    # 1 & 2. Schema existence checks (already covered by schema_checker, but
    # we need the resolved schemas to proceed — bail on missing ones)
    for _i, step in enumerate(workflow.steps):
        if step.output_schema not in schema_map:
            results.append(
                CheckResult(
                    passed=False,
                    check_type="type_flow",
                    step=step.name,
                    message=f"Step '{step.name}' output schema '{step.output_schema}' not found.",
                    severity="error",
                )
            )
        if step.input_schema is not None and step.input_schema not in schema_map:
            results.append(
                CheckResult(
                    passed=False,
                    check_type="type_flow",
                    step=step.name,
                    message=f"Step '{step.name}' input schema '{step.input_schema}' not found.",
                    severity="error",
                )
            )

    # If we have missing schemas, we can't do flow analysis
    if any(not r.passed for r in results):
        return results

    # 3. First step's input must be compatible with workflow input
    if workflow.steps:
        wf_input = schema_map.get(workflow.input_schema)
        first_input = resolved_inputs[0]
        if wf_input and first_input:
            wf_rec = _schema_to_record(wf_input)
            first_rec = _schema_to_record(first_input)
            if is_compatible(wf_rec, first_rec):
                results.append(
                    CheckResult(
                        passed=True,
                        check_type="type_flow",
                        step=workflow.steps[0].name,
                        message=(
                            f"Step '{workflow.steps[0].name}' input compatible "
                            f"with workflow input '{workflow.input_schema}'."
                        ),
                        severity="info",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        passed=False,
                        check_type="type_flow",
                        step=workflow.steps[0].name,
                        message=(
                            f"Step '{workflow.steps[0].name}' input schema "
                            f"'{first_input.name}' is not compatible with "
                            f"workflow input schema '{workflow.input_schema}'. "
                            f"Workflow input fields: "
                            f"{_format_fields(wf_input)}."
                        ),
                        severity="error",
                    )
                )

    # 4. Last step's output must be compatible with workflow output
    if workflow.steps:
        wf_output = schema_map.get(workflow.output_schema)
        last_output = resolved_outputs[-1]
        if wf_output and last_output:
            last_rec = _schema_to_record(last_output)
            wf_out_rec = _schema_to_record(wf_output)
            if is_compatible(last_rec, wf_out_rec):
                results.append(
                    CheckResult(
                        passed=True,
                        check_type="type_flow",
                        step=workflow.steps[-1].name,
                        message=(
                            f"Step '{workflow.steps[-1].name}' output satisfies "
                            f"workflow output '{workflow.output_schema}'."
                        ),
                        severity="info",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        passed=False,
                        check_type="type_flow",
                        step=workflow.steps[-1].name,
                        message=(
                            f"Step '{workflow.steps[-1].name}' output schema '{last_output.name}' "
                            f"does not satisfy workflow output schema '{workflow.output_schema}'. "
                            f"Expected fields: {_format_fields(wf_output)}."
                        ),
                        severity="error",
                    )
                )

    # 5. Consecutive step compatibility
    for i in range(1, len(workflow.steps)):
        prev_step = workflow.steps[i - 1]
        curr_step = workflow.steps[i]
        prev_output = resolved_outputs[i - 1]
        curr_input = resolved_inputs[i]

        if prev_output is None or curr_input is None:
            continue

        prev_rec = _schema_to_record(prev_output)
        curr_rec = _schema_to_record(curr_input)

        if is_compatible(prev_rec, curr_rec):
            results.append(
                CheckResult(
                    passed=True,
                    check_type="type_flow",
                    step=curr_step.name,
                    message=(
                        f"Step '{curr_step.name}' input compatible with '{prev_step.name}' output."
                    ),
                    severity="info",
                )
            )
        else:
            # Find the specific missing/incompatible fields
            prev_fields = {f.name: f for f in prev_output.fields}
            missing = []
            incompatible = []
            for field in curr_input.fields:
                if field.name not in prev_fields:
                    ftype = field.type.value if hasattr(field.type, "value") else field.type
                    missing.append(f"{field.name} ({ftype})")
                elif not is_compatible(prev_fields[field.name].type, field.type):
                    prev_t = prev_fields[field.name].type
                    got = prev_t.value if hasattr(prev_t, "value") else prev_t
                    exp = field.type.value if hasattr(field.type, "value") else field.type
                    incompatible.append(f"{field.name} (got {got}, expected {exp})")

            parts = []
            if missing:
                parts.append(f"Missing fields: {', '.join(missing)}")
            if incompatible:
                parts.append(f"Incompatible fields: {', '.join(incompatible)}")

            results.append(
                CheckResult(
                    passed=False,
                    check_type="type_flow",
                    step=curr_step.name,
                    message=(
                        f"Step '{curr_step.name}' requires fields from '{curr_input.name}' "
                        f"but previous step '{prev_step.name}' output schema "
                        f"'{prev_output.name}' is not compatible. "
                        f"{'. '.join(parts)}. "
                        f"Available fields: {_format_fields(prev_output)}."
                    ),
                    severity="error",
                    suggestion=(
                        f"Add the missing fields to '{prev_output.name}' or "
                        f"remove them from '{curr_input.name}'."
                    ),
                )
            )

    # 6. Check output schema match for each step (info-level pass)
    for i, step in enumerate(workflow.steps):
        out = resolved_outputs[i]
        if out is not None:
            results.append(
                CheckResult(
                    passed=True,
                    check_type="type_flow",
                    step=step.name,
                    message=f"Step '{step.name}' output matches '{out.name}'.",
                    severity="info",
                )
            )

    return results
