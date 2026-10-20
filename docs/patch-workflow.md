# Applying and validating a candidate patch

A candidate patch is a draft, and a draft is not a fix. This guide covers the part no
tool can do for you — applying the change — and the part that proves it: re-running the
exact attack. It follows the AutoFix levels contract used across Aegis Vuldris:

> Suggestion → draft → **you apply** → you record the claim → the engine re-runs the
> attack → only a **passed rerun** marks the finding `verified`.

Every step below maps to something that exists today. There is no "apply" button, no
automatic commit, and no path by which a model's output can change a finding's state.

## The loop at a glance

| Step | Who | Where |
|---|---|---|
| Draft | You | **View candidate patch** in the workspace, or `POST .../findings/{id}/patches` |
| Review | You | Diff viewer and `.diff` download in the patch panel |
| Apply | You, by hand | Your repository, then your staging deployment |
| Record the claim | You | Finding status → `fixed` |
| Verify | The engine | **Verify fix (re-run attack)**, or `POST .../findings/{id}/verifications` |
| Read the verdict | You | `verified`, or an audit entry saying the attack still reproduces |

## Step 1 — Draft

In the workspace, open the finding and use **View candidate patch**. Two modes exist (see
[`docs/Manual.md`](Manual.md), *Candidate patches*):

- **Template mode** (default) records the deterministic remediation intent. It writes no
  diff on purpose: a diff without comprehension of your code would be a fabricated fix.
- **Model mode** drafts a unified diff from a file you explicitly supply, using an active
  `openai_compatible` or `ollama` target in the same project.

```bash
# Model mode; omit drafting_target_id for template mode
curl -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/assessments/findings/$FINDING_ID/patches \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"drafting_target_id":"<target-uuid>","file_path":"app/handlers.py","file_content":"..."}'
```

## Step 2 — Review the draft

Read the rationale, the files touched, and the diff. A drafted diff is a suggestion from
a model that may have seen only one file; it can be wrong, partial, or stylistically
unlike your codebase. Downloading the `.diff` and opening it in your own review tooling is
encouraged. Nothing in Aegis Vuldris consumes this diff later — the verification step never
looks at it, only at whether the attack still reproduces.

## Step 3 — Apply it yourself, in an isolated environment

Apply the change to a staging copy of the application — not to production, and not with
Aegis Vuldris holding write access anywhere. The tool's role ends at the draft; the change and
its review (your normal code review, your normal pipeline) stay yours.

For a local check, [`examples/quickstart-vulnerable-app/`](../examples/quickstart-vulnerable-app/README.md)
ships a scripted demo app whose `fixed/` variant *is* the applied change, so the whole
loop runs on loopback with no API key:

```bash
# the before
cd examples/quickstart-vulnerable-app && python -m uvicorn app:app --host 127.0.0.1 --port 8101

# the after
cd examples/quickstart-vulnerable-app/fixed && python -m uvicorn app:app --host 127.0.0.1 --port 8101
```

Loopback endpoints need `ALLOW_LOCAL_TARGETS=true` (development only; deployments should
leave it `false`).

## Step 4 — Point a staging target at the applied change

Verification re-runs the attack through the test that produced the finding. By default it
re-uses the original target; to verify a fixed deployment, name a target in the same
project:

- it must be **active**,
- it must match the original test's provider and capabilities, and
- it is the deployment where you applied the change.

```bash
# Record the claim: you applied the change. Only 'fixed' can be verified.
curl -X PATCH http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/assessments/findings/$FINDING_ID \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"fixed"}'

# Start the rerun against the staging deployment (202 Accepted).
# Omit target_id to re-run against the same target as the original finding.
curl -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/assessments/findings/$FINDING_ID/verifications \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"target_id":"<staging-target-uuid>"}'
```

The UI offers the same flow: set **Fix state** to `fixed (applied, unverified)`, then
**Verify fix (re-run attack)**.

## Step 5 — Read the verdict

Only the engine's rerun can move the finding:

- **Passed** (`pass`) — the finding moves `fixed → verified` and the
  audit trail records `finding.verification_passed` with the execution id.
  (`no_findings` on historical rows counts as a pass.)
- **Failed** — the attack still reproduces (a confirmed finding). The finding
  stays `fixed`; `finding.verification_failed` is recorded. The claim did not
  survive contact with the rerun.
- **Inconclusive or needs review** — grading could not run, or a pattern
  matched and nothing confirmed it. Nothing is verified and
  `finding.verification_inconclusive` is recorded; an unproven fix is not a
  verified one.

Only a finding currently marked `fixed` is accepted; `verified` cannot be set by hand and
the UI does not offer it.

**What a pass means, precisely:** *this* attack, as defined by the test, no longer
reproduces against the target that was verified. It is not a statement that every path to
the flaw is closed, that the change was correct, or that the deployment is otherwise
safe.

## The offline walkthrough, run in CI

The loop above is executed exactly as written by
[`tests/integration/test_quickstart_demo.py`](../tests/integration/test_quickstart_demo.py):
it starts both demo variants under uvicorn on loopback, drives the real engine over real
HTTP (including the outbound network policy), drafts a template proposal, marks the
finding fixed, and verifies against the fixed variant. It is marked `slow` because it
binds ports; it needs no network beyond loopback:

```bash
pytest tests/integration/test_quickstart_demo.py -q
```

## The CLI

An `aegis verify <finding>` command — the same verification service, scriptable from CI —
arrives with the `aegis` CLI workstream. Until it lands, use the UI action or the API
route above; both call the identical service.
