"""Clay table definition resolver."""

from __future__ import annotations

import os
from typing import Any

from workflow_verify.ast.models import FieldDef, Schema
from workflow_verify.ast.types import WFType
from workflow_verify.resolvers.base import SchemaResolveError, SchemaResolver

CLAY_TYPE_MAP: dict[str, WFType] = {
    "text": WFType.TEXT,
    "number": WFType.FLOAT,
    "email": WFType.EMAIL,
    "url": WFType.URL,
    "boolean": WFType.BOOL,
    "date": WFType.DATE,
    "json": WFType.JSON,
    "list": WFType.JSON,
    "rich_text": WFType.TEXT,
    "phone": WFType.PHONE,
    "select": WFType.TEXT,
    "multi_select": WFType.JSON,
}


class ClayResolver(SchemaResolver):
    """Resolves schemas from Clay table definitions.

    For Clay, object_type is the table ID — every table has unique columns.

    TODO: Implement once Clay's table metadata API endpoint is documented.
    The expected flow:
    1. GET /api/v1/tables/{table_id}/columns (or similar)
    2. Parse column definitions into FieldDefs
    3. Map Clay column types -> WFType
    """

    service_name = "clay"

    def supported_objects(self) -> list[str]:
        return []  # Dynamic — every Clay table is unique

    def env_var_names(self) -> list[str]:
        return ["CLAY_API_KEY"]

    def map_type(self, service_type: str) -> WFType:
        return CLAY_TYPE_MAP.get(service_type.lower(), WFType.ANY)

    def _get_api_key(self, credentials: dict) -> str:
        key = credentials.get("api_key")
        if not key:
            key = os.environ.get("CLAY_API_KEY")
        if not key:
            raise SchemaResolveError(
                "Clay API key required. Provide 'api_key' in credentials "
                "or set CLAY_API_KEY environment variable."
            )
        return key

    async def resolve(
        self,
        object_type: str,
        credentials: dict,
        include_custom: bool = True,
    ) -> Schema:
        _api_key = self._get_api_key(credentials)

        # TODO: Replace with actual Clay API call when endpoint is available.
        # Expected implementation:
        #
        # url = f"https://api.clay.com/v1/tables/{object_type}/columns"
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(
        #         url, headers={"Authorization": f"Bearer {api_key}"}
        #     )
        # columns = response.json().get("columns", [])
        # return self._parse_columns(columns, object_type)

        raise SchemaResolveError(
            f"Clay resolver not yet implemented. "
            f"Use static schema fallback or provide a Clay table schema manually. "
            f"Table ID: {object_type}"
        )

    def _parse_columns(self, columns: list[dict[str, Any]], table_id: str) -> Schema:
        """Parse Clay column definitions into a Schema.

        Expected column format:
        {"name": "column_name", "type": "text", "label": "Column Label"}
        """
        fields: list[FieldDef] = []
        for col in columns:
            field_type = self.map_type(col.get("type", "text"))
            fields.append(
                FieldDef(
                    name=col["name"],
                    type=field_type,
                    description=col.get("label", ""),
                )
            )
        return Schema(
            name=f"ClayTable_{table_id}",
            fields=fields,
            description=f"Live schema from Clay table '{table_id}'",
        )
