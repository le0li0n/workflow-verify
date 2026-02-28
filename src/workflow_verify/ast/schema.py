"""JSON Schema export for LLM structured output APIs."""

from workflow_verify.ast.models import Workflow


def get_workflow_json_schema() -> dict:
    """Returns JSON Schema for use with Anthropic/OpenAI structured outputs."""
    return Workflow.model_json_schema()


def get_workflow_tool_definition() -> dict:
    """Returns a tool definition for use with Anthropic's tool_use API."""
    return {
        "name": "generate_workflow",
        "description": (
            "Generate a verified workflow AST that defines a multi-step "
            "agentic pipeline. The workflow will be verified for type safety, "
            "schema compatibility, side-effect declarations, and guard "
            "conditions before any code executes."
        ),
        "input_schema": get_workflow_json_schema(),
    }
