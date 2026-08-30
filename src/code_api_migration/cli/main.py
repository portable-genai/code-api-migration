"""Minimal stdlib CLI: analyse a repo migration, or verify the audit chain (argparse)."""

from __future__ import annotations

import argparse
import sys

from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..domain.migration_service import MigrationService
from ..packs import pack_resolver


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code_api_migration")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_cmd = sub.add_parser("analyze", help="Analyse a target repo's migration.")
    analyze_cmd.add_argument("repo_id", help="The target repo id the scanner resolves.")
    analyze_cmd.add_argument("--actor", default="cli-user@bank.example")
    analyze_cmd.add_argument("--tenant", default="", help="Tenant partition asserted to Hrz7.")

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="code-api-migration")

    if args.command == "analyze":
        checkout = container.repo_scanner.scan(args.repo_id)
        service = MigrationService(
            container.audit, tracer=container.tracer, resolve_pack=pack_resolver()
        )
        result, plan = service.run(checkout, actor=args.actor)
        print(f"{result.subject}: {result.severity.value} ({result.decision.value})")
        print(
            f"  {result.fail_count} breaking change(s), {result.step_count} step(s), "
            f"blocked={result.blocked}"
        )
        print(f"  requires_human_review: {result.requires_human_review}")
        if result.requires_human_review:
            # Rule R8 on the CLI path too: the same escalation, the same router. A surface that
            # only printed the flag would be a second place for an escalation to stop.
            ref = container.review_router.route(result, maker=args.actor, tenant=args.tenant)
            print(f"  routed to human review: {ref}")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
