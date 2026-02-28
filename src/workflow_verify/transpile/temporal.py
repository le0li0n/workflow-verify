"""Temporal transpiler — generates Temporal workflow + activity definitions."""

from __future__ import annotations

import re

from workflow_verify.ast.models import Schema, Step, Workflow
from workflow_verify.ast.types import (
    AnyWFType,
    ListType,
    OptionalType,
    RecordType,
    WFType,
)
from workflow_verify.transpile import TranspileResult, TranspileTarget

_TYPE_MAP: dict[WFType, str] = {
    WFType.TEXT: "str",
    WFType.INT: "int",
    WFType.FLOAT: "float",
    WFType.BOOL: "bool",
    WFType.EMAIL: "str",
    WFType.URL: "str",
    WFType.PHONE: "str",
    WFType.DATE: "str",
    WFType.DATETIME: "str",
    WFType.JSON: "Any",
    WFType.ANY: "Any",
}


def _to_snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _to_pascal(name: str) -> str:
    # Handle spaces, underscores, and hyphens
    parts = re.split(r"[\s_\-]+", name)
    return "".join(p.capitalize() for p in parts if p)


def _type_to_python(t: AnyWFType) -> str:
    if isinstance(t, WFType):
        return _TYPE_MAP.get(t, "Any")
    elif isinstance(t, ListType):
        return f"list[{_type_to_python(t.element)}]"
    elif isinstance(t, OptionalType):
        return f"{_type_to_python(t.inner)} | None"
    elif isinstance(t, RecordType):
        return "dict[str, Any]"
    return "Any"


def _emit_dataclass(schema: Schema) -> str:
    """Generate a dataclass for Temporal serialization."""
    name = _to_pascal(schema.name)
    lines: list[str] = []
    lines.append("@dataclass")
    lines.append(f"class {name}:")
    if schema.description:
        lines.append(f'    """{schema.description}"""')
        lines.append("")

    for field in schema.fields:
        py_type = _type_to_python(field.type)
        if field.description:
            lines.append(f"    {field.name}: {py_type}  # {field.description}")
        else:
            lines.append(f"    {field.name}: {py_type}")

    if not schema.fields:
        lines.append("    pass")

    return "\n".join(lines)


def _translate_guard_condition(condition: str) -> str:
    c = condition.strip()
    c = re.sub(r"(\w+)\s+is\s+not\s+null", r"input.\1 is not None", c)
    c = re.sub(r"(\w+)\s+is\s+null", r"input.\1 is None", c)
    c = re.sub(r"^(\w+)\s*(>=|<=|>|<|==|!=)\s*(.+)$", r"input.\1 \2 \3", c)
    return c


def _emit_activity(step: Step, prev_output_schema: str | None, workflow: Workflow) -> str:
    """Generate a Temporal activity function."""
    func_name = _to_snake(step.name)
    input_schema = step.input_schema or prev_output_schema or workflow.input_schema
    output_schema = step.output_schema
    input_type = _to_pascal(input_schema)
    output_type = _to_pascal(output_schema)

    lines: list[str] = []
    lines.append("@activity.defn")
    lines.append(f"async def {func_name}(input: {input_type}) -> {output_type}:")
    if step.description:
        lines.append(f'    """{step.description}"""')

    # Log effects via activity context
    if step.effects:
        for effect in step.effects:
            lines.append(
                f'    activity.logger.info("Effect: {effect.kind.upper()}:{effect.target}")'
            )

    # Guard checks
    for guard in step.guards:
        field_condition = _translate_guard_condition(guard.condition)
        if guard.on_fail == "skip":
            lines.append(f"    if not ({field_condition}):")
            msg = f"Guard failed: {guard.condition} — skipping"
            lines.append(f'        activity.logger.info("{msg}")')
            lines.append("        return input  # type: ignore[return-value]")
        elif guard.on_fail == "error":
            lines.append(f"    if not ({field_condition}):")
            lines.append(f'        raise ApplicationError("Guard failed: {guard.condition}")')
        elif guard.on_fail == "default":
            default_val = repr(guard.default_value) if guard.default_value is not None else "None"
            lines.append(f"    if not ({field_condition}):")
            lines.append(f"        return {default_val}  # type: ignore[return-value]")

    lines.append(f"    # TODO: Implement {step.description or step.name}")
    lines.append(f'    raise NotImplementedError("{func_name}")')

    return "\n".join(lines)


def _emit_workflow_class(workflow: Workflow) -> str:
    """Generate a Temporal Workflow class."""
    class_name = _to_pascal(workflow.name) + "Workflow"
    input_type = _to_pascal(workflow.input_schema)
    output_type = _to_pascal(workflow.output_schema)

    lines: list[str] = []
    lines.append("@workflow.defn")
    lines.append(f"class {class_name}:")
    if workflow.description:
        lines.append(f'    """{workflow.description}"""')
        lines.append("")

    lines.append("    @workflow.run")
    lines.append(f"    async def run(self, input: {input_type}) -> {output_type}:")

    for i, step in enumerate(workflow.steps):
        func_name = _to_snake(step.name)
        if i == 0:
            lines.append(f"        step{i + 1} = await workflow.execute_activity(")
            lines.append(f"            {func_name},")
            lines.append("            input,")
        else:
            lines.append(f"        step{i + 1} = await workflow.execute_activity(")
            lines.append(f"            {func_name},")
            lines.append(f"            step{i},")

        lines.append("            start_to_close_timeout=timedelta(seconds=60),")
        lines.append("        )")

    if workflow.steps:
        lines.append(f"        return step{len(workflow.steps)}")
    else:
        lines.append("        return input  # type: ignore[return-value]")

    return "\n".join(lines)


def transpile_temporal(workflow: Workflow) -> TranspileResult:
    """Transpile a workflow AST to Temporal workflow + activity definitions."""
    parts: list[str] = []

    # Imports
    parts.append(f'"""Temporal workflow: {workflow.name}"""')
    parts.append("")
    parts.append("from __future__ import annotations")
    parts.append("")
    parts.append("from dataclasses import dataclass")
    parts.append("from datetime import timedelta")
    parts.append("from typing import Any")
    parts.append("")
    parts.append("from temporalio import activity, workflow")
    parts.append("from temporalio.exceptions import ApplicationError")
    parts.append("")
    parts.append("")

    # Data classes
    parts.append("# === Data Models ===")
    parts.append("")
    for schema in workflow.schemas:
        parts.append(_emit_dataclass(schema))
        parts.append("")
        parts.append("")

    # Activities
    parts.append("# === Activities ===")
    parts.append("")
    prev_output: str | None = None
    for step in workflow.steps:
        parts.append(_emit_activity(step, prev_output, workflow))
        parts.append("")
        parts.append("")
        prev_output = step.output_schema

    # Workflow class
    parts.append("# === Workflow ===")
    parts.append("")
    parts.append(_emit_workflow_class(workflow))
    parts.append("")

    code = "\n".join(parts)
    filename = re.sub(r"[^a-z0-9]+", "_", workflow.name.lower()).strip("_") + "_temporal.py"

    return TranspileResult(
        target=TranspileTarget.TEMPORAL,
        code=code,
        filename=filename,
        dependencies=["temporalio"],
        instructions=(
            "1. pip install temporalio\n"
            "2. Fill in the TODO sections in each activity function\n"
            "3. Register activities and workflow with a Temporal worker\n"
            "4. Start the workflow via a Temporal client"
        ),
    )
