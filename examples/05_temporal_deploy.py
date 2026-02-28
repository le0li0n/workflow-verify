"""Example 05: Transpile to Temporal.io workflow.

Demonstrates transpiling a verified workflow to a Temporal.io workflow
definition with activities, workflow class, and worker setup.
"""

import json
from pathlib import Path

from workflow_verify import TranspileTarget, Workflow, transpile, verify

# Load fixture
fixture_path = Path(__file__).parent.parent / "tests" / "fixtures" / "valid_crm_pipeline.json"
workflow = Workflow(**json.loads(fixture_path.read_text()))

# Verify first
result = verify(workflow)
assert result.passed, f"Verification failed: {[e.message for e in result.errors]}"

# Transpile to Temporal
temporal = transpile(workflow, TranspileTarget.TEMPORAL)

print(f"=== Temporal Workflow: {temporal.filename} ===")
print(f"Dependencies: {', '.join(temporal.dependencies)}")
print()
print("=== Setup Instructions ===")
print(temporal.instructions)
print()
print("=== Generated Code ===")
print(temporal.code)
