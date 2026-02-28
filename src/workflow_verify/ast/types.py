"""Type system for workflow data flowing between pipeline steps."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class WFType(str, Enum):
    """Built-in scalar types for workflow fields."""

    TEXT = "Text"
    INT = "Int"
    FLOAT = "Float"
    BOOL = "Bool"
    EMAIL = "Email"
    URL = "Url"
    PHONE = "Phone"
    DATE = "Date"
    DATETIME = "DateTime"
    JSON = "Json"
    ANY = "Any"


# Subtype relationships: key is-a-subtype-of each value in its set
_SUBTYPES: dict[WFType, set[WFType]] = {
    WFType.EMAIL: {WFType.TEXT},
    WFType.URL: {WFType.TEXT},
    WFType.PHONE: {WFType.TEXT},
    WFType.INT: {WFType.FLOAT},
    WFType.DATE: {WFType.TEXT},
    WFType.DATETIME: {WFType.TEXT},
}


class ListType(BaseModel):
    """List[T] — a homogeneous list of a single element type."""

    kind: str = Field("List", frozen=True)
    element: AnyWFType


class OptionalType(BaseModel):
    """Optional[T] — the value may be absent/null."""

    kind: str = Field("Optional", frozen=True)
    inner: AnyWFType


class RecordField(BaseModel):
    """A single field within a RecordType."""

    name: str
    type: AnyWFType
    required: bool = True


class RecordType(BaseModel):
    """A named record with typed fields (structural typing)."""

    kind: str = Field("Record", frozen=True)
    name: str = ""
    fields: list[RecordField] = []


# Union of all types that can appear in a field definition
AnyWFType = Annotated[
    WFType | ListType | OptionalType | RecordType,
    Field(discriminator=None),
]

# Rebuild models now that forward refs are defined
ListType.model_rebuild()
OptionalType.model_rebuild()
RecordType.model_rebuild()


def is_compatible(source: AnyWFType, target: AnyWFType) -> bool:
    """Check if `source` type can be passed where `target` type is expected.

    Rules:
    - Any is compatible with everything (both directions).
    - Email/URL/Phone/Date/DateTime are subtypes of Text.
    - Int is a subtype of Float.
    - Optional[T] is compatible with T (but not reverse).
    - List[T] is compatible with List[T] only (invariant).
    - RecordType uses structural subtyping: source must have all of target's
      required fields with compatible types.
    """
    # Identical types always match
    if source == target:
        return True

    # Any is the universal escape hatch
    if source is WFType.ANY or target is WFType.ANY:
        return True
    if isinstance(source, WFType) and source == WFType.ANY:
        return True
    if isinstance(target, WFType) and target == WFType.ANY:
        return True

    # Scalar subtype checks
    if isinstance(source, WFType) and isinstance(target, WFType):
        supers = _SUBTYPES.get(source, set())
        if target in supers:
            return True
        # Transitive: check if any super of source is compatible with target
        for s in supers:
            if is_compatible(s, target):
                return True
        return False

    # Optional[T] -> T: stripping Optional is allowed (caller guarantees presence)
    if isinstance(source, OptionalType) and not isinstance(target, OptionalType):
        return is_compatible(source.inner, target)

    # T -> Optional[T]: always fine (value is present)
    if not isinstance(source, OptionalType) and isinstance(target, OptionalType):
        return is_compatible(source, target.inner)

    # Optional[A] -> Optional[B]
    if isinstance(source, OptionalType) and isinstance(target, OptionalType):
        return is_compatible(source.inner, target.inner)

    # List invariance
    if isinstance(source, ListType) and isinstance(target, ListType):
        return is_compatible(source.element, target.element)

    # Record structural subtyping
    if isinstance(source, RecordType) and isinstance(target, RecordType):
        source_fields = {f.name: f for f in source.fields}
        for target_field in target.fields:
            if not target_field.required:
                continue
            source_field = source_fields.get(target_field.name)
            if source_field is None:
                return False
            if not is_compatible(source_field.type, target_field.type):
                return False
        return True

    return False
