"""``python -m app.cli.demo`` — seed the offline demo project.

Seeds a synthetic project (recorded execution, findings, evidence) from the
bundled fixture so the UI can be explored with zero provider credentials.
Every seeded row carries a ``[DEMO]`` marker and the recorded findings stay
``open``; nothing in the demo path can mark data ``fixed`` or ``verified``.

Usage:
    python -m app.cli.demo --email owner@example.com
    aegis demo --email owner@example.com

Options:
    --email EMAIL     Account that will own the demo project (required)
    --name NAME       Demo project name (default: "[DEMO] Aegis demo")
    --dry-run         Report what would be seeded without writing
    --prune           Delete this account's demo project and exit
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.session import create_session_factory
from app.models.user import User
from app.services.demo import (
    DEFAULT_DEMO_PROJECT_NAME,
    DemoSeedReport,
    load_demo_fixture,
    prune_demo_project,
    seed_demo_project,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.demo",
        description="Seed an offline, synthetic demo project (zero credentials needed).",
    )
    parser.add_argument("--email", required=True, help="Account that will own the demo project.")
    parser.add_argument(
        "--name",
        default=DEFAULT_DEMO_PROJECT_NAME,
        help=f"Demo project name (default: {DEFAULT_DEMO_PROJECT_NAME!r}).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be seeded without writing."
    )
    parser.add_argument(
        "--prune", action="store_true", help="Delete this account's demo project and exit."
    )
    return parser.parse_args(argv)


def _require_user(session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        print(f"error: no account with email {email!r}; register one first", file=sys.stderr)
        raise SystemExit(1)
    return user


def _dry_run(name: str) -> int:
    fixture = load_demo_fixture()
    print(f"would seed project {name!r} with:")
    print(f"  1 target ({fixture['target']['name']})")
    print(f"  1 test ({fixture['test']['name']})")
    print(
        "  1 recorded execution"
        f" ({len(fixture['execution']['steps'])} step(s), result {fixture['execution']['result']})"
    )
    print(f"  {len(fixture['findings'])} finding(s), all open, all [DEMO]-marked")
    print("  remediation plans are generated on demand, nothing to seed")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.dry_run and args.prune:
        print("error: --dry-run and --prune are mutually exclusive", file=sys.stderr)
        return 1
    if args.dry_run:
        return _dry_run(args.name)

    session = create_session_factory()()
    try:
        user = _require_user(session, args.email)

        if args.prune:
            deleted = prune_demo_project(session, user, project_name=args.name)
            if deleted:
                print(f"deleted demo project {args.name!r}")
                return 0
            print(f"no demo project named {args.name!r} for {args.email}")
            return 0

        report: DemoSeedReport = seed_demo_project(session, user, project_name=args.name)
        if not report.created:
            print(f"demo project already seeded: {args.name!r} ({report.project_id})")
            print(f"  {report.findings} finding(s), {report.evidence} evidence row(s)")
            return 0

        print(f"seeded demo project {args.name!r} ({report.project_id})")
        print(f"  1 recorded execution, {report.findings} finding(s),")
        print(f"  {report.evidence} evidence row(s), every row [DEMO]-marked")
        print(
            "  findings stay un-resolved, never fixed or verified; "
            "open the project in the UI to inspect it"
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
