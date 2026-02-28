"""TypeScript transpiler — generates Zod schemas + typed async pipeline."""

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
    WFType.TEXT: "z.string()",
    WFType.INT: "z.number().int()",
    WFType.FLOAT: "z.number()",
    WFType.BOOL: "z.boolean()",
    WFType.EMAIL: "z.string().email()",
    WFType.URL: "z.string().url()",
    WFType.PHONE: "z.string()",
    WFType.DATE: "z.string().date()",
    WFType.DATETIME: "z.string().datetime()",
    WFType.JSON: "z.unknown()",
    WFType.ANY: "z.unknown()",
}


def _to_camel(name: str) -> str:
    """Convert snake_case or PascalCase step name to camelCase function name."""
    # If already camelCase/PascalCase, just lowercase first char
    if "_" not in name:
        return name[0].lower() + name[1:]
    parts = name.split("_")
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def _to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase for schema names."""
    if "_" not in name:
        return name[0].upper() + name[1:]
    return "".join(p.capitalize() for p in name.split("_"))


def _type_to_zod(t: AnyWFType) -> str:
    """Convert a WFType to its Zod equivalent."""
    if isinstance(t, WFType):
        return _TYPE_MAP.get(t, "z.unknown()")
    elif isinstance(t, ListType):
        return f"z.array({_type_to_zod(t.element)})"
    elif isinstance(t, OptionalType):
        return f"{_type_to_zod(t.inner)}.optional()"
    elif isinstance(t, RecordType):
        if not t.fields:
            return "z.record(z.unknown())"
        fields = ", ".join(f"  {f.name}: {_type_to_zod(f.type)}" for f in t.fields)
        return f"z.object({{\n{fields}\n}})"
    return "z.unknown()"


def _emit_schema(schema: Schema) -> str:
    """Generate a Zod schema definition."""
    name = _to_pascal(schema.name)
    fields: list[str] = []
    for field in schema.fields:
        zod_type = _type_to_zod(field.type)
        fields.append(f"  {field.name}: {zod_type},")

    fields_str = "\n".join(fields)
    lines = [f"const {name}Schema = z.object({{", fields_str, "});", ""]
    lines.append(f"type {name} = z.infer<typeof {name}Schema>;")
    return "\n".join(lines)


def _emit_step(step: Step, prev_output_schema: str | None, workflow: Workflow) -> str:
    """Generate a typed async function for a step."""
    func_name = _to_camel(step.name)
    input_schema = step.input_schema or prev_output_schema or workflow.input_schema
    output_schema = step.output_schema
    input_type = _to_pascal(input_schema)
    output_type = _to_pascal(output_schema)

    lines: list[str] = []

    # Function signature
    lines.append(f"async function {func_name}(input: {input_type}): Promise<{output_type}> {{")

    # Effect comments
    if step.effects:
        effects_str = ", ".join(f"{e.kind.upper()}:{e.target}" for e in step.effects)
        lines.append(f"  // Effects: {effects_str}")

    # Guard checks
    for guard in step.guards:
        if guard.on_fail == "skip":
            lines.append(f"  if (!({guard.condition})) {{")
            lines.append(f'    console.log("Guard failed: {guard.condition} — skipping");')
            lines.append(f"    return input as unknown as {output_type};")
            lines.append("  }")
        elif guard.on_fail == "error":
            lines.append(f"  if (!({guard.condition})) {{")
            lines.append(f'    throw new Error("Guard failed: {guard.condition}");')
            lines.append("  }")
        elif guard.on_fail == "default":
            default_val = (
                repr(guard.default_value) if guard.default_value is not None else "undefined"
            )
            lines.append(f"  if (!({guard.condition})) {{")
            lines.append(f"    return {default_val} as unknown as {output_type};")
            lines.append("  }")

    # Body placeholder
    lines.append(f"  // TODO: Implement {step.description or step.name}")
    lines.append(f'  throw new Error("Not implemented: {func_name}");')
    lines.append("}")

    return "\n".join(lines)


def _emit_pipeline(workflow: Workflow) -> str:
    """Generate the runWorkflow orchestration function."""
    input_type = _to_pascal(workflow.input_schema)
    output_type = _to_pascal(workflow.output_schema)

    lines: list[str] = []
    lines.append(f"async function runWorkflow(input: {input_type}): Promise<{output_type}> {{")

    for i, step in enumerate(workflow.steps):
        func_name = _to_camel(step.name)
        if i == 0:
            lines.append(f"  const step{i + 1} = await {func_name}(input);")
        else:
            lines.append(f"  const step{i + 1} = await {func_name}(step{i});")

    if workflow.steps:
        lines.append(f"  return step{len(workflow.steps)};")
    else:
        lines.append("  return input as unknown as any;")

    lines.append("}")

    return "\n".join(lines)


def transpile_typescript(workflow: Workflow) -> TranspileResult:
    """Transpile a workflow AST to TypeScript with Zod schemas."""
    parts: list[str] = []

    # Import
    parts.append('import { z } from "zod";\n')

    # Schemas
    parts.append("// === Schemas ===\n")
    for schema in workflow.schemas:
        parts.append(_emit_schema(schema))
        parts.append("")

    # Step functions
    parts.append("\n// === Steps ===\n")
    prev_output: str | None = None
    for step in workflow.steps:
        parts.append(_emit_step(step, prev_output, workflow))
        parts.append("")
        prev_output = step.output_schema

    # Pipeline
    parts.append("\n// === Pipeline ===\n")
    parts.append(_emit_pipeline(workflow))
    parts.append("")

    # Export
    parts.append("export { runWorkflow };")
    parts.append("")

    code = "\n".join(parts)
    filename = re.sub(r"[^a-z0-9]+", "_", workflow.name.lower()).strip("_") + ".ts"

    return TranspileResult(
        target=TranspileTarget.TYPESCRIPT,
        code=code,
        filename=filename,
        dependencies=["zod"],
        instructions=(
            "1. npm install zod\n"
            "2. Fill in the TODO sections in each step function\n"
            "3. Import and call runWorkflow() with your input data"
        ),
    )
