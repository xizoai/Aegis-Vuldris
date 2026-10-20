# Security Policy

## Supported versions

Until the first tagged release, only the latest commit on `main` is
supported. Once releases exist, the latest tagged release is supported and
the release notes state anything older.

## Reporting a vulnerability

**Please do not open a public issue for a vulnerability.**

Use GitHub's private vulnerability reporting on this repository
(Report a vulnerability → Security advisories), or contact a repository
maintainer privately through the GitHub profile associated with the
repository. Include:

- a description of the issue and its impact;
- steps or a proof of concept, ideally against a local deployment;
- the `aegis doctor` output and version if applicable;
- whether you have already disclosed it elsewhere.

## What we commit to

- Acknowledge reports within **7 days**.
- Assess and keep reporters informed of progress; fix confirmed issues
  according to severity.
- Credit reporters in the advisory unless they prefer to remain anonymous.

## Scope

In scope:

- The Aegis Vuldris platform itself: authentication, authorization, credential
  storage, the SSRF/network policy, evidence handling, and anything that lets
  one tenant read another tenant's data.
- The Docker images and compose files as shipped in this repository.

Out of scope:

- Vulnerabilities in AI models *tested with* Aegis Vuldris. The tool reports those
  findings to you; the target model is not this project's software.
- Using Aegis Vuldris against systems you do not own or lack written authorization
  to test. The tool's threat model assumes authorized testing only
  ([`docs/security.md`](docs/security.md)).
- Denial-of-service against the demo applications in `examples/` — they are
  deliberately vulnerable by design and documented as such.
- Reports from automated scanners without a demonstrated impact.

## Security design references

- [`docs/security.md`](docs/security.md) — security principles
- [`docs/security-baseline.md`](docs/security-baseline.md) — security requirements
- [`docs/threat-model.md`](docs/threat-model.md) — threat model
- [`docs/secrets-management.md`](docs/secrets-management.md) — secret handling
