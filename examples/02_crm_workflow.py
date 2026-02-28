"""Example 02: CRM Lead Pipeline — Salesforce + Clearbit enrichment.

A realistic workflow that fetches leads from Salesforce, enriches them
with Clearbit company data, scores them, and pushes qualified leads back.
Uses the built-in schema registry for pre-defined schemas.
"""

import json
from pathlib import Path

from workflow_verify import (
    TranspileTarget,
    Workflow,
    load_schema,
    transpile,
    verify,
)

# Load the CRM pipeline fixture (same as what an LLM would generate)
fixture_path = Path(__file__).parent.parent / "tests" / "fixtures" / "valid_crm_pipeline.json"
workflow = Workflow(**json.loads(fixture_path.read_text()))

# Show what schemas are available from the registry
print("=== Registry schemas for reference ===")
sf_lead = load_schema("crm/salesforce_lead")
print(f"Salesforce Lead: {len(sf_lead.fields)} fields")
for f in sf_lead.fields[:5]:
    print(f"  {f.name}: {f.type}")
print(f"  ... and {len(sf_lead.fields) - 5} more\n")

# Verify the workflow
print("=== Verification ===")
result = verify(workflow, strict=False)
print(result.trace)
print()

# Show the effects manifest
print("=== Effects Manifest ===")
for effect in result.effects_manifest:
    print(f"  {effect.kind.upper()}:{effect.target} — {effect.description}")
print()

# Transpile to all three targets
for target in TranspileTarget:
    transpiled = transpile(workflow, target)
    lines = transpiled.code.count("\n") + 1
    print(f"=== {target.value.title()} ({lines} lines, deps: {transpiled.dependencies}) ===")
    # Show just the first 5 lines
    for line in transpiled.code.split("\n")[:5]:
        print(f"  {line}")
    print("  ...\n")
