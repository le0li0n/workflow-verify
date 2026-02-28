"""Example 07: Define custom schemas and use registry schemas together.

Shows how to combine pre-built registry schemas with your own custom
schemas in a single workflow.
"""

from workflow_verify import (
    FieldDef,
    Schema,
    TranspileTarget,
    Workflow,
    list_categories,
    list_schemas,
    load_schema,
    search_schemas,
    transpile,
    verify,
)

# Browse what's available in the registry
print("=== Schema Registry ===\n")
categories = list_categories()
for cat in categories:
    schemas = list_schemas(cat)
    print(f"  {cat}/  ({len(schemas)} schemas)")
    for s in schemas:
        print(f"    {s}")
print()

# Search for relevant schemas
print("=== Searching for 'lead' schemas ===\n")
results = search_schemas("lead")
for schema in results:
    print(f"  {schema.name}: {schema.description}")
print()

# Load a registry schema to see its structure
sf_lead = load_schema("crm/salesforce_lead")
print(f"=== Registry Schema: {sf_lead.name} ===")
print(f"  {sf_lead.description}")
for f in sf_lead.fields:
    print(f"  {f.name}: {f.type} — {f.description}")
print()

# Define a custom schema that extends the concept
print("=== Building Custom Workflow ===\n")

custom_scored = Schema(
    name="CustomScoredLead",
    description="Our internal scoring format",
    fields=[
        FieldDef(name="email", type="Email", description="Contact email"),
        FieldDef(name="name", type="Text", description="Full name"),
        FieldDef(name="company", type="Text", description="Company name"),
        FieldDef(name="fit_score", type="Int", description="ICP fit score 0-100"),
        FieldDef(name="intent_score", type="Int", description="Intent signal score 0-100"),
        FieldDef(name="combined_score", type="Float", description="Weighted combined score"),
    ],
)

output_schema = Schema(
    name="RoutingResult",
    description="Result of lead routing",
    fields=[
        FieldDef(name="email", type="Email", description="Contact email"),
        FieldDef(name="assigned_to", type="Text", description="Assigned sales rep"),
        FieldDef(name="priority", type="Text", description="Priority level"),
    ],
)

# Build a workflow using the custom schemas
workflow = Workflow(
    name="Lead Scoring & Routing",
    description="Score leads with custom model and route to sales reps",
    schemas=[custom_scored, output_schema],
    steps=[
        {
            "name": "score_leads",
            "description": "Apply custom scoring model to leads",
            "input_schema": None,
            "output_schema": "CustomScoredLead",
            "effects": [
                {"kind": "read", "target": "data_warehouse", "description": "Read lead features"},
            ],
            "guards": [],
            "config": {"model": "lead_scoring_v3"},
        },
        {
            "name": "route_to_sales",
            "description": "Route qualified leads to appropriate sales reps",
            "input_schema": "CustomScoredLead",
            "output_schema": "RoutingResult",
            "effects": [
                {"kind": "write", "target": "crm", "description": "Update lead assignment in CRM"},
                {"kind": "send", "target": "slack", "description": "Notify sales rep via Slack"},
            ],
            "guards": [
                {"condition": "combined_score >= 70", "on_fail": "skip"},
            ],
            "config": {},
        },
    ],
    input_schema="CustomScoredLead",
    output_schema="RoutingResult",
)

# Verify and transpile
result = verify(workflow)
print(result.trace)
print()

if result.passed:
    transpiled = transpile(workflow, TranspileTarget.PYTHON)
    print(f"Transpiled to {transpiled.filename} ({transpiled.code.count(chr(10)) + 1} lines)")
    print(f"Dependencies: {transpiled.dependencies}")
