"""Salesforce describe API resolver."""

from __future__ import annotations

import os
from typing import Any

from workflow_verify.ast.models import FieldDef, Schema
from workflow_verify.ast.types import WFType
from workflow_verify.resolvers.base import SchemaResolveError, SchemaResolver, http_get

SALESFORCE_TYPE_MAP: dict[str, WFType] = {
    "string": WFType.TEXT,
    "email": WFType.EMAIL,
    "phone": WFType.PHONE,
    "url": WFType.URL,
    "int": WFType.INT,
    "double": WFType.FLOAT,
    "currency": WFType.FLOAT,
    "percent": WFType.FLOAT,
    "boolean": WFType.BOOL,
    "date": WFType.DATE,
    "datetime": WFType.DATETIME,
    "id": WFType.TEXT,
    "reference": WFType.TEXT,
    "picklist": WFType.TEXT,
    "multipicklist": WFType.TEXT,
    "textarea": WFType.TEXT,
    "encryptedstring": WFType.TEXT,
    "combobox": WFType.TEXT,
    "base64": WFType.TEXT,
    "address": WFType.JSON,
    "location": WFType.JSON,
}


class SalesforceResolver(SchemaResolver):
    """Resolves schemas from Salesforce describe API.

    Hits GET /services/data/vXX.0/sobjects/{object_type}/describe/ to
    discover all fields including custom __c fields.
    """

    service_name = "salesforce"

    def supported_objects(self) -> list[str]:
        return [
            "Lead",
            "Contact",
            "Account",
            "Opportunity",
            "Case",
            "Task",
            "Event",
        ]

    def env_var_names(self) -> list[str]:
        return ["SALESFORCE_ACCESS_TOKEN", "SALESFORCE_INSTANCE_URL"]

    def map_type(self, service_type: str) -> WFType:
        return SALESFORCE_TYPE_MAP.get(service_type.lower(), WFType.TEXT)

    def _get_credentials(self, credentials: dict) -> tuple[str, str]:
        token = credentials.get("access_token") or os.environ.get(
            "SALESFORCE_ACCESS_TOKEN"
        )
        instance_url = credentials.get("instance_url") or os.environ.get(
            "SALESFORCE_INSTANCE_URL"
        )
        if not token:
            raise SchemaResolveError(
                "Salesforce access_token required. Provide in credentials "
                "or set SALESFORCE_ACCESS_TOKEN environment variable."
            )
        if not instance_url:
            raise SchemaResolveError(
                "Salesforce instance_url required. Provide in credentials "
                "or set SALESFORCE_INSTANCE_URL environment variable."
            )
        return token, instance_url.rstrip("/")

    async def resolve(
        self,
        object_type: str,
        credentials: dict,
        include_custom: bool = True,
    ) -> Schema:
        token, instance_url = self._get_credentials(credentials)
        url = f"{instance_url}/services/data/v59.0/sobjects/{object_type}/describe/"

        response = await http_get(
            url, headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code == 401:
            raise SchemaResolveError(
                "Salesforce authentication failed. Check your access token."
            )
        if response.status_code == 404:
            raise SchemaResolveError(
                f"Salesforce object '{object_type}' not found. "
                f"Common objects: {', '.join(self.supported_objects())}"
            )
        if response.status_code != 200:
            raise SchemaResolveError(
                f"Salesforce API error {response.status_code}: {response.text}"
            )

        data = response.json()
        return self._parse_describe(data, object_type, include_custom)

    def _parse_describe(
        self, data: dict[str, Any], object_type: str, include_custom: bool
    ) -> Schema:
        sf_fields = data.get("fields", [])
        fields: list[FieldDef] = []

        for sf_field in sf_fields:
            is_custom = sf_field.get("custom", False)
            if not include_custom and is_custom:
                continue

            field_type = self.map_type(sf_field.get("type", "string"))

            description = sf_field.get("label", "")
            if is_custom:
                description = f"[custom] {description}"

            name = sf_field.get("name", "")
            fields.append(
                FieldDef(
                    name=name,
                    type=field_type,
                    description=description,
                )
            )

        return Schema(
            name=f"Salesforce{object_type}",
            fields=fields,
            description=f"Live schema from Salesforce {object_type} describe API",
        )
