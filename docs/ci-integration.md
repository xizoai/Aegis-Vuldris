# CI Integration

Aegis Vuldris can gate a CI job on assessment results. The contract is the CLI's
exit codes — a job fails on what you *configured* it to fail on, and can
always tell "the target regressed" apart from "the scanner broke".

## Exit codes

| Exit | Meaning | Job result |
|---|---|---|
| 0 | Assessment completed; no configured condition matched | pass |
| 1 | Usage or configuration error (bad arguments, unknown ids) | fail — fix the workflow |
| 2 | A configured condition matched: `--fail-on` threshold, `--baseline` regression, `--fail-on-inconclusive`, `aegis verify` on a re-producing or unconfirmed attack, `grading-accuracy` above its threshold, or `judge-calibration` below one of its thresholds | fail — **the security gate worked** |
| 4 | Operational error: database unavailable, target unreachable, engine failure | fail — **not a finding**; fix the scanner/deployment |

Two-grading-stage note: `--fail-on` counts only non-dismissed findings. A finding a
reviewer dismissed as a false positive never fails the job, and an unconfirmed match is
counted but labelled `(unconfirmed candidate)` — a run whose matches are only candidates
prints `[NEEDS REVIEW]`. To gate on unconfirmed matches explicitly, add the
`aegis grading-accuracy --threshold` job below, or fail on `--fail-on-inconclusive` and
treat `needs_review` through your own triage process.

## GitHub Action

The repository ships a composite action at
[`integration/github-action/action.yml`](../integration/github-action/action.yml).
It runs the `aegis run` CLI in a container against your Aegis Vuldris deployment,
writes a job summary (per-test results, totals, matched reasons), and
propagates the exit code unchanged.

```yaml
name: Aegis Vuldris security gate
on:
  pull_request:

jobs:
  aegis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - uses: xizoai/Aegis-Vuldris/integration/github-action@main
        with:
          project: ${{ secrets.AEGIS_PROJECT_ID }}
          target: ${{ secrets.AEGIS_TARGET_ID }}
          email: ci@example.com
          database-url: ${{ secrets.AEGIS_DATABASE_URL }}
          secret-key: ${{ secrets.AEGIS_SECRET_KEY }}
          # Until the first tagged release publishes official images, point
          # this at an image you built from the repository:
          #   docker build -f backend/Dockerfile -t my-registry/aegis:ci .
          image: my-registry/aegis:ci
          fail-on: high
```

Inputs:

| Input | Required | Meaning |
|---|---|---|
| `project` | yes | Project id (UUID) holding the tests to run |
| `target` | yes | Target id (UUID) in that project to attack |
| `email` | yes | Account performing the run (audited as the actor; needs project write access) |
| `database-url` | yes | PostgreSQL connection string of your Aegis Vuldris deployment — use a secret |
| `secret-key` | yes | `SECRET_KEY` of the deployment — use a secret |
| `image` | yes | Aegis Vuldris backend image to run |
| `fail-on` | no | Severity threshold that fails the job (`info`…`critical`); empty disables |
| `baseline` | no | Regression baseline: a report id, or a path (workspace-relative) to a saved JSON report artifact |
| `fail-on-inconclusive` | no | `true` to fail when any run is inconclusive |

### Baseline regression gating

Commit the JSON artifact from your last known-good run (produce it with
`aegis export --report <id> --output baseline.json`) and point the gate at
it. Only findings that are new or regressed versus that baseline fail the
job, filtered by `fail-on`:

```yaml
          fail-on: high
          baseline: baselines/aegis-baseline.json
```

The file form needs no database reports, so it works against any deployment
and diffs stay reviewable in the repository.

## Any other CI: run the CLI

Every gate is just `aegis run` and its exit code:

```bash
docker run --rm \
  -e DATABASE_URL="$AEGIS_DATABASE_URL" \
  -e SECRET_KEY="$AEGIS_SECRET_KEY" \
  -e APP_ENV=production \
  my-registry/aegis:ci \
  aegis run \
    --project "$PROJECT_ID" \
    --target "$TARGET_ID" \
    --email ci@example.com \
    --fail-on high \
    --baseline "$(pwd)/baseline.json" \
    --json
```

## Grader precision gate (offline)

A separate, cheap job guards the grader itself, not the target: it grades known-safe
responses with every bundled attack and fails when the false-positive rate exceeds a
threshold. It needs no database, no network, and no credentials.

```bash
aegis grading-accuracy --threshold 0.01 --json
```

Run it whenever the attack library or grading rules change
([`grading-accuracy.md`](grading-accuracy.md)).

## Judge calibration gate (offline replay)

The precision gate covers the lexical stage. A second offline job covers the
confirmation judge: it re-scores recorded judge outputs against a labeled corpus and
fails when agreement or recall drops below the floor you set. Replay needs no
database, network, or model — the recording is the evidence, and re-running it is the
re-measurement.

```bash
# Record once, next to your judge model and prompt (needs a judge target).
aegis judge-calibration --judge-target "$JUDGE_TARGET" --email ci@example.com \
  --record calibration/judge-run.jsonl

# Replay in CI; this job is cheap and deterministic.
aegis judge-calibration --judge-outputs calibration/judge-run.jsonl \
  --min-judge-accuracy 0.90 --min-judge-recall 0.85 --json
```

`--items FILE` imports a labeled benchmark subset (`.jsonl`, `.json`, or `.csv`;
AdvBench/JailbreakBench/StrongREJECT-style column names are recognized). Labels are
required: prompt-only datasets must be run and labeled before they can calibrate a
judge. See [`judge-calibration.md`](judge-calibration.md) for the schema, the bundled
corpus, and the metrics.

## Security notes

- `database-url` and `secret-key` grant access to your Aegis Vuldris deployment
  (the secret key also decrypts stored target credentials). Always pass them
  as CI secrets, never inline.
- The runner connects directly to your Aegis Vuldris PostgreSQL database. Restrict
  network access to the database to your CI egress ranges, or run a
  self-hosted runner next to the deployment.
- The action mounts the workspace **read-only** so a baseline file can be
  read; Aegis Vuldris writes nothing back to your repository.
- `aegis run` is a real attack run against the configured target. Only point
  it at systems you are authorized to test — creating the target already
  attests that authorization.

## Reference walkthrough

[`examples/quickstart-vulnerable-app/`](../examples/quickstart-vulnerable-app/)
demonstrates the full loop a gate protects: a vulnerable variant leaks under
the direct-instruction-override attack, the `fixed/` variant does not, and
`aegis verify` proves the fix. `docs/patch-workflow.md` documents the same
loop with candidate patches.
