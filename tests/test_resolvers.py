"""Tests for dynamic schema resolvers with mocked API responses."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from workflow_verify.ast.models import Effect, FieldDef, Schema, Step, Workflow
from workflow_verify.ast.types import WFType
from workflow_verify.resolvers import (
    SchemaResolveError,
    configure_cache,
    get_cache,
    get_resolver,
    list_resolvers,
    resolve_schema,
)
from workflow_verify.resolvers.cache import SchemaCache
from workflow_verify.resolvers.hubspot import HubSpotResolver
from workflow_verify.resolvers.salesforce import SalesforceResolver
from workflow_verify.resolvers.stripe import StripeResolver
from workflow_verify.verify.engine import verify

# --- Mock HTTP response helper ---


class MockResponse:
    """Minimal mock for httpx.Response."""

    def __init__(self, status_code: int, data: dict[str, Any]) -> None:
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self) -> dict[str, Any]:
        return self._data


# --- Resolver registry tests ---


class TestResolverRegistry:
    def test_list_resolvers(self):
        resolvers = list_resolvers()
        assert "hubspot" in resolvers
        assert "salesforce" in resolvers
        assert "postgres" in resolvers
        assert "clay" in resolvers
        assert "crmzero" in resolvers
        assert "stripe" in resolvers

    def test_get_resolver_hubspot(self):
        r = get_resolver("hubspot")
        assert isinstance(r, HubSpotResolver)
        assert r.service_name == "hubspot"

    def test_get_resolver_salesforce(self):
        r = get_resolver("salesforce")
        assert isinstance(r, SalesforceResolver)

    def test_get_resolver_unknown_raises(self):
        with pytest.raises(SchemaResolveError, match="No resolver"):
            get_resolver("nonexistent_service")

    def test_resolver_supported_objects(self):
        r = get_resolver("hubspot")
        objects = r.supported_objects()
        assert "contacts" in objects
        assert "deals" in objects

    def test_resolver_env_var_names(self):
        r = get_resolver("hubspot")
        env_vars = r.env_var_names()
        assert "HUBSPOT_API_KEY" in env_vars


# --- HubSpot resolver tests ---


class TestHubSpotResolver:
    """Test HubSpot resolver with mocked API responses."""

    MOCK_PROPERTIES = {
        "results": [
            {
                "name": "email",
                "type": "string",
                "fieldType": "email",
                "label": "Email",
                "hubspotDefined": True,
            },
            {
                "name": "firstname",
                "type": "string",
                "fieldType": "text",
                "label": "First Name",
                "hubspotDefined": True,
            },
            {
                "name": "phone",
                "type": "string",
                "fieldType": "phonenumber",
                "label": "Phone Number",
                "hubspotDefined": True,
            },
            {
                "name": "custom_lead_score",
                "type": "number",
                "fieldType": "number",
                "label": "Lead Score",
                "hubspotDefined": False,
            },
            {
                "name": "lifecyclestage",
                "type": "enumeration",
                "fieldType": "radio",
                "label": "Lifecycle Stage",
                "hubspotDefined": True,
            },
        ]
    }

    def test_resolve_contacts(self):
        resolver = HubSpotResolver()
        response = MockResponse(200, self.MOCK_PROPERTIES)

        with patch(
            "workflow_verify.resolvers.hubspot.http_get",
            new=AsyncMock(return_value=response),
        ):
            schema = asyncio.run(resolver.resolve("contacts", {"api_key": "test-key"}))

        assert schema.name == "HubSpotContacts"
        assert len(schema.fields) == 5
        email_field = next(f for f in schema.fields if f.name == "email")
        assert email_field.type == WFType.EMAIL
        phone_field = next(f for f in schema.fields if f.name == "phone")
        assert phone_field.type == WFType.PHONE
        custom_field = next(f for f in schema.fields if f.name == "custom_lead_score")
        assert "[custom]" in custom_field.description
        assert custom_field.type == WFType.FLOAT

    def test_resolve_without_custom(self):
        resolver = HubSpotResolver()
        response = MockResponse(200, self.MOCK_PROPERTIES)

        with patch(
            "workflow_verify.resolvers.hubspot.http_get",
            new=AsyncMock(return_value=response),
        ):
            schema = asyncio.run(
                resolver.resolve("contacts", {"api_key": "test-key"}, include_custom=False)
            )

        assert len(schema.fields) == 4
        assert not any(f.name == "custom_lead_score" for f in schema.fields)

    def test_auth_failure(self):
        resolver = HubSpotResolver()
        response = MockResponse(401, {"message": "Unauthorized"})

        with patch(
            "workflow_verify.resolvers.hubspot.http_get",
            new=AsyncMock(return_value=response),
        ):
            with pytest.raises(SchemaResolveError, match="authentication failed"):
                asyncio.run(resolver.resolve("contacts", {"api_key": "bad-key"}))

    def test_missing_credentials_raises(self):
        resolver = HubSpotResolver()
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(SchemaResolveError, match="credentials required"):
                asyncio.run(resolver.resolve("contacts", {}))


# --- Salesforce resolver tests ---


class TestSalesforceResolver:
    """Test Salesforce resolver with mocked API responses."""

    MOCK_DESCRIBE = {
        "name": "Lead",
        "fields": [
            {
                "name": "Id",
                "type": "id",
                "label": "Record ID",
                "custom": False,
            },
            {
                "name": "Email",
                "type": "email",
                "label": "Email",
                "custom": False,
            },
            {
                "name": "FirstName",
                "type": "string",
                "label": "First Name",
                "custom": False,
            },
            {
                "name": "Custom_Score__c",
                "type": "double",
                "label": "Custom Score",
                "custom": True,
            },
        ],
    }

    def test_resolve_lead(self):
        resolver = SalesforceResolver()
        response = MockResponse(200, self.MOCK_DESCRIBE)

        with patch(
            "workflow_verify.resolvers.salesforce.http_get",
            new=AsyncMock(return_value=response),
        ):
            schema = asyncio.run(
                resolver.resolve(
                    "Lead",
                    {
                        "access_token": "test-token",
                        "instance_url": "https://test.salesforce.com",
                    },
                )
            )

        assert schema.name == "SalesforceLead"
        assert len(schema.fields) == 4
        email_field = next(f for f in schema.fields if f.name == "Email")
        assert email_field.type == WFType.EMAIL
        custom_field = next(f for f in schema.fields if f.name == "Custom_Score__c")
        assert custom_field.type == WFType.FLOAT
        assert "[custom]" in custom_field.description

    def test_missing_instance_url_raises(self):
        resolver = SalesforceResolver()
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(SchemaResolveError, match="instance_url"):
                asyncio.run(resolver.resolve("Lead", {"access_token": "token"}))


# --- Stripe resolver tests ---


class TestStripeResolver:
    """Test Stripe resolver."""

    def test_resolve_customer_base_fields(self):
        resolver = StripeResolver()
        # No API call needed for base fields — Stripe uses known schemas
        schema = asyncio.run(
            resolver.resolve("customer", {"api_key": "sk_test_xxx"}, include_custom=False)
        )

        assert schema.name == "StripeCustomer"
        assert len(schema.fields) > 0
        email_field = next(f for f in schema.fields if f.name == "email")
        assert email_field.type == WFType.EMAIL

    def test_resolve_unknown_object_raises(self):
        resolver = StripeResolver()
        with pytest.raises(SchemaResolveError, match="not supported"):
            asyncio.run(resolver.resolve("widget", {"api_key": "sk_test_xxx"}))

    def test_supported_objects(self):
        resolver = StripeResolver()
        objects = resolver.supported_objects()
        assert "customer" in objects
        assert "charge" in objects
        assert "subscription" in objects
        assert "invoice" in objects


# --- Clay/CRMZero stub tests ---


class TestStubResolvers:
    """Test that stub resolvers raise clearly."""

    def test_clay_raises_not_implemented(self):
        resolver = get_resolver("clay")
        with pytest.raises(SchemaResolveError, match="not yet implemented"):
            asyncio.run(resolver.resolve("tbl_123", {"api_key": "test"}))

    def test_crmzero_raises_not_implemented(self):
        resolver = get_resolver("crmzero")
        with pytest.raises(SchemaResolveError, match="not yet implemented"):
            asyncio.run(resolver.resolve("contacts", {"api_key": "test"}))

    def test_clay_type_map(self):
        resolver = get_resolver("clay")
        assert resolver.map_type("email") == WFType.EMAIL
        assert resolver.map_type("number") == WFType.FLOAT
        assert resolver.map_type("url") == WFType.URL

    def test_crmzero_type_map(self):
        resolver = get_resolver("crmzero")
        assert resolver.map_type("email") == WFType.EMAIL
        assert resolver.map_type("integer") == WFType.INT


# --- SchemaCache tests ---


class TestSchemaCache:
    """Test TTL-based schema caching."""

    def test_set_and_get(self):
        cache = SchemaCache(ttl_seconds=60)
        schema = Schema(
            name="Test",
            fields=[FieldDef(name="x", type=WFType.TEXT)],
        )
        cache.set("svc", "obj", {"key": "val"}, schema)
        result = cache.get("svc", "obj", {"key": "val"})
        assert result is not None
        assert result.name == "Test"

    def test_cache_miss(self):
        cache = SchemaCache()
        result = cache.get("svc", "missing", {})
        assert result is None

    def test_ttl_expiration(self):
        cache = SchemaCache(ttl_seconds=0)  # Immediate expiry
        schema = Schema(name="Exp", fields=[FieldDef(name="x", type=WFType.TEXT)])
        cache.set("svc", "obj", {}, schema)
        time.sleep(0.01)
        result = cache.get("svc", "obj", {})
        assert result is None

    def test_invalidate_all(self):
        cache = SchemaCache()
        schema = Schema(name="T", fields=[FieldDef(name="x", type=WFType.TEXT)])
        cache.set("a", "1", {}, schema)
        cache.set("b", "2", {}, schema)
        assert cache.size == 2
        cache.invalidate()
        assert cache.size == 0

    def test_invalidate_service(self):
        cache = SchemaCache()
        schema = Schema(name="T", fields=[FieldDef(name="x", type=WFType.TEXT)])
        cache.set("hubspot", "contacts", {}, schema)
        cache.set("hubspot", "deals", {}, schema)
        cache.set("salesforce", "Lead", {}, schema)
        assert cache.size == 3
        cache.invalidate_service("hubspot")
        assert cache.size == 1

    def test_different_credentials_different_keys(self):
        cache = SchemaCache()
        schema1 = Schema(name="A", fields=[FieldDef(name="x", type=WFType.TEXT)])
        schema2 = Schema(name="B", fields=[FieldDef(name="y", type=WFType.INT)])
        cache.set("svc", "obj", {"key": "one"}, schema1)
        cache.set("svc", "obj", {"key": "two"}, schema2)
        r1 = cache.get("svc", "obj", {"key": "one"})
        r2 = cache.get("svc", "obj", {"key": "two"})
        assert r1.name == "A"
        assert r2.name == "B"


# --- Unified resolve_schema tests ---


class TestResolveSchema:
    """Test the unified resolve_schema API."""

    def test_fallback_to_static_hubspot(self):
        """When dynamic fails, should fall back to static YAML."""
        # Reset cache
        configure_cache(ttl_seconds=300)
        get_cache().invalidate()

        schema = asyncio.run(
            resolve_schema(
                "hubspot",
                "contacts",
                credentials={},
                fallback_to_static=True,
                use_cache=False,
            )
        )

        # Should get the static hubspot_contact.yaml
        assert schema.name == "HubSpotContact"
        assert len(schema.fields) > 0

    def test_fallback_to_static_salesforce(self):
        configure_cache(ttl_seconds=300)
        get_cache().invalidate()

        schema = asyncio.run(
            resolve_schema(
                "salesforce",
                "Lead",
                credentials={},
                fallback_to_static=True,
                use_cache=False,
            )
        )

        assert schema.name == "SalesforceLead"

    def test_no_fallback_raises(self):
        """Without fallback, missing credentials should raise."""
        configure_cache(ttl_seconds=300)
        get_cache().invalidate()

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(SchemaResolveError):
                asyncio.run(
                    resolve_schema(
                        "hubspot",
                        "contacts",
                        credentials={},
                        fallback_to_static=False,
                        use_cache=False,
                    )
                )

    def test_cache_is_used(self):
        """Second call should use cache."""
        configure_cache(ttl_seconds=300)
        get_cache().invalidate()

        schema = Schema(
            name="Cached",
            fields=[FieldDef(name="x", type=WFType.TEXT)],
        )
        get_cache().set("hubspot", "contacts", {}, schema)

        result = asyncio.run(
            resolve_schema(
                "hubspot",
                "contacts",
                credentials={},
                use_cache=True,
            )
        )

        assert result.name == "Cached"

    def test_stripe_resolves_without_api_call(self):
        """Stripe resolver works with known schemas even without API."""
        configure_cache(ttl_seconds=300)
        get_cache().invalidate()

        schema = asyncio.run(
            resolve_schema(
                "stripe",
                "customer",
                credentials={"api_key": "sk_test_xxx"},
                use_cache=False,
            )
        )

        assert schema.name == "StripeCustomer"
        assert any(f.name == "email" for f in schema.fields)


# --- Integration: resolved schemas in verification ---


class TestResolvedSchemaVerification:
    """Verify that dynamically resolved schemas work through the verification engine."""

    def test_static_and_resolved_verify_identically(self):
        """A workflow using a static schema and one using an identical
        dynamically-resolved schema should both pass verification."""
        from workflow_verify.registry.loader import load_schema

        static_lead = load_schema("crm/salesforce_lead")

        # Build a simple workflow with the static schema
        result_schema = Schema(
            name="ProcessResult",
            fields=[
                FieldDef(name="id", type=WFType.TEXT),
                FieldDef(name="processed", type=WFType.BOOL),
            ],
        )

        wf = Workflow(
            name="Static Test",
            schemas=[static_lead, result_schema],
            steps=[
                Step(
                    name="process",
                    input_schema="SalesforceLead",
                    output_schema="ProcessResult",
                    effects=[Effect(kind="read", target="salesforce")],
                ),
            ],
            input_schema="SalesforceLead",
            output_schema="ProcessResult",
        )

        result = verify(wf)
        assert result.passed, f"Static schema workflow failed: {[e.message for e in result.errors]}"

        # Now build the same workflow but with a "resolved" schema
        # (same fields, different source)
        resolved_lead = Schema(
            name="SalesforceLead",
            fields=static_lead.fields,
            description="Dynamically resolved from Salesforce describe API",
        )

        wf2 = Workflow(
            name="Resolved Test",
            schemas=[resolved_lead, result_schema],
            steps=[
                Step(
                    name="process",
                    input_schema="SalesforceLead",
                    output_schema="ProcessResult",
                    effects=[Effect(kind="read", target="salesforce")],
                ),
            ],
            input_schema="SalesforceLead",
            output_schema="ProcessResult",
        )

        result2 = verify(wf2)
        assert result2.passed, (
            f"Resolved schema workflow failed: {[e.message for e in result2.errors]}"
        )

    def test_resolved_schema_with_custom_fields(self):
        """A workflow that uses custom fields only available via dynamic resolution."""
        custom_schema = Schema(
            name="HubSpotContacts",
            fields=[
                FieldDef(name="email", type=WFType.EMAIL),
                FieldDef(name="firstname", type=WFType.TEXT),
                FieldDef(name="custom_lead_score", type=WFType.FLOAT),
            ],
            description="Live schema with custom fields",
        )

        scored = Schema(
            name="ScoredContact",
            fields=[
                FieldDef(name="email", type=WFType.EMAIL),
                FieldDef(name="score", type=WFType.FLOAT),
            ],
        )

        wf = Workflow(
            name="Custom Field Pipeline",
            schemas=[custom_schema, scored],
            steps=[
                Step(
                    name="score_contacts",
                    description="Score contacts using custom_lead_score",
                    input_schema="HubSpotContacts",
                    output_schema="ScoredContact",
                ),
            ],
            input_schema="HubSpotContacts",
            output_schema="ScoredContact",
        )

        result = verify(wf)
        assert result.passed
