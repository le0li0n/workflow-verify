"""Example 03: Pipeline with guard conditions.

Guards are pre-conditions on steps. They reference fields in the step's
input schema and control whether the step executes, skips, or uses a default.
"""

from workflow_verify import Workflow, verify

workflow = Workflow(**{
    "name": "Guarded Email Campaign",
    "description": "Send targeted emails only to qualified, opted-in contacts",
    "schemas": [
        {
            "name": "Contact",
            "fields": [
                {"name": "email", "type": "Email", "description": "Contact email"},
                {"name": "name", "type": "Text", "description": "Full name"},
                {"name": "score", "type": "Int", "description": "Lead score 0-100"},
                {"name": "opted_in", "type": "Bool", "description": "Email opt-in status"},
                {"name": "segment", "type": "Text", "description": "Market segment"},
            ],
        },
        {
            "name": "EmailResult",
            "fields": [
                {"name": "email", "type": "Email", "description": "Recipient email"},
                {"name": "status", "type": "Text", "description": "Send status"},
                {"name": "segment", "type": "Text", "description": "Segment used"},
            ],
        },
    ],
    "steps": [
        {
            "name": "fetch_contacts",
            "description": "Load contacts from CRM",
            "input_schema": None,
            "output_schema": "Contact",
            "effects": [{"kind": "read", "target": "crm", "description": "Read contacts"}],
            "guards": [],
            "config": {},
        },
        {
            "name": "send_email",
            "description": "Send personalized email to qualified contacts",
            "input_schema": "Contact",
            "output_schema": "EmailResult",
            "effects": [
                {"kind": "send", "target": "email_service", "description": "Send via SendGrid"},
            ],
            "guards": [
                # Only send to high-scoring contacts
                {"condition": "score >= 50", "on_fail": "skip"},
                # Must have opted in
                {"condition": "opted_in == true", "on_fail": "skip"},
                # Default segment if missing
                {"condition": "segment != ''", "on_fail": "default", "default_value": "general"},
            ],
            "config": {"template": "campaign_q1"},
        },
    ],
    "input_schema": "Contact",
    "output_schema": "EmailResult",
})

result = verify(workflow)
print(result.trace)
print()

if result.passed:
    print("All guards validated successfully!")
    print("\nGuards on 'send_email' step:")
    for step in workflow.steps:
        if step.name == "send_email":
            for guard in step.guards:
                if guard.on_fail == "default":
                    action = f"default={guard.default_value}"
                else:
                    action = guard.on_fail
                print(f"  {guard.condition} (on_fail: {action})")
else:
    print("Guard validation failed:")
    for error in result.errors:
        print(f"  {error.message}")
        if error.suggestion:
            print(f"  Fix: {error.suggestion}")
