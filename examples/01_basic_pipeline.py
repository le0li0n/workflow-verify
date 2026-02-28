"""Example 01: Basic 3-step pipeline — define, verify, transpile.

This is the simplest possible workflow-verify usage: define a workflow
as a Python dict, verify it, and transpile to Python code.
"""

from workflow_verify import TranspileTarget, Workflow, transpile, verify

# Define a minimal 3-step workflow inline
workflow_data = {
    "name": "Data Cleanup Pipeline",
    "description": "Fetch records, normalize fields, and write cleaned data",
    "schemas": [
        {
            "name": "RawRecord",
            "fields": [
                {"name": "id", "type": "Text", "description": "Record ID"},
                {"name": "email", "type": "Text", "description": "Raw email string"},
                {"name": "name", "type": "Text", "description": "Full name"},
            ],
        },
        {
            "name": "CleanRecord",
            "fields": [
                {"name": "id", "type": "Text", "description": "Record ID"},
                {"name": "email", "type": "Email", "description": "Validated email"},
                {"name": "name", "type": "Text", "description": "Normalized name"},
            ],
        },
        {
            "name": "WriteResult",
            "fields": [
                {"name": "id", "type": "Text", "description": "Record ID"},
                {"name": "status", "type": "Text", "description": "Write status"},
            ],
        },
    ],
    "steps": [
        {
            "name": "fetch_records",
            "description": "Read raw records from the database",
            "input_schema": None,
            "output_schema": "RawRecord",
            "effects": [
                {"kind": "read", "target": "database", "description": "Read from source DB"},
            ],
            "guards": [],
            "config": {},
        },
        {
            "name": "normalize",
            "description": "Validate emails and normalize names",
            "input_schema": "RawRecord",
            "output_schema": "CleanRecord",
            "effects": [],
            "guards": [],
            "config": {},
        },
        {
            "name": "write_clean",
            "description": "Write cleaned records to destination",
            "input_schema": "CleanRecord",
            "output_schema": "WriteResult",
            "effects": [
                {"kind": "write", "target": "database", "description": "Write to dest DB"},
            ],
            "guards": [],
            "config": {},
        },
    ],
    "input_schema": "RawRecord",
    "output_schema": "WriteResult",
}

workflow = Workflow(**workflow_data)

# Verify
result = verify(workflow)
print(result.trace)
print()

if result.passed:
    print("Verification passed! Transpiling to Python...\n")
    transpiled = transpile(workflow, TranspileTarget.PYTHON)
    print(f"# Filename: {transpiled.filename}")
    print(f"# Dependencies: {', '.join(transpiled.dependencies)}")
    print()
    print(transpiled.code)
else:
    print("Verification failed:")
    for error in result.errors:
        print(f"  - {error.message}")
