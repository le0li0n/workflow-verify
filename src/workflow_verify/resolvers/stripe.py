"""Stripe metadata resolver."""

from __future__ import annotations

import os

from workflow_verify.ast.models import FieldDef, Schema
from workflow_verify.ast.types import WFType
from workflow_verify.resolvers.base import SchemaResolveError, SchemaResolver

STRIPE_TYPE_MAP: dict[str, WFType] = {
    "string": WFType.TEXT,
    "number": WFType.FLOAT,
    "integer": WFType.INT,
    "boolean": WFType.BOOL,
    "hash": WFType.JSON,
    "array": WFType.JSON,
}

# Known Stripe object fields (Stripe doesn't have a describe API,
# but object shapes are well-documented)
_STRIPE_OBJECTS: dict[str, list[tuple[str, WFType, str]]] = {
    "customer": [
        ("id", WFType.TEXT, "Stripe customer ID (cus_...)"),
        ("email", WFType.EMAIL, "Customer email"),
        ("name", WFType.TEXT, "Customer name"),
        ("phone", WFType.PHONE, "Customer phone"),
        ("currency", WFType.TEXT, "Default currency"),
        ("created", WFType.DATETIME, "Creation timestamp"),
        ("balance", WFType.INT, "Balance in smallest currency unit"),
        ("default_source", WFType.TEXT, "Default payment source ID"),
        ("metadata", WFType.JSON, "Arbitrary key-value metadata"),
    ],
    "charge": [
        ("id", WFType.TEXT, "Stripe charge ID (ch_...)"),
        ("amount", WFType.INT, "Amount in smallest currency unit"),
        ("currency", WFType.TEXT, "Three-letter ISO currency code"),
        ("status", WFType.TEXT, "Charge status (succeeded, pending, failed)"),
        ("customer", WFType.TEXT, "Customer ID"),
        ("description", WFType.TEXT, "Charge description"),
        ("created", WFType.DATETIME, "Creation timestamp"),
        ("metadata", WFType.JSON, "Arbitrary key-value metadata"),
    ],
    "subscription": [
        ("id", WFType.TEXT, "Stripe subscription ID (sub_...)"),
        ("customer", WFType.TEXT, "Customer ID"),
        ("status", WFType.TEXT, "Subscription status"),
        ("current_period_start", WFType.DATETIME, "Current period start"),
        ("current_period_end", WFType.DATETIME, "Current period end"),
        ("cancel_at_period_end", WFType.BOOL, "Cancel at period end"),
        ("created", WFType.DATETIME, "Creation timestamp"),
        ("metadata", WFType.JSON, "Arbitrary key-value metadata"),
    ],
    "invoice": [
        ("id", WFType.TEXT, "Stripe invoice ID (in_...)"),
        ("customer", WFType.TEXT, "Customer ID"),
        ("amount_due", WFType.INT, "Amount due"),
        ("amount_paid", WFType.INT, "Amount paid"),
        ("currency", WFType.TEXT, "Currency"),
        ("status", WFType.TEXT, "Invoice status"),
        ("due_date", WFType.DATE, "Due date"),
        ("created", WFType.DATETIME, "Creation timestamp"),
        ("metadata", WFType.JSON, "Arbitrary key-value metadata"),
    ],
}


class StripeResolver(SchemaResolver):
    """Resolves schemas for Stripe objects.

    Stripe doesn't have a describe/metadata API like Salesforce or HubSpot.
    This resolver uses known object shapes and optionally fetches a sample
    object to discover metadata keys.
    """

    service_name = "stripe"

    def supported_objects(self) -> list[str]:
        return list(_STRIPE_OBJECTS.keys())

    def env_var_names(self) -> list[str]:
        return ["STRIPE_API_KEY"]

    def map_type(self, service_type: str) -> WFType:
        return STRIPE_TYPE_MAP.get(service_type.lower(), WFType.TEXT)

    def _get_api_key(self, credentials: dict) -> str:
        key = credentials.get("api_key")
        if not key:
            key = os.environ.get("STRIPE_API_KEY")
        if not key:
            raise SchemaResolveError(
                "Stripe API key required. Provide 'api_key' in credentials "
                "or set STRIPE_API_KEY environment variable."
            )
        return key

    async def resolve(
        self,
        object_type: str,
        credentials: dict,
        include_custom: bool = True,
    ) -> Schema:
        object_type_lower = object_type.lower()
        if object_type_lower not in _STRIPE_OBJECTS:
            raise SchemaResolveError(
                f"Stripe object '{object_type}' not supported. "
                f"Available: {', '.join(self.supported_objects())}"
            )

        # Build base schema from known fields
        known_fields = _STRIPE_OBJECTS[object_type_lower]
        fields = [
            FieldDef(name=name, type=wf_type, description=desc)
            for name, wf_type, desc in known_fields
        ]

        # Optionally fetch a sample object to discover metadata keys
        if include_custom:
            try:
                api_key = self._get_api_key(credentials)
                metadata_fields = await self._discover_metadata(api_key, object_type_lower)
                fields.extend(metadata_fields)
            except SchemaResolveError:
                pass  # Proceed with base fields only

        return Schema(
            name=f"Stripe{object_type.title()}",
            fields=fields,
            description=f"Stripe {object_type} schema",
        )

    async def _discover_metadata(self, api_key: str, object_type: str) -> list[FieldDef]:
        """Fetch a sample object to discover metadata keys."""
        try:
            import httpx
        except ImportError:
            return []

        url_map = {
            "customer": "https://api.stripe.com/v1/customers",
            "charge": "https://api.stripe.com/v1/charges",
            "subscription": "https://api.stripe.com/v1/subscriptions",
            "invoice": "https://api.stripe.com/v1/invoices",
        }

        url = url_map.get(object_type)
        if not url:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"limit": "1"},
                auth=(api_key, ""),
            )

        if response.status_code != 200:
            return []

        data = response.json().get("data", [])
        if not data:
            return []

        metadata = data[0].get("metadata", {})
        return [
            FieldDef(
                name=f"metadata_{key}",
                type=WFType.TEXT,
                description=f"[metadata] {key}",
            )
            for key in metadata
        ]
