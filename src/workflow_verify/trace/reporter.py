"""Verification trace — produces human-readable audit trail."""

from __future__ import annotations

from workflow_verify.verify.results import CheckResult

_PASS_ICON = "\u2705 "  # green checkmark
_WARN_ICON = "\u26a0\ufe0f "  # warning sign
_FAIL_ICON = "\u274c "  # red X


def format_trace(checks: list[CheckResult]) -> str:
    """Format check results as a human-readable verification trace."""
    lines: list[str] = []

    for check in checks:
        if check.severity == "error" and not check.passed:
            icon = _FAIL_ICON
        elif check.severity == "warning":
            icon = _WARN_ICON
        else:
            icon = _PASS_ICON

        lines.append(f"{icon}{check.message}")

    return "\n".join(lines)
