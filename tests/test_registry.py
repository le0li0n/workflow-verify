"""Tests for the schema registry."""

import json
from pathlib import Path

import pytest

from workflow_verify.ast.models import Schema, Workflow
from workflow_verify.ast.types import WFType
from workflow_verify.registry import (
    SchemaLoadError,
    list_categories,
    list_schemas,
    load_schema,
    search_schemas,
)
from workflow_verify.verify.engine import verify

FIXTURES = Path(__file__).parent / "fixtures"


# --- load_schema tests ---


class TestLoadSchema:
    """Test loading individual schemas from the registry."""

    def test_load_salesforce_lead(self):
        schema = load_schema("crm/salesforce_lead")
        assert schema.name == "SalesforceLead"
        assert len(schema.fields) > 0
        assert any(f.name == "email" for f in schema.fields)

    def test_load_hubspot_contact(self):
        schema = load_schema("crm/hubspot_contact")
        assert schema.name == "HubSpotContact"

    def test_load_clearbit_person(self):
        schema = load_schema("enrichment/clearbit_person")
        assert schema.name == "ClearbitPerson"
        email_field = next(f for f in schema.fields if f.name == "email")
        assert email_field.type == WFType.EMAIL

    def test_load_common_person(self):
        schema = load_schema("common/person")
        assert schema.name == "Person"

    def test_load_common_money(self):
        schema = load_schema("common/money")
        assert schema.name == "Money"
        amount_field = next(f for f in schema.fields if f.name == "amount")
        assert amount_field.type == WFType.FLOAT

    def test_load_stripe_customer(self):
        schema = load_schema("data/stripe_customer")
        assert schema.name == "StripeCustomer"

    def test_load_slack_message(self):
        schema = load_schema("communication/slack_message")
        assert schema.name == "SlackMessage"

    def test_load_nonexistent_raises(self):
        with pytest.raises(SchemaLoadError, match="not found"):
            load_schema("crm/nonexistent_crm")

    def test_loaded_schema_is_pydantic_model(self):
        schema = load_schema("crm/salesforce_lead")
        assert isinstance(schema, Schema)
        # Should be serializable
        json_str = schema.model_dump_json()
        assert "SalesforceLead" in json_str

    def test_field_types_are_valid(self):
        """All loaded fields should have valid WFType values."""
        for path in list_schemas():
            schema = load_schema(path)
            for field in schema.fields:
                assert isinstance(field.type, WFType), (
                    f"Field '{field.name}' in '{path}' has invalid type: {field.type}"
                )

    def test_validate_expressions_preserved(self):
        """Fields with validate expressions should preserve them."""
        schema = load_schema("crm/salesforce_lead")
        email_field = next(f for f in schema.fields if f.name == "email")
        assert email_field.validate_expr is not None
        assert "value" in email_field.validate_expr


# --- list_schemas tests ---


class TestListSchemas:
    """Test listing schemas by category."""

    def test_list_all_schemas(self):
        all_schemas = list_schemas()
        assert len(all_schemas) >= 15  # Acceptance criteria: at least 15

    def test_list_crm_schemas(self):
        crm = list_schemas("crm")
        assert len(crm) == 6
        assert "crm/salesforce_lead" in crm
        assert "crm/hubspot_contact" in crm
        assert "crm/crmzero_contact" in crm

    def test_list_enrichment_schemas(self):
        enrichment = list_schemas("enrichment")
        assert len(enrichment) == 4
        assert "enrichment/clearbit_person" in enrichment

    def test_list_communication_schemas(self):
        comm = list_schemas("communication")
        assert len(comm) == 3

    def test_list_data_schemas(self):
        data = list_schemas("data")
        assert len(data) == 3

    def test_list_common_schemas(self):
        common = list_schemas("common")
        assert len(common) == 4

    def test_list_nonexistent_category(self):
        result = list_schemas("nonexistent")
        assert result == []

    def test_list_categories(self):
        cats = list_categories()
        assert "crm" in cats
        assert "enrichment" in cats
        assert "communication" in cats
        assert "data" in cats
        assert "common" in cats


# --- search_schemas tests ---


class TestSearchSchemas:
    """Test searching schemas by keyword."""

    def test_search_email(self):
        results = search_schemas("email")
        assert len(results) > 0
        # Should find schemas with email fields
        names = [s.name for s in results]
        assert "EmailMessage" in names

    def test_search_salesforce(self):
        results = search_schemas("salesforce")
        assert len(results) >= 3  # lead, contact, opportunity
        names = [s.name for s in results]
        assert "SalesforceLead" in names

    def test_search_stripe(self):
        results = search_schemas("stripe")
        assert len(results) >= 1
        assert any(s.name == "StripeCustomer" for s in results)

    def test_search_case_insensitive(self):
        results_lower = search_schemas("hubspot")
        results_upper = search_schemas("HubSpot")
        assert len(results_lower) == len(results_upper)

    def test_search_by_field_name(self):
        results = search_schemas("linkedin")
        assert len(results) > 0

    def test_search_no_results(self):
        results = search_schemas("xyznonexistent")
        assert results == []

    def test_search_returns_schema_models(self):
        results = search_schemas("person")
        assert all(isinstance(s, Schema) for s in results)


# --- Validation tests ---


class TestSchemaValidation:
    """Test that invalid YAML schemas are caught on load."""

    def test_all_registry_schemas_load_successfully(self):
        """Every YAML file in the registry should load without error."""
        for path in list_schemas():
            schema = load_schema(path)
            assert schema.name, f"Schema at {path} has empty name"
            assert len(schema.fields) > 0, f"Schema at {path} has no fields"


# --- Integration test: registry schemas in a workflow ---


class TestRegistryInWorkflow:
    """Test that registry schemas can be used in workflow verification."""

    def test_crm_pipeline_with_registry_schemas(self):
        """Build a workflow using registry schemas and verify it passes."""
        lead = load_schema("crm/salesforce_lead")
        clearbit = load_schema("enrichment/clearbit_person")
        email = load_schema("communication/email_message")

        # Build a simple pipeline: fetch lead -> enrich -> send email
        # We need output schemas that are compatible with the next step's input

        from workflow_verify.ast.models import Effect, FieldDef, Step
        from workflow_verify.ast.types import WFType

        # Create a scored lead schema that bridges enrichment to email
        scored = Schema(
            name="ScoredLead",
            fields=[
                FieldDef(name="email", type=WFType.EMAIL),
                FieldDef(name="full_name", type=WFType.TEXT),
                FieldDef(name="company_name", type=WFType.TEXT),
                FieldDef(name="score", type=WFType.INT),
            ],
        )

        # Create an email result schema
        email_result = Schema(
            name="EmailResult",
            fields=[
                FieldDef(name="to", type=WFType.EMAIL),
                FieldDef(name="sent", type=WFType.BOOL),
            ],
        )

        workflow = Workflow(
            name="Registry CRM Pipeline",
            schemas=[lead, clearbit, scored, email_result],
            steps=[
                Step(
                    name="fetch_leads",
                    description="Fetch leads from Salesforce",
                    input_schema=None,
                    output_schema="SalesforceLead",
                    effects=[Effect(kind="read", target="salesforce")],
                ),
                Step(
                    name="enrich",
                    description="Enrich with Clearbit",
                    input_schema="SalesforceLead",
                    output_schema="ClearbitPerson",
                    effects=[Effect(kind="call", target="clearbit")],
                ),
                Step(
                    name="score",
                    description="Score the lead",
                    input_schema="ClearbitPerson",
                    output_schema="ScoredLead",
                ),
                Step(
                    name="send_outreach",
                    description="Send outreach email",
                    input_schema="ScoredLead",
                    output_schema="EmailResult",
                    effects=[Effect(kind="send", target="email")],
                ),
            ],
            input_schema="SalesforceLead",
            output_schema="EmailResult",
        )

        result = verify(workflow)
        assert result.passed, (
            f"Workflow with registry schemas failed: "
            f"{[e.message for e in result.errors]}"
        )
        assert len(result.effects_manifest) == 3
