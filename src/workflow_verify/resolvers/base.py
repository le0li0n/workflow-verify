"""Abstract base class for schema resolvers + type mapping utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from workflow_verify.ast.models import Schema
from workflow_verify.ast.types import WFType

# Common type mappings shared across resolvers
COMMON_TYPE_MAP: dict[str, WFType] = {
    "string": WFType.TEXT,
    "str": WFType.TEXT,
    "text": WFType.TEXT,
    "varchar": WFType.TEXT,
    "char": WFType.TEXT,
    "int": WFType.INT,
    "integer": WFType.INT,
    "bigint": WFType.INT,
    "smallint": WFType.INT,
    "number": WFType.FLOAT,
    "float": WFType.FLOAT,
    "double": WFType.FLOAT,
    "decimal": WFType.FLOAT,
    "numeric": WFType.FLOAT,
    "bool": WFType.BOOL,
    "boolean": WFType.BOOL,
    "email": WFType.EMAIL,
    "phone": WFType.PHONE,
    "phone_number": WFType.PHONE,
    "url": WFType.URL,
    "date": WFType.DATE,
    "datetime": WFType.DATETIME,
    "timestamp": WFType.DATETIME,
    "json": WFType.JSON,
    "jsonb": WFType.JSON,
    "object": WFType.JSON,
    "array": WFType.JSON,
}


class SchemaResolveError(Exception):
    """Raised when a resolver fails to fetch or parse a live schema."""


async def http_get(
    url: str,
    headers: dict | None = None,
    auth: tuple | None = None,
    params: dict | None = None,
) -> Any:
    """Shared HTTP GET helper. Raises SchemaResolveError if httpx is missing."""
    try:
        import httpx
    except ImportError:
        raise SchemaResolveError(
            "httpx package required for live resolvers. Install with: pip install httpx"
        ) from None
    async with httpx.AsyncClient() as client:
        return await client.get(url, headers=headers, auth=auth, params=params)


class SchemaResolver(ABC):
    """Base class for dynamic schema resolvers.

    Each resolver knows how to fetch live schema from one service.
    """

    service_name: str

    @abstractmethod
    async def resolve(
        self,
        object_type: str,
        credentials: dict,
        include_custom: bool = True,
    ) -> Schema:
        """Fetch the live schema from the service API.

        Args:
            object_type: The object/table to describe (e.g. "contact", "Lead").
            credentials: Service-specific auth (API key, OAuth token, etc.).
            include_custom: Whether to include custom/user-defined fields.

        Returns:
            A Schema with all fields from the live service.

        Raises:
            SchemaResolveError: If the API call fails or credentials are invalid.
        """

    @abstractmethod
    def supported_objects(self) -> list[str]:
        """List the object types this resolver can handle."""

    def map_type(self, service_type: str) -> WFType:
        """Map a service-specific type string to a WFType.

        Override per resolver for service-specific mappings.
        Falls back to COMMON_TYPE_MAP, then WFType.ANY.
        """
        return COMMON_TYPE_MAP.get(service_type.lower(), WFType.ANY)

    def env_var_names(self) -> list[str]:
        """Return environment variable names this resolver checks for credentials."""
        return []
