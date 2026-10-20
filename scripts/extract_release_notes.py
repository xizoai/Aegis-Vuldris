"""Extract a release's changelog section plus upgrade notes.

Run: python scripts/extract_release_notes.py v0.2.0

Used by the release workflow to publish the GitHub Release body: the
changelog section for the tag, plus an Upgrade notes block stating the
migration head at that release. Exit 1 with a clear message when the
changelog has no section for the tag, so a release cannot ship without
release notes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"

_REVISION_RE = re.compile(r"^revision(?::[^=\n]*)?=\s*[\"']([^\"']+)[\"']", re.MULTILINE)
_DOWN_REVISION_RE = re.compile(r"^down_revision(?::[^=\n]*)?=\s*(.+)$", re.MULTILINE)
_QUOTED_RE = re.compile(r"[\"']([^\"']+)[\"']")


def migration_head() -> str:
    """Return the head Alembic revision, parsed from the scripts.

    Deliberately dependency-free: the release job runs before anything is
    installed, and the only question is "which revision string is the head".
    """

    revisions: dict[str, list[str]] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        revision = _REVISION_RE.search(text)
        if revision is None:
            continue
        # A merge revision names several parents in a tuple; a normal revision
        # names one string; a base revision sets None (no quoted values).
        down = _DOWN_REVISION_RE.search(text)
        revisions[revision.group(1)] = _QUOTED_RE.findall(down.group(1)) if down else []

    parents = {parent for down_revisions in revisions.values() for parent in down_revisions}
    heads = [revision for revision in revisions if revision not in parents]
    if not heads:
        raise SystemExit("no alembic revisions found under alembic/versions")
    if len(heads) > 1:
        raise SystemExit("multiple alembic heads: " + ", ".join(sorted(heads)))
    return heads[0]


def changelog_section(version: str) -> str:
    """Return the CHANGELOG.md section for a tag like ``v0.2.0``."""

    clean = version.lstrip("vV")
    text = CHANGELOG.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^## \[{re.escape(clean)}\][^\n]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"CHANGELOG.md has no section for [{clean}]")
    return match.group(0).strip("\n")


def render(version: str) -> str:
    section = changelog_section(version)
    head = migration_head()
    return "\n\n".join(
        [
            section,
            "## Upgrade notes",
            "",
            f"- **Migration head at this release:** `{head}`. Run "
            "`alembic upgrade head` (or the compose `migrate` service) before the "
            "new version takes traffic; the app never migrates on start.",
            "- **Breaking changes:** listed in the changelog section above; if "
            "the section lists none, there are none.",
            "- **Rollback:** see `docs/release-process.md` — roll back images only "
            "when the schema is backwards-compatible with them.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python scripts/extract_release_notes.py <tag>", file=sys.stderr)
        return 1
    # The changelog contains non-ASCII characters; the release notes file must
    # be UTF-8 regardless of the platform's default console encoding.
    if sys.stdout.encoding is None or sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(render(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
