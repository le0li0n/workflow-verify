"""Python transpiler — generates Pydantic models + typed async pipeline."""

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
    WFType.EMAIL: "EmailStr",
    WFType.URL: "HttpUrl",
    WFType.PHONE: "str",
    WFType.DATE: "str",
    WFType.DATETIME: "str",
    WFType.JSON: "Any",
    WFType.ANY: "Any",
}

_NEEDS_EMAIL_STR = False
_NEEDS_HTTP_URL = False


def _to_snake(name: str) -> str:
    """Convert PascalCase or camelCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    if "_" not in name:
        return name[0].upper() + name[1:]
    return "".join(p.capitalize() for p in name.split("_"))


def _type_to_python(t: AnyWFType) -> str:
    """Convert a WFType to its Python type annotation."""
    if isinstance(t, WFType):
        return _TYPE_MAP.get(t, "Any")
    elif isinstance(t, ListType):
        return f"list[{_type_to_python(t.element)}]"
    elif isinstance(t, OptionalType):
        return f"{_type_to_python(t.inner)} | None"
    elif isinstance(t, RecordType):
        return "dict[str, Any]"
    return "Any"


def _emit_schema(schema: Schema) -> tuple[str, bool, bool]:
    """Generate a Pydantic model class. Returns (code, needs_email, needs_url)."""
    name = _to_pascal(schema.name)
    needs_email = False
    needs_url = False

    lines: list[str] = []
    if schema.description:
        lines.append(f"class {name}(BaseModel):")
        lines.append(f'    """{schema.description}"""')
        lines.append("")
    else:
        lines.append(f"class {name}(BaseModel):")

    for field in schema.fields:
        py_type = _type_to_python(field.type)
        if isinstance(field.type, WFType) and field.type == WFType.EMAIL:
            needs_email = True
        if isinstance(field.type, WFType) and field.type == WFType.URL:
            needs_url = True

        if field.description:
            lines.append(f"    {field.name}: {py_type}  # {field.description}")
        else:
            lines.append(f"    {field.name}: {py_type}")

    if not schema.fields:
        lines.append("    pass")

    return "\n".join(lines), needs_email, needs_url


def _emit_step(step: Step, prev_output_schema: str | None, workflow: Workflow) -> str:
    """Generate a typed async function for a step."""
    func_name = _to_snake(step.name)
    input_schema = step.input_schema or prev_output_schema or workflow.input_schema
    output_schema = step.output_schema
    input_type = _to_pascal(input_schema)
    output_type = _to_pascal(output_schema)

    lines: list[str] = []

    # Effect decorator-style comments
    if step.effects:
        for effect in step.effects:
            lines.append(f'# @effect({effect.kind}, "{effect.target}")')

    # Function signature
    lines.append(f"async def {func_name}(input: {input_type}) -> {output_type}:")
    if step.description:
        lines.append(f'    """{step.description}"""')

    # Guard checks
    for guard in step.guards:
        field_condition = _translate_guard_condition(guard.condition)
        if guard.on_fail == "skip":
            lines.append(f"    if not ({field_condition}):")
            lines.append(f'        print("Guard failed: {guard.condition} — skipping")')
            lines.append("        return input  # type: ignore[return-value]")
        elif guard.on_fail == "error":
            lines.append(f"    if not ({field_condition}):")
            lines.append(f'        raise ValueError("Guard failed: {guard.condition}")')
        elif guard.on_fail == "default":
            default_val = repr(guard.default_value) if guard.default_value is not None else "None"
            lines.append(f"    if not ({field_condition}):")
            lines.append(f"        return {default_val}  # type: ignore[return-value]")

    # Body placeholder
    lines.append(f"    # TODO: Implement {step.description or step.name}")
    lines.append(f'    raise NotImplementedError("{func_name}")')

    return "\n".join(lines)


def _translate_guard_condition(condition: str) -> str:
    """Translate a guard condition to Python syntax."""
    c = condition.strip()
    # "field is not null" -> "input.field is not None"
    c = re.sub(r"(\w+)\s+is\s+not\s+null", r"input.\1 is not None", c)
    # "field is null" -> "input.field is None"
    c = re.sub(r"(\w+)\s+is\s+null", r"input.\1 is None", c)
    # "field >= value" -> "input.field >= value"
    c = re.sub(r"^(\w+)\s*(>=|<=|>|<|==|!=)\s*(.+)$", r"input.\1 \2 \3", c)
    return c


def _emit_pipeline(workflow: Workflow) -> str:
    """Generate the run_workflow orchestration function."""
    input_type = _to_pascal(workflow.input_schema)
    output_type = _to_pascal(workflow.output_schema)

    lines: list[str] = []
    lines.append(f"async def run_workflow(input: {input_type}) -> {output_type}:")
    lines.append(f'    """Execute the {workflow.name} pipeline."""')

    for i, step in enumerate(workflow.steps):
        func_name = _to_snake(step.name)
        if i == 0:
            lines.append(f"    step{i + 1} = await {func_name}(input)")
        else:
            lines.append(f"    step{i + 1} = await {func_name}(step{i})")

    if workflow.steps:
        lines.append(f"    return step{len(workflow.steps)}")
    else:
        lines.append("    return input  # type: ignore[return-value]")

    return "\n".join(lines)


def transpile_python(workflow: Workflow) -> TranspileResult:
    """Transpile a workflow AST to Python with Pydantic models."""
    parts: list[str] = []
    needs_email = False
    needs_url = False

    # Generate schemas first to detect import needs
    schema_parts: list[str] = []
    for schema in workflow.schemas:
        code, ne, nu = _emit_schema(schema)
        schema_parts.append(code)
        needs_email = needs_email or ne
        needs_url = needs_url or nu

    # Imports
    parts.append(f'"""Auto-generated workflow: {workflow.name}"""')
    parts.append("")
    parts.append("from __future__ import annotations")
    parts.append("")

    typing_imports = ["Any"]
    parts.append(f"from typing import {', '.join(sorted(typing_imports))}")
    parts.append("")
    parts.append("from pydantic import BaseModel")

    extra_imports: list[str] = []
    if needs_email:
        extra_imports.append("EmailStr")
    if needs_url:
        extra_imports.append("HttpUrl")
    if extra_imports:
        parts.append(f"from pydantic import {', '.join(sorted(extra_imports))}")

    parts.append("")
    parts.append("")

    # Schemas
    parts.append("# === Schemas ===")
    parts.append("")
    for sp in schema_parts:
        parts.append(sp)
        parts.append("")
        parts.append("")

    # Step functions
    parts.append("# === Steps ===")
    parts.append("")
    prev_output: str | None = None
    for step in workflow.steps:
        parts.append(_emit_step(step, prev_output, workflow))
        parts.append("")
        parts.append("")
        prev_output = step.output_schema

    # Pipeline
    parts.append("# === Pipeline ===")
    parts.append("")
    parts.append(_emit_pipeline(workflow))
    parts.append("")

    code = "\n".join(parts)
    filename = re.sub(r"[^a-z0-9]+", "_", workflow.name.lower()).strip("_") + ".py"

    dependencies = ["pydantic>=2.0"]
    if needs_email or needs_url:
        dependencies.append("email-validator")

    return TranspileResult(
        target=TranspileTarget.PYTHON,
        code=code,
        filename=filename,
        dependencies=dependencies,
        instructions=(
            f"1. pip install {' '.join(dependencies)}\n"
            f"2. Fill in the TODO sections in each step function\n"
            f"3. Import and await run_workflow() with your input data"
        ),
    )
