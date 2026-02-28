"""Core Pydantic AST models defining a valid agentic workflow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from workflow_verify.ast.types import AnyWFType


class FieldDef(BaseModel):
    """A named, typed field in a schema or step I/O."""

    model_config = ConfigDict(
        ignored_types=(),
    )

    name: str
    type: AnyWFType
    description: str = ""
    validate_expr: str | None = Field(default=None, serialization_alias="validate", validation_alias="validate")


class Schema(BaseModel):
    """A named data schema — like a Pydantic model definition."""

    name: str
    fields: list[FieldDef]
    description: str = ""


class Effect(BaseModel):
    """A declared side effect."""

    kind: Literal["read", "write", "call", "send", "delete"]
    target: str
    description: str = ""


class Guard(BaseModel):
    """A pre-condition for a step."""

    condition: str
    on_fail: Literal["skip", "error", "default"] = "error"
    default_value: Any | None = None


class Step(BaseModel):
    """A single step in the workflow pipeline."""

    name: str
    description: str = ""
    input_schema: str | None = None
    output_schema: str
    effects: list[Effect] = []
    guards: list[Guard] = []
    config: dict[str, Any] = {}


class Workflow(BaseModel):
    """The top-level workflow AST. This is what the LLM generates."""

    name: str
    description: str = ""
    schemas: list[Schema]
    steps: list[Step]
    input_schema: str
    output_schema: str
    metadata: dict[str, Any] = {}
