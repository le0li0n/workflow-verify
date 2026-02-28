"""HubSpot properties API resolver."""

from __future__ import annotations

import os
from typing import Any

from workflow_verify.ast.models import FieldDef, Schema
from workflow_verify.ast.types import WFType
from workflow_verify.resolvers.base import SchemaResolveError, SchemaResolver, http_get

HUBSPOT_TYPE_MAP: dict[str, WFType] = {
    "string": WFType.TEXT,
    "number": WFType.FLOAT,
    "date": WFType.DATE,
    "datetime": WFType.DATETIME,
    "enumeration": WFType.TEXT,
    "bool": WFType.BOOL,
    "phone_number": WFType.PHONE,
}


class HubSpotResolver(SchemaResolver):
    """Resolves schemas from HubSpot CRM properties API.

    Hits GET /crm/v3/properties/{object_type} to discover all properties
    including custom ones.
    """

    service_name = "hubspot"

    def supported_objects(self) -> list[str]:
        return ["contacts", "companies", "deals", "tickets"]

    def env_var_names(self) -> list[str]:
        return ["HUBSPOT_API_KEY", "HUBSPOT_ACCESS_TOKEN"]

    def map_type(self, service_type: str) -> WFType:
        return HUBSPOT_TYPE_MAP.get(service_type.lower(), WFType.TEXT)

    def _get_token(self, credentials: dict) -> str:
        token = credentials.get("api_key") or credentials.get("access_token")
        if not token:
            token = os.environ.get("HUBSPOT_API_KEY") or os.environ.get("HUBSPOT_ACCESS_TOKEN")
        if not token:
            raise SchemaResolveError(
                "HubSpot credentials required. Provide 'api_key' or "
                "'access_token' in credentials, or set HUBSPOT_API_KEY "
                "or HUBSPOT_ACCESS_TOKEN environment variable."
            )
        return token

    async def resolve(
        self,
        object_type: str,
        credentials: dict,
        include_custom: bool = True,
    ) -> Schema:
        token = self._get_token(credentials)
        url = f"https://api.hubapi.com/crm/v3/properties/{object_type}"

        response = await http_get(url, headers={"Authorization": f"Bearer {token}"})

        if response.status_code == 401:
            raise SchemaResolveError(
                "HubSpot authentication failed. Check your API key or access token."
            )
        if response.status_code == 404:
            raise SchemaResolveError(
                f"HubSpot object type '{object_type}' not found. "
                f"Available: {', '.join(self.supported_objects())}"
            )
        if response.status_code != 200:
            raise SchemaResolveError(f"HubSpot API error {response.status_code}: {response.text}")

        data = response.json()
        return self._parse_properties(data, object_type, include_custom)

    def _parse_properties(
        self, data: dict[str, Any], object_type: str, include_custom: bool
    ) -> Schema:
        results = data.get("results", [])
        fields: list[FieldDef] = []

        for prop in results:
            is_custom = not prop.get("hubspotDefined", True)
            if not include_custom and is_custom:
                continue

            field_type = self.map_type(prop.get("type", "string"))
            # HubSpot marks some fields as "email" in fieldType
            if prop.get("fieldType") == "email":
                field_type = WFType.EMAIL
            elif prop.get("fieldType") == "phonenumber":
                field_type = WFType.PHONE

            description = prop.get("label", "")
            if is_custom:
                description = f"[custom] {description}"

            fields.append(
                FieldDef(
                    name=prop["name"],
                    type=field_type,
                    description=description,
                )
            )

        schema_name = f"HubSpot{object_type.title().replace(' ', '')}"
        return Schema(
            name=schema_name,
            fields=fields,
            description=f"Live schema from HubSpot {object_type} properties API",
        )
