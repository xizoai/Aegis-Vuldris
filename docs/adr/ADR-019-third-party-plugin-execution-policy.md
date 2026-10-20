# ADR-019: Third-Party Plugin Execution Policy

**Status:** Accepted — implemented (v1 contracts shipped; sandboxing deferred)
**Date:** 2026-10-17
**Decision Owners:** Aegis Vuldris Maintainers

---

## 1. Decision Summary

Aegis Vuldris is extensible through four **versioned contracts**, discovered through
Python entry points and gated by `PLUGIN_API_VERSION = 1`:

| Group | What it contributes |
|---|---|
| `aegis.graders` | Custom response graders |
| `aegis.report_exporters` | New report formats |
| `aegis.attack_plugins` | Directories of YAML attack cases |
| `aegis.adapters` | Adapter overrides for an existing provider value |

Policy:

- **Community:** third-party plugins are enabled by default
  (`ALLOW_THIRD_PARTY_PLUGINS=true`). A self-hosted operator owns the decision
  to install code; that is a normal open-source trust boundary.
- **Cloud pilot:** `ALLOW_THIRD_PARTY_PLUGINS=false` — only first-party code
  runs in the hosted environment.
- **No sandbox claim.** Plugins execute in-process with the application's
  privileges. Sandboxed third-party execution is deferred and would require
  its own decision.
- **Attacks stay data.** An attack plugin contributes a directory of YAML
  cases; attacks are never imported code.
- **Failures are non-fatal and audited.** A plugin that fails to import,
  declares the wrong contract version, or violates its contract is rejected
  with a clear reason and a `plugin.rejected` audit entry; discovery of the
  remaining plugins continues.

## 2. Context

Extensibility is an adoption lever: security teams have their own graders,
their own report formats, their own attack corpora, and their own gateway
quirks. Without extension points, every such need becomes a core feature
request or a fork.

Extensibility is also a supply-chain surface: a plugin is Python code that
runs in the same process as the engine, with access to everything the process
can reach. The grading pipeline touches model responses, the report pipeline
touches findings and evidence, and the adapter layer performs outbound network
calls under an SSRF policy. A policy that pretends a plugin is sandboxed when
it is not would be exactly the kind of unsupported claim the project's honesty
rules forbid.

Finally, the hosted pilot has a different risk posture than a self-hoster:
the operator runs the code, can read what they install, and answers for it.
The pilot's operator cannot review arbitrary customer-installed code, so the
pilot runs with third-party plugins disabled.

## 3. Decision Drivers

1. **Adoption.** Common extension needs must be satisfiable without core
   changes.
2. **Honest trust model.** The policy must state plainly that plugins are
   trusted code, not sandboxed code.
3. **Pilot safety.** The hosted environment needs a single switch that
   guarantees only first-party code runs.
4. **Stability.** Third-party code must be able to pin against a versioned
   contract.
5. **Auditability.** Operators must be able to see what loaded and what was
   rejected, and why.
6. **Failure containment.** A broken plugin must not take down the platform.

## 4. Decision

### 4.1 Contracts and version gate

Every extension object must expose a `PLUGIN_API_VERSION` equal to the
current contract version (`1`, in `app.services.extensions`). A mismatch is
**rejected with a clear reason** and an audit entry — never loaded on a guess.
The current contract version is bumped only with a documented migration note;
old plugins fail loudly rather than silently misbehaving.

### 4.2 Policy switch

- `ALLOW_THIRD_PARTY_PLUGINS` defaults to `true` in community and `false` in
  the cloud pilot (selected by the edition defaults switch, ADR-016).
- With discovery disabled, only first-party extension objects are used —
  built-in grading, built-in report formats, bundled attack library, built-in
  adapters.

### 4.3 Attacks are data

An `aegis.attack_plugins` extension contributes a `cases_dir` of YAML cases
validated against the test-case schema. The loader never imports attack
content. This keeps the attack surface of the attack library at "parser plus
validator" rather than "arbitrary code".

### 4.4 Grader data boundary

A third-party grader receives **normalized response text and the test config
only** — never credentials, HTTP clients, sessions, or authorization objects.
The engine constructs the grader's inputs; the grader cannot reach beyond
them.

### 4.5 Auditability

Passing a session to discovery records `plugin.loaded` / `plugin.rejected`
audit rows, so operators can see exactly what ran (or was refused) and when.
`aegis doctor` prints a one-line discovered/rejected summary.

### 4.6 Broken plugins are not fatal

An extension that fails to import or violates its contract is reported and
skipped. Discovery continues; the platform stays up.

## 5. What This Policy Does Not Do

- It does not sandbox plugins. Python plugins run in-process with full
  application privileges. Operators who cannot accept that should not enable
  third-party plugins (or should run with the switch off, as the cloud pilot
  does).
- It does not provide a plugin marketplace, signing, or provenance
  attestations. Those would require their own security decision.
- It does not allow adapters for arbitrary new providers. An adapter override
  substitutes an implementation for an existing provider value; new provider
  values remain a core change (a deliberate constraint — provider identity
  drives validation and documentation).

## 6. Implementation Status

**Shipped** (P3 §4.4):

- `backend/app/services/extensions.py` — shared loader for all four groups,
  `PLUGIN_API_VERSION = 1`, policy switch, rejection reasons, audit entries.
- `backend/app/services/report_exporters.py` — report generation dispatches
  unknown formats to discovered exporters and raises a clear error instead of
  silently rendering JSON.
- Adapter overrides — `AdapterRegistry` consults discovered overrides before
  its static registrations.
- Bundled `aegis.attack_plugins` support with schema validation for YAML
  cases.
- `docs/extension-points.md` — the working reference, including the fixture
  plugin.
- `aegis doctor` prints the discovered/rejected plugin summary.
- Tests (11) including the fixture plugin discovered through the real
  `importlib.metadata` machinery, rejection of version mismatches, import
  failures, and contract violations, and the report-exporter dispatch path.

**Deferred:** sandboxed third-party execution; plugin signing/provenance; a
hosted plugin marketplace. Any of these requires a new ADR.

## 7. Consequences

**Positive:**

- Real extension needs are satisfiable without forking or core bloat.
- The cloud pilot has a one-switch guarantee: only first-party code runs.
- Failed/mismatched plugins are visible and loud instead of mysterious.

**Negative:**

- Community operators must understand that installing a plugin is executing
  untrusted-by-default code; the docs say so explicitly.
- No sandbox means the cloud cannot offer third-party plugins in this window;
  a customer requiring one is a product-limits conversation, not a
  configuration change.

## 8. Alternatives Considered

| Alternative | Outcome |
|---|---|
| Directory-based discovery (scan a plugins folder) | Rejected — implicit discovery, no packaging metadata, no version pinning; entry points make installation and versioning explicit. |
| Sandbox plugins for cloud via subprocess/containers | Deferred — significant engineering for a capability no pilot customer has asked for; the disable switch covers the pilot risk now. |
| No extension points (core features only) | Rejected — turns every integration into a fork; extensibility is an adoption lever. |
| Allow arbitrary new provider values via plugins | Rejected — provider identity drives validation, credential handling, and documentation; overrides of existing providers cover the practical gateway cases. |

## 9. References

- [`docs/extension-points.md`](../extension-points.md) — the operational reference for all four contracts.
- [ADR-016](ADR-016-open-core-edition-boundary.md) — `ALLOW_THIRD_PARTY_PLUGINS` as an edition default.
- [`tests/fixtures/plugins/fixture_plugin.py`](../../tests/fixtures/plugins/fixture_plugin.py) — the runnable reference implementation.
