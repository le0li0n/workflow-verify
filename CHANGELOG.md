# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `strict=True` was a no-op — both strict and non-strict modes evaluated `len(errors) == 0`. In strict mode, `passed` now correctly requires `len(errors) == 0 and len(warnings) == 0`.

### Changed ⚠️ Breaking
- `verify()`, `effects()`, and `mcp_server.verify_workflow()` default changed from `strict=True` to `strict=False`. Callers relying on the default will now get permissive behavior (warnings do not fail verification unless `strict=True` is explicitly passed).
- CLI flag `--no-strict` renamed to `--strict` (opt-in for warnings-as-errors, consistent with the new permissive default). The old `--no-strict` flag is no longer accepted.

## [0.1.0] - 2026-02-28

### Added

- **Workflow AST** — Pydantic models for workflows, steps, schemas, effects, guards, and a complete type system with subtyping rules.
- **Verification engine** — Four-pass checker: type flow, schema validation, side-effect analysis, and guard condition verification. Human-readable trace output.
- **Transpiler suite** — Generate executable code from verified workflows targeting Python (Pydantic + async), TypeScript (Zod + typed functions), and Temporal.io (workflow + activities).
- **Self-correction protocol** — Generate-verify-correct loop with built-in Anthropic and OpenAI clients. Formats verification errors as structured LLM prompts for self-repair.
- **Schema registry** — 20 pre-built YAML schemas across 5 categories (CRM, enrichment, communication, data, common). Search, list, and load by path.
- **Dynamic schema resolvers** — Live schema resolution from HubSpot, Salesforce, Stripe, PostgreSQL, Clay, and CRMZero APIs with TTL caching and static fallback.
- **Public API** — All 37 symbols re-exported from top-level package. Convenience functions: `run()`, `run_sync()`, `effects()`.
- **CLI tool (`wfv`)** — Four subcommands: `verify`, `transpile`, `registry`, `generate`. JSON output mode, strict/non-strict verification.
- **Documentation** — README with architecture diagram, quick start, and API reference. 7 example scripts. CONTRIBUTING guide with schema contribution walkthrough.
- **CI/CD** — GitHub Actions for lint (ruff), type check (mypy), test (pytest across Python 3.10-3.13), and PyPI publish.
- **MCP server** — Model Context Protocol integration with `verify_workflow` and `generate_verified_workflow` tools for inline LLM verification via Claude Desktop or any MCP client.

