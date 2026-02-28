"""Verification result models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from workflow_verify.ast.models import Effect


class CheckResult(BaseModel):
    """Result of a single verification check."""

    passed: bool
    check_type: str
    step: str | None
    message: str
    severity: Literal["error", "warning", "info"]
    suggestion: str | None = None


class VerificationResult(BaseModel):
    """Aggregated result of all verification checks."""

    passed: bool
    checks: list[CheckResult]
    effects_manifest: list[Effect]
    trace: str
    errors: list[CheckResult]
    warnings: list[CheckResult]
