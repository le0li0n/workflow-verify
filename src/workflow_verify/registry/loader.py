"""Static YAML schema loading — extracted from Phase 5a registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from workflow_verify.ast.models import FieldDef, Schema
from workflow_verify.ast.types import WFType

_SCHEMAS_DIR = Path(__file__).parent / "schemas"

_VALID_TYPES = {t.value for t in WFType}


class SchemaLoadError(Exception):
    """Raised when a schema YAML file cannot be loaded or is invalid."""


def _parse_field_type(type_str: str) -> WFType:
    if type_str not in _VALID_TYPES:
        raise SchemaLoadError(
            f"Invalid field type '{type_str}'. "
            f"Valid types: {', '.join(sorted(_VALID_TYPES))}"
        )
    return WFType(type_str)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SchemaLoadError(f"Invalid YAML in {path}: {e}")

    if not isinstance(data, dict):
        raise SchemaLoadError(f"Schema file {path} must contain a YAML mapping")
    if "name" not in data:
        raise SchemaLoadError(f"Schema file {path} missing required 'name' field")
    if "fields" not in data or not isinstance(data["fields"], list):
        raise SchemaLoadError(f"Schema file {path} missing required 'fields' list")
    return data


def _yaml_to_schema(data: dict[str, Any], path: Path) -> Schema:
    fields: list[FieldDef] = []
    for i, field_data in enumerate(data["fields"]):
        if not isinstance(field_data, dict):
            raise SchemaLoadError(
                f"Field {i} in {path} must be a mapping, got {type(field_data).__name__}"
            )
        if "name" not in field_data:
            raise SchemaLoadError(f"Field {i} in {path} missing 'name'")
        if "type" not in field_data:
            raise SchemaLoadError(
                f"Field '{field_data['name']}' in {path} missing 'type'"
            )
        field_type = _parse_field_type(field_data["type"])
        fields.append(
            FieldDef(
                name=field_data["name"],
                type=field_type,
                description=field_data.get("description", ""),
                validate=field_data.get("validate"),
            )
        )
    return Schema(
        name=data["name"],
        fields=fields,
        description=data.get("description", ""),
    )


def load_schema(path: str) -> Schema:
    """Load a schema by its registry path (e.g. 'crm/salesforce_lead')."""
    full_path = _SCHEMAS_DIR / f"{path}.yaml"
    if not full_path.exists():
        raise SchemaLoadError(
            f"Schema '{path}' not found at {full_path}. "
            f"Available categories: {', '.join(list_categories())}"
        )
    data = _load_yaml(full_path)
    return _yaml_to_schema(data, full_path)


def list_categories() -> list[str]:
    return sorted(
        d.name for d in _SCHEMAS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def list_schemas(category: str | None = None) -> list[str]:
    if category:
        cat_dir = _SCHEMAS_DIR / category
        if not cat_dir.is_dir():
            return []
        return sorted(f"{category}/{f.stem}" for f in cat_dir.glob("*.yaml"))
    results: list[str] = []
    for cat in list_categories():
        results.extend(list_schemas(cat))
    return results


def search_schemas(keyword: str) -> list[Schema]:
    keyword_lower = keyword.lower()
    matches: list[Schema] = []
    for schema_path in list_schemas():
        full_path = _SCHEMAS_DIR / f"{schema_path}.yaml"
        data = _load_yaml(full_path)
        searchable = " ".join([
            data.get("name", ""),
            data.get("description", ""),
            data.get("source", ""),
            " ".join(
                f"{f.get('name', '')} {f.get('description', '')} {f.get('type', '')}"
                for f in data.get("fields", [])
                if isinstance(f, dict)
            ),
        ]).lower()
        if keyword_lower in searchable:
            matches.append(_yaml_to_schema(data, full_path))
    return matches
