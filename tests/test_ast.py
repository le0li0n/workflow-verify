"""Tests for AST models, type system, and JSON schema export."""

import json
from pathlib import Path

from workflow_verify.ast.models import (
    Effect,
    FieldDef,
    Guard,
    Schema,
    Step,
    Workflow,
)
from workflow_verify.ast.schema import (
    get_workflow_json_schema,
    get_workflow_tool_definition,
)
from workflow_verify.ast.types import (
    ListType,
    OptionalType,
    RecordField,
    RecordType,
    WFType,
    is_compatible,
)

FIXTURES = Path(__file__).parent / "fixtures"


# --- Type compatibility tests ---


class TestTypeCompatibility:
    """Test the is_compatible function against all documented rules."""

    def test_identical_types(self):
        assert is_compatible(WFType.TEXT, WFType.TEXT)
        assert is_compatible(WFType.INT, WFType.INT)
        assert is_compatible(WFType.BOOL, WFType.BOOL)

    def test_email_is_subtype_of_text(self):
        assert is_compatible(WFType.EMAIL, WFType.TEXT)
        assert not is_compatible(WFType.TEXT, WFType.EMAIL)

    def test_url_is_subtype_of_text(self):
        assert is_compatible(WFType.URL, WFType.TEXT)
        assert not is_compatible(WFType.TEXT, WFType.URL)

    def test_phone_is_subtype_of_text(self):
        assert is_compatible(WFType.PHONE, WFType.TEXT)
        assert not is_compatible(WFType.TEXT, WFType.PHONE)

    def test_date_is_subtype_of_text(self):
        assert is_compatible(WFType.DATE, WFType.TEXT)

    def test_datetime_is_subtype_of_text(self):
        assert is_compatible(WFType.DATETIME, WFType.TEXT)

    def test_int_is_subtype_of_float(self):
        assert is_compatible(WFType.INT, WFType.FLOAT)
        assert not is_compatible(WFType.FLOAT, WFType.INT)

    def test_any_is_universal(self):
        for t in WFType:
            assert is_compatible(WFType.ANY, t)
            assert is_compatible(t, WFType.ANY)

    def test_incompatible_scalars(self):
        assert not is_compatible(WFType.BOOL, WFType.INT)
        assert not is_compatible(WFType.TEXT, WFType.INT)
        assert not is_compatible(WFType.EMAIL, WFType.URL)

    def test_optional_to_required(self):
        """Optional[T] -> T is allowed (caller guarantees presence)."""
        opt_email = OptionalType(inner=WFType.EMAIL)
        assert is_compatible(opt_email, WFType.EMAIL)
        assert is_compatible(opt_email, WFType.TEXT)  # Email -> Text still holds

    def test_required_to_optional(self):
        """T -> Optional[T] is fine (value is present)."""
        opt_text = OptionalType(inner=WFType.TEXT)
        assert is_compatible(WFType.TEXT, opt_text)
        assert is_compatible(WFType.EMAIL, opt_text)  # Email -> Optional[Text]

    def test_optional_to_optional(self):
        opt_email = OptionalType(inner=WFType.EMAIL)
        opt_text = OptionalType(inner=WFType.TEXT)
        assert is_compatible(opt_email, opt_text)
        assert not is_compatible(opt_text, opt_email)

    def test_list_invariance(self):
        list_text = ListType(element=WFType.TEXT)
        list_email = ListType(element=WFType.EMAIL)
        list_int = ListType(element=WFType.INT)

        assert is_compatible(list_text, list_text)
        # Email is subtype of Text, so List[Email] is compatible with List[Text]
        assert is_compatible(list_email, list_text)
        assert not is_compatible(list_text, list_email)
        assert not is_compatible(list_int, list_text)

    def test_list_vs_scalar(self):
        assert not is_compatible(ListType(element=WFType.TEXT), WFType.TEXT)
        assert not is_compatible(WFType.TEXT, ListType(element=WFType.TEXT))

    def test_record_structural_subtyping(self):
        """Source record has all target's required fields with compatible types."""
        source = RecordType(
            name="Full",
            fields=[
                RecordField(name="email", type=WFType.EMAIL),
                RecordField(name="name", type=WFType.TEXT),
                RecordField(name="age", type=WFType.INT),
            ],
        )
        target = RecordType(
            name="Partial",
            fields=[
                RecordField(name="email", type=WFType.TEXT),  # Email -> Text ok
                RecordField(name="name", type=WFType.TEXT),
            ],
        )
        assert is_compatible(source, target)

    def test_record_missing_field(self):
        source = RecordType(
            name="Incomplete",
            fields=[
                RecordField(name="name", type=WFType.TEXT),
            ],
        )
        target = RecordType(
            name="NeedsEmail",
            fields=[
                RecordField(name="name", type=WFType.TEXT),
                RecordField(name="email", type=WFType.EMAIL),
            ],
        )
        assert not is_compatible(source, target)

    def test_record_optional_field_not_required(self):
        """Optional fields in target don't need to exist in source."""
        source = RecordType(
            name="Minimal",
            fields=[
                RecordField(name="name", type=WFType.TEXT),
            ],
        )
        target = RecordType(
            name="WithOptional",
            fields=[
                RecordField(name="name", type=WFType.TEXT),
                RecordField(name="nickname", type=WFType.TEXT, required=False),
            ],
        )
        assert is_compatible(source, target)

    def test_record_incompatible_field_type(self):
        source = RecordType(
            name="A",
            fields=[
                RecordField(name="count", type=WFType.TEXT),
            ],
        )
        target = RecordType(
            name="B",
            fields=[
                RecordField(name="count", type=WFType.INT),
            ],
        )
        assert not is_compatible(source, target)


# --- AST model tests ---


class TestASTModels:
    """Test Pydantic model construction and serialization."""

    def test_field_def_with_scalar_type(self):
        f = FieldDef(name="email", type=WFType.EMAIL, description="User email")
        assert f.name == "email"
        assert f.type == WFType.EMAIL

    def test_field_def_with_list_type(self):
        f = FieldDef(name="tags", type=ListType(element=WFType.TEXT))
        assert isinstance(f.type, ListType)

    def test_field_def_with_optional_type(self):
        f = FieldDef(name="phone", type=OptionalType(inner=WFType.PHONE))
        assert isinstance(f.type, OptionalType)

    def test_schema_model(self):
        s = Schema(
            name="Lead",
            fields=[
                FieldDef(name="email", type=WFType.EMAIL),
                FieldDef(name="name", type=WFType.TEXT),
            ],
        )
        assert len(s.fields) == 2

    def test_effect_model(self):
        e = Effect(kind="write", target="salesforce", description="Write to SF")
        assert e.kind == "write"

    def test_guard_model(self):
        g = Guard(condition="score >= 70", on_fail="skip")
        assert g.on_fail == "skip"
        assert g.default_value is None

    def test_guard_with_default(self):
        g = Guard(condition="value is not null", on_fail="default", default_value=0)
        assert g.default_value == 0

    def test_step_model(self):
        s = Step(
            name="enrich",
            output_schema="EnrichedLead",
            effects=[Effect(kind="call", target="clearbit")],
            guards=[Guard(condition="email is not null")],
        )
        assert s.input_schema is None
        assert s.output_schema == "EnrichedLead"

    def test_workflow_model(self):
        w = Workflow(
            name="Test",
            schemas=[
                Schema(name="In", fields=[FieldDef(name="x", type=WFType.TEXT)]),
                Schema(name="Out", fields=[FieldDef(name="y", type=WFType.INT)]),
            ],
            steps=[
                Step(name="process", input_schema="In", output_schema="Out"),
            ],
            input_schema="In",
            output_schema="Out",
        )
        assert w.name == "Test"
        assert len(w.schemas) == 2
        assert len(w.steps) == 1


# --- Fixture loading tests ---


class TestFixtures:
    """Test that fixture files parse into valid Workflow models."""

    def test_valid_crm_pipeline(self):
        data = json.loads((FIXTURES / "valid_crm_pipeline.json").read_text())
        w = Workflow(**data)
        assert w.name == "CRM Lead Pipeline"
        assert len(w.schemas) == 4
        assert len(w.steps) == 4
        assert w.input_schema == "RawLead"
        assert w.output_schema == "PushResult"

    def test_invalid_type_mismatch_parses(self):
        """The fixture should parse as a valid Workflow structurally —
        the type mismatch is a semantic error caught by verification."""
        data = json.loads((FIXTURES / "invalid_type_mismatch.json").read_text())
        w = Workflow(**data)
        assert len(w.steps) == 2

    def test_invalid_undeclared_effect_parses(self):
        """Same — parses fine, verification catches the problem."""
        data = json.loads((FIXTURES / "invalid_undeclared_effect.json").read_text())
        w = Workflow(**data)
        assert w.steps[0].effects == []


# --- Round-trip tests ---


class TestRoundTrip:
    """Test serialization round-trips."""

    def test_workflow_round_trip(self):
        data = json.loads((FIXTURES / "valid_crm_pipeline.json").read_text())
        w1 = Workflow(**data)
        json_str = w1.model_dump_json()
        w2 = Workflow(**json.loads(json_str))
        assert w1 == w2

    def test_all_fixtures_round_trip(self):
        for fixture_path in FIXTURES.glob("*.json"):
            data = json.loads(fixture_path.read_text())
            w1 = Workflow(**data)
            w2 = Workflow(**json.loads(w1.model_dump_json()))
            assert w1 == w2, f"Round-trip failed for {fixture_path.name}"


# --- JSON Schema export tests ---


class TestSchemaExport:
    """Test JSON Schema generation."""

    def test_json_schema_is_valid(self):
        schema = get_workflow_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "schemas" in schema["properties"]
        assert "steps" in schema["properties"]

    def test_tool_definition_structure(self):
        tool = get_workflow_tool_definition()
        assert tool["name"] == "generate_workflow"
        assert "description" in tool
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]
