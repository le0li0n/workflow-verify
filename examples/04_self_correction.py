"""Example 04: Self-correction loop with mock LLM.

Demonstrates the generate-and-verify loop. On the first attempt the "LLM"
returns an invalid workflow (type mismatch). The correction loop formats
the errors and the "LLM" returns a fixed version on attempt 2.

No real LLM API key needed — uses a mock client for demonstration.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from workflow_verify import generate_and_verify

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"


class MockLLMClient:
    """Simulates an LLM that returns an invalid workflow first, then a valid one."""

    def __init__(self):
        self._attempt = 0
        self._invalid = json.loads((FIXTURES / "invalid_type_mismatch.json").read_text())
        self._valid = json.loads((FIXTURES / "valid_crm_pipeline.json").read_text())

    async def generate_workflow(self, prompt: str, schema: dict) -> dict[str, Any]:
        self._attempt += 1
        if self._attempt == 1:
            print(f"  [Mock LLM] Attempt {self._attempt}: returning invalid workflow")
            return self._invalid
        else:
            print(f"  [Mock LLM] Attempt {self._attempt}: returning corrected workflow")
            return self._valid


async def main():
    print("=== Self-Correction Loop Demo ===\n")

    client = MockLLMClient()
    result = await generate_and_verify(
        prompt="Build a CRM lead pipeline with enrichment and scoring",
        target="python",
        client=client,
        max_attempts=3,
    )

    print(f"\nConverged: {result.converged}")
    print(f"Total attempts: {len(result.attempts)}\n")

    for attempt in result.attempts:
        status = "PASS" if (attempt.verification and attempt.verification.passed) else "FAIL"
        errors = len(attempt.verification.errors) if attempt.verification else 0
        print(f"Attempt {attempt.attempt_number}: {status} ({errors} errors)")

        if attempt.correction:
            print(f"  Correction sent to LLM with {len(attempt.correction.errors)} errors:")
            for err in attempt.correction.errors:
                print(f"    - {err.message}")

    if result.converged and result.transpiled:
        lines = result.transpiled.code.count("\n") + 1
        print(f"\nTranspiled to {result.transpiled.target.value} ({lines} lines)")


asyncio.run(main())
