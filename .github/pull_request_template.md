<!--
Definition of done and project rules: CONTRIBUTING.md
-->

## Summary

<!-- What does this PR change, and why? One or two sentences. -->

## Changes

<!-- Bullet points; mention docs and migrations. -->

## Checklist

- [ ] `ruff check` + `ruff format --check` pass
- [ ] `pyright` passes with 0 errors
- [ ] Full `pytest` suite passes (with PostgreSQL)
- [ ] `alembic check` passes (model changes carry a migration)
- [ ] Frontend `typecheck`, `lint`, and tests pass (if touched)
- [ ] Docs updated where behavior changed
- [ ] `CHANGELOG.md` entry under `[Unreleased]`

## Security checklist

- [ ] This change does **not** weaken an existing security test, the SSRF/network policy, or credential handling.
- [ ] Nothing in this change lets a finding become `fixed` except a human claim, or `verified` except a passed deterministic rerun.
- [ ] No secrets, real credentials, or private evidence are committed.
- [ ] New/changed CLI exit codes or API paths are documented (they are contracts).

## Sign-off

<!-- Commits must carry `Signed-off-by: Name <email>` (DCO, see CONTRIBUTING.md). -->

- [ ] My commits are signed off (`git commit -s`).
