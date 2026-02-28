"""Example 06: Extract effects manifest for compliance review.

Before deploying an LLM-generated workflow, compliance teams need to know
exactly what external systems it will touch. The effects() function
extracts a complete manifest of side effects from a verified workflow.
"""

import json
from pathlib import Path

from workflow_verify import Workflow, effects, verify

# Load the CRM pipeline
fixture_path = Path(__file__).parent.parent / "tests" / "fixtures" / "valid_crm_pipeline.json"
workflow = Workflow(**json.loads(fixture_path.read_text()))

# Extract effects manifest
manifest = effects(workflow, strict=False)

print(f"=== Compliance Report: {workflow.name} ===\n")
print(f"Description: {workflow.description}")
print(f"Steps: {len(workflow.steps)}")
print()

# Group by effect kind
by_kind: dict[str, list] = {}
for effect in manifest:
    by_kind.setdefault(effect.kind, []).append(effect)

print("=== Side Effects Summary ===\n")
for kind in ["read", "write", "call", "send", "delete"]:
    group = by_kind.get(kind, [])
    if group:
        print(f"  {kind.upper()} ({len(group)}):")
        for e in group:
            print(f"    - {e.target}: {e.description}")
        print()

# Show which steps have write effects (highest risk)
print("=== Write Operations (Requires Approval) ===\n")
for step in workflow.steps:
    writes = [e for e in step.effects if e.kind == "write"]
    if writes:
        guards = [g.condition for g in step.guards] if step.guards else ["NONE"]
        print(f"  Step '{step.name}':")
        for w in writes:
            print(f"    Target: {w.target}")
            print(f"    Description: {w.description}")
        print(f"    Guards: {', '.join(guards)}")
        print()

# Full verification trace for the record
print("=== Full Verification Trace ===\n")
result = verify(workflow, strict=False)
print(result.trace)
