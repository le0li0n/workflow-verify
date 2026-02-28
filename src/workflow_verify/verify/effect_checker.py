"""Effect checker — verifies side effects are properly declared."""

from __future__ import annotations

import re

from workflow_verify.ast.models import Effect, Workflow

from .results import CheckResult

EFFECT_KEYWORDS: dict[str, list[str]] = {
    "read": ["fetch", "get", "pull", "query", "select", "read", "load"],
    "write": ["push", "write", "insert", "update", "upsert", "save", "store", "create"],
    "call": ["api", "http", "request", "webhook", "endpoint", "call"],
    "send": ["email", "notify", "send", "sms", "slack", "message"],
    "delete": ["delete", "remove", "drop", "truncate", "purge"],
}

# Known external service names
_SERVICE_NAMES = [
    "salesforce", "hubspot", "stripe", "twilio", "sendgrid", "slack",
    "clearbit", "segment", "snowflake", "bigquery", "postgres", "mysql",
    "redis", "dynamodb", "s3", "firebase", "supabase", "airtable",
]


def _detect_implied_effects(text: str) -> list[str]:
    """Detect effect kinds implied by text (description, config, name)."""
    text_lower = text.lower()
    detected: list[str] = []
    for kind, keywords in EFFECT_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                detected.append(kind)
                break
    return detected


def _detect_services(text: str) -> list[str]:
    """Detect external service names in text."""
    text_lower = text.lower()
    return [s for s in _SERVICE_NAMES if s in text_lower]


def check_effects(workflow: Workflow) -> list[CheckResult]:
    """Verify side effects are properly declared across all steps."""
    results: list[CheckResult] = []
    all_effects: list[Effect] = []
    effect_targets: dict[str, list[str]] = {}  # target -> list of (kind, step_name)

    for step in workflow.steps:
        # Collect all declared effects
        all_effects.extend(step.effects)

        # Track effect targets for duplicate detection
        for effect in step.effects:
            key = f"{effect.kind}:{effect.target}"
            if key not in effect_targets:
                effect_targets[key] = []
            effect_targets[key].append(step.name)

        # Build searchable text from step description, name, and config
        searchable_parts = [step.name, step.description]
        for k, v in step.config.items():
            searchable_parts.append(str(k))
            searchable_parts.append(str(v))
        searchable = " ".join(searchable_parts)

        # 2. Heuristic: check for undeclared effects
        implied_kinds = _detect_implied_effects(searchable)
        declared_kinds = {e.kind for e in step.effects}

        for kind in implied_kinds:
            if kind not in declared_kinds:
                results.append(
                    CheckResult(
                        passed=True,  # Warning, not failure
                        check_type="effect",
                        step=step.name,
                        message=(
                            f"Step '{step.name}' description/config suggests a "
                            f"'{kind}' effect but none is declared."
                        ),
                        severity="warning",
                        suggestion=(
                            f"Add an Effect(kind='{kind}', target='...') to "
                            f"step '{step.name}' if it performs this action."
                        ),
                    )
                )

        # Check for service names without effects
        implied_services = _detect_services(searchable)
        declared_targets = {e.target.lower() for e in step.effects}
        for service in implied_services:
            if service not in declared_targets:
                results.append(
                    CheckResult(
                        passed=True,
                        check_type="effect",
                        step=step.name,
                        message=(
                            f"Step '{step.name}' mentions '{service}' but has "
                            f"no declared effect targeting it."
                        ),
                        severity="warning",
                        suggestion=(
                            f"If step '{step.name}' interacts with {service}, "
                            f"declare the appropriate effect."
                        ),
                    )
                )

        # 3. Steps with effects but no guards
        write_effects = [e for e in step.effects if e.kind in ("write", "delete", "send")]
        if write_effects and not step.guards:
            targets = ", ".join(f"{e.kind.upper()}:{e.target}" for e in write_effects)
            results.append(
                CheckResult(
                    passed=True,
                    check_type="effect",
                    step=step.name,
                    message=(
                        f"Step '{step.name}' has {targets} effect(s) but no "
                        f"guard conditions — all records will be affected."
                    ),
                    severity="warning",
                    suggestion=(
                        f"Add a Guard to step '{step.name}' to protect "
                        f"against unintended side effects."
                    ),
                )
            )

    # 4. Duplicate effects across steps
    for key, step_names in effect_targets.items():
        if len(step_names) > 1:
            kind, target = key.split(":", 1)
            results.append(
                CheckResult(
                    passed=True,
                    check_type="effect",
                    step=None,
                    message=(
                        f"Multiple steps {step_names} declare "
                        f"{kind.upper()} effect on '{target}'. "
                        f"This may cause conflicts."
                    ),
                    severity="warning",
                    suggestion=(
                        f"Verify that multiple {kind.upper()} operations "
                        f"on '{target}' are intentional."
                    ),
                )
            )

    # 1. Produce effects manifest (info-level pass result)
    if all_effects:
        manifest = ", ".join(
            f"{e.kind.upper()}:{e.target}" for e in all_effects
        )
        results.append(
            CheckResult(
                passed=True,
                check_type="effect",
                step=None,
                message=f"Effects manifest: {manifest}.",
                severity="info",
            )
        )

    return results, all_effects
