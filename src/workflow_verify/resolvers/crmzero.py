"""CRM Zero schema resolver."""

from __future__ import annotations

import os
from typing import Any

from workflow_verify.ast.models import FieldDef, Schema
from workflow_verify.ast.types import WFType
from workflow_verify.resolvers.base import SchemaResolveError, SchemaResolver

CRMZERO_TYPE_MAP: dict[str, WFType] = {
    "string": WFType.TEXT,
    "text": WFType.TEXT,
    "number": WFType.FLOAT,
    "integer": WFType.INT,
    "email": WFType.EMAIL,
    "phone": WFType.PHONE,
    "url": WFType.URL,
    "boolean": WFType.BOOL,
    "date": WFType.DATE,
    "datetime": WFType.DATETIME,
    "json": WFType.JSON,
    "array": WFType.JSON,
}


class CRMZeroResolver(SchemaResolver):
    """Resolves schemas from CRM Zero.

    TODO: Implement once CRM Zero's schema metadata API is available.
    The expected flow:
    1. GET /api/v1/schemas/{object_type} or similar
    2. Parse field definitions
    3. Map CRM Zero types -> WFType
    """

    service_name = "crmzero"

    def supported_objects(self) -> list[str]:
        return ["contacts", "deals", "accounts", "activities"]

    def env_var_names(self) -> list[str]:
        return ["CRMZERO_API_KEY"]

    def map_type(self, service_type: str) -> WFType:
        return CRMZERO_TYPE_MAP.get(service_type.lower(), WFType.TEXT)

    def _get_api_key(self, credentials: dict) -> str:
        key = credentials.get("api_key")
        if not key:
            key = os.environ.get("CRMZERO_API_KEY")
        if not key:
            raise SchemaResolveError(
                "CRM Zero API key required. Provide 'api_key' in credentials "
                "or set CRMZERO_API_KEY environment variable."
            )
        return key

    async def resolve(
        self,
        object_type: str,
        credentials: dict,
        include_custom: bool = True,
    ) -> Schema:
        _api_key = self._get_api_key(credentials)

        # TODO: Replace with actual CRM Zero API call.
        # Expected implementation:
        #
        # url = f"https://api.crmzero.com/v1/schemas/{object_type}"
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(
        #         url, headers={"Authorization": f"Bearer {api_key}"}
        #     )
        # fields_data = response.json().get("fields", [])
        # return self._parse_fields(fields_data, object_type)

        raise SchemaResolveError(
            f"CRM Zero resolver not yet implemented. "
            f"Use static schema fallback (e.g. 'crm/crmzero_contact'). "
            f"Object type: {object_type}"
        )

    def _parse_fields(self, fields_data: list[dict[str, Any]], object_type: str) -> Schema:
        """Parse CRM Zero field definitions into a Schema."""
        fields: list[FieldDef] = []
        for f in fields_data:
            field_type = self.map_type(f.get("type", "string"))
            fields.append(
                FieldDef(
                    name=f["name"],
                    type=field_type,
                    description=f.get("label", ""),
                )
            )
        return Schema(
            name=f"CRMZero{object_type.title()}",
            fields=fields,
            description=f"Live schema from CRM Zero {object_type}",
        )
