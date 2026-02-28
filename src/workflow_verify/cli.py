"""CLI tool for workflow-verify (wfv)."""

from __future__ import annotations

import argparse
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wfv",
        description="Workflow Verify — pre-execution verification for LLM-generated workflows",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- verify ---
    p_verify = subparsers.add_parser("verify", help="Verify a workflow JSON file")
    p_verify.add_argument("file", help="Path to workflow JSON file")
    p_verify.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON",
    )
    p_verify.add_argument(
        "--no-strict", action="store_true", help="Treat undeclared effects as warnings",
    )

    # --- transpile ---
    p_transpile = subparsers.add_parser("transpile", help="Verify and transpile a workflow")
    p_transpile.add_argument("file", help="Path to workflow JSON file")
    p_transpile.add_argument(
        "-t", "--target", required=True,
        choices=["python", "typescript", "temporal"],
        help="Transpile target language",
    )
    p_transpile.add_argument("-o", "--output", help="Output file path (default: stdout)")

    # --- registry ---
    p_registry = subparsers.add_parser("registry", help="Browse the schema registry")
    registry_sub = p_registry.add_subparsers(dest="registry_command", help="Registry commands")

    p_reg_list = registry_sub.add_parser("list", help="List schemas")
    p_reg_list.add_argument("category", nargs="?", help="Filter by category")

    p_reg_search = registry_sub.add_parser("search", help="Search schemas by keyword")
    p_reg_search.add_argument("keyword", help="Search keyword")

    p_reg_show = registry_sub.add_parser("show", help="Show a schema by path")
    p_reg_show.add_argument("path", help="Schema path (e.g. crm/salesforce_lead)")

    # --- generate ---
    p_generate = subparsers.add_parser("generate", help="Generate a workflow from a prompt")
    p_generate.add_argument("prompt", help="Natural language workflow description")
    p_generate.add_argument(
        "-t", "--target", default="python",
        choices=["python", "typescript", "temporal"],
        help="Transpile target (default: python)",
    )
    p_generate.add_argument(
        "--llm", default="anthropic",
        choices=["anthropic", "openai"],
        help="LLM provider (default: anthropic)",
    )
    p_generate.add_argument(
        "--max-attempts", type=int, default=3,
        help="Max correction attempts (default: 3)",
    )

    return parser


def _cmd_verify(args: argparse.Namespace) -> int:
    from pathlib import Path

    from workflow_verify.ast.models import Workflow
    from workflow_verify.trace.reporter import format_trace
    from workflow_verify.verify import verify

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text())
        workflow = Workflow(**data)
    except Exception as e:
        print(f"Error: failed to parse workflow: {e}", file=sys.stderr)
        return 1

    strict = not args.no_strict
    result = verify(workflow, strict=strict)

    if args.json_output:
        output = {
            "passed": result.passed,
            "errors": [c.model_dump() for c in result.errors],
            "warnings": [c.model_dump() for c in result.warnings],
            "effects": [e.model_dump() for e in result.effects_manifest],
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_trace(result.checks))
        if result.effects_manifest:
            print(f"\nEffects ({len(result.effects_manifest)}):")
            for effect in result.effects_manifest:
                print(f"  {effect.kind}:{effect.target}")
        if result.passed:
            print("\nVerification passed.")
        else:
            print(f"\nVerification failed with {len(result.errors)} error(s).", file=sys.stderr)

    return 0 if result.passed else 1


def _cmd_transpile(args: argparse.Namespace) -> int:
    from pathlib import Path

    from workflow_verify.ast.models import Workflow
    from workflow_verify.transpile import TranspileTarget, transpile

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text())
        workflow = Workflow(**data)
    except Exception as e:
        print(f"Error: failed to parse workflow: {e}", file=sys.stderr)
        return 1

    try:
        result = transpile(workflow, TranspileTarget(args.target))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.output:
        out = Path(args.output)
        out.write_text(result.code)
        print(f"Wrote {out} ({len(result.code)} bytes)")
    else:
        print(result.code)

    return 0


def _cmd_registry(args: argparse.Namespace) -> int:
    from workflow_verify.registry import (
        SchemaLoadError,
        list_categories,
        list_schemas,
        load_schema,
        search_schemas,
    )

    subcmd = args.registry_command

    if subcmd == "list":
        if args.category:
            categories = list_categories()
            if args.category not in categories:
                avail = ", ".join(categories)
                msg = f"Error: unknown category '{args.category}'. Available: {avail}"
                print(msg, file=sys.stderr)
                return 1
            schemas = list_schemas(args.category)
        else:
            schemas = list_schemas()
        for s in schemas:
            print(s)
        return 0

    elif subcmd == "search":
        results = search_schemas(args.keyword)
        if not results:
            print(f"No schemas matching '{args.keyword}'")
            return 0
        for schema in results:
            print(f"{schema.name}: {schema.description or 'No description'}")
        return 0

    elif subcmd == "show":
        try:
            schema = load_schema(args.path)
        except SchemaLoadError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Name: {schema.name}")
        if schema.description:
            print(f"Description: {schema.description}")
        print(f"Fields ({len(schema.fields)}):")
        for f in schema.fields:
            print(f"  {f.name}: {f.type} — {f.description or ''}")
        return 0

    else:
        print("Error: specify a registry subcommand: list, search, or show", file=sys.stderr)
        return 1


def _cmd_generate(args: argparse.Namespace) -> int:
    import asyncio

    from workflow_verify.correct import generate_and_verify

    try:
        result = asyncio.run(
            generate_and_verify(
                prompt=args.prompt,
                target=args.target,
                llm=args.llm,
                max_attempts=args.max_attempts,
            )
        )
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if result.converged and result.transpiled:
        print(result.transpiled.code)
        return 0
    else:
        print(f"Failed to converge after {len(result.attempts)} attempt(s).", file=sys.stderr)
        if result.verification:
            for err in result.verification.errors:
                print(f"  - {err.message}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handlers = {
        "verify": _cmd_verify,
        "transpile": _cmd_transpile,
        "registry": _cmd_registry,
        "generate": _cmd_generate,
    }

    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
