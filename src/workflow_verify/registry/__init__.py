"""Schema registry — unified API for static and dynamic schema resolution.

Static schemas are loaded from YAML files (Phase 5a).
Dynamic schemas are resolved from live service APIs (Phase 5b).
The unified API tries dynamic first, falls back to static.
"""

from workflow_verify.registry.loader import (
    SchemaLoadError,
    list_categories,
    list_schemas,
    load_schema,
    search_schemas,
)
from workflow_verify.resolvers import resolve_schema

__all__ = [
    "SchemaLoadError",
    "list_categories",
    "list_schemas",
    "load_schema",
    "resolve_schema",
    "search_schemas",
]
