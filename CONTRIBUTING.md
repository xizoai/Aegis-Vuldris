# Contributing to Aegis Vuldris

Thanks for wanting to contribute. This document is the shortest path from
clone to merged PR; [`docs/development.md`](docs/development.md) has the full
local-setup detail.

## Setup

```bash
python -m venv .venv && .venv\Scripts\activate    # or source .venv/bin/activate
pip install .
pip install "pytest>=9.1,<10" "httpx2>=2.13,<3" "ruff>=0.16.6,<1" "pyright>=1.1.413,<2"
cp .env.example .env    # fill in DATABASE_URL and SECRET_KEY (PostgreSQL is required)
```

Backend tests need a PostgreSQL database:

```bash
set DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/aegis_test
set SECRET_KEY=dev
set APP_ENV=testing
pytest -q
```

## Definition of done (every PR)

These all run in CI; run them locally first:

```bash
ruff check . && ruff format --check .        # lint + formatting (backend, tests, scripts, examples)
pyright                                      # 0 errors
pytest -q                                    # full suite, needs PostgreSQL
alembic check                                # no migration drift
cd frontend && npm run typecheck && npm run lint && npm test
```

Plus:

- docs updated if behavior changed, and a `CHANGELOG.md` entry under
  `[Unreleased]`;
- new user-facing behavior has a test;
- no unsupported claims in docs — describe demonstrated behavior only
  (the demo and example apps are scripted, and say so).

## Project rules that reviews will hold you to

**Do not weaken security semantics.** A finding only becomes `fixed` by a
human claim and only becomes `verified` by a passed deterministic
verification rerun. No code path may let a model output change either state.
If your change touches this lifecycle, say so explicitly in the PR.

**Respect the module boundaries.** The engine, grading, classification,
adapters, evidence, and report schemas are the shared core: extend them in
place rather than restructuring. Billing or metering code must never be
imported by core modules. Business logic lives in `backend/app/services/`;
routes and the CLI stay thin callers of it.

**Adapters are extended via the registry** (`backend/app/adapters/registry.py`),
never replaced. The attack library is data (`backend/app/test_cases/`) —
adding cases means adding YAML, not code.

**Migrations are additive and reviewed separately** from model changes:
`alembic check` must pass, and a migration that cannot run against a live
database is a release blocker.

**Exit codes and API paths are contracts.** The `aegis` CLI exit-code table
(`docs/Manual.md`) and existing route paths are what CI jobs and clients
build on; change them only with a deprecation note in the changelog.

## Commit sign-off (DCO)

This project uses the [Developer Certificate of Origin](https://developercertificate.org/).
Every commit must include a sign-off line certifying that you wrote the code
and have the right to submit it:

```
Signed-off-by: Jane Doe <jane@example.com>
```

Add `-s` to `git commit` (`git commit -s`) if your Git user name and email
are set. Maintainers check for the sign-off at merge time.

## Pull requests

1. Branch from `main`.
2. Keep PRs focused; one logical change each.
3. Fill in the pull request template, including the security checklist.
4. `main` requires CI to pass and one approval.

## Reporting issues

- Bugs: use the bug report issue template and paste `aegis doctor` output.
- Security vulnerabilities: see [`SECURITY.md`](SECURITY.md) — please do not
  open a public issue for those.
- Conduct: see [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions are licensed under the
Apache License 2.0 (see [`LICENSE`](LICENSE)).
