# Aegis Vuldris Data Retention and Evidence Handling

What Aegis Vuldris stores, how sensitive it is, and how long it is kept.

## Why this document exists

A security assessment stores the prompts it sent and the responses it got back.
For a data-leakage test, that response *is* the sensitive payload: it is the
moment a model disclosed something it should not have.

Storing those responses verbatim, unlabelled, means the tool accumulates the
very secrets it discovered, with no way to apply a different policy to them.
Aegis Vuldris therefore classifies evidence when it is written, and redacts detected
credential values before they reach the database.

## Evidence sensitivity levels

| Level | Meaning |
|---|---|
| `0` PUBLIC | Nothing sensitive detected. Safe to show anywhere. |
| `1` INTERNAL | Default. Assessment content with no detected credentials or personal data. |
| `2` CONFIDENTIAL | Contains personal data (email, phone, national id). |
| `3` RESTRICTED | Contains a credential: API key, password, private key, or payment card. |

Classification is derived at write time from what the scanner found, and stored
on the record alongside the kinds detected. It is not a guess applied later, so
a policy change does not require re-scanning historical rows.

## What is redacted

Detected credentials are replaced with a keyed placeholder:

```
[REDACTED:api_key:9f2c1a7b4e6d8035]
```

The suffix is an HMAC-SHA256 of the value, keyed with `SECRET_KEY` and truncated
to 16 hex characters. That gives two properties:

- **Proof survives.** Two disclosures of the same secret produce the same
  fingerprint, so an assessment can show that the same credential leaked twice,
  or that a fix actually worked.
- **The secret does not.** The value is not recoverable from the database. The
  keying prevents an attacker holding the database from confirming a guessed
  secret by recomputing the hash; the truncation prevents brute-forcing a short
  one.

Personal data is redacted the same way, and can be disabled per project.

### Detection is deliberately high-precision

A red-team tool that flagged ordinary prose would be unusable, so patterns are
anchored on structure — a known vendor prefix, a PEM header, a
`password = value` assignment — rather than a bare keyword. "The password field
is required" is not a finding. Detection runs against model output that
frequently contains security language by nature, so a loose rule would mark most
evidence `RESTRICTED` and make the classification useless.

Redaction can be disabled per project for cases where the exact bytes matter to
an investigation. **Classification still happens when redaction is off**, so
turning redaction off does not silently unlabel the evidence.

## Where this applies

| Data | Redacted | Classified | Notes |
|---|---|---|---|
| Evidence content (model request/response) | Yes | Yes | At write time |
| Report artifacts (JSON/Markdown) | Yes, by inheritance | Labelled | Generated from stored evidence |
| Findings | No | Via their evidence | A finding title is not itself sensitive |
| Audit log entries | N/A | N/A | Counts and IDs only; never evidence content |
| Target credentials | Encrypted (Fernet) | N/A | Never stored in plaintext anywhere |

Report downloads are served with `Cache-Control: no-store` so evidence does not
linger in shared or browser caches.

Viewing evidence emits an `evidence.viewed` audit event carrying the record
count and how many were restricted. The event never contains evidence content.

## Retention

Each project declares how long its evidence and report artifacts are kept, in
`projects.evidence_retention_days`. The default is **90 days**. A value of `0`
means keep indefinitely, for operators who arrange their own deletion.

A cleanup pass removes what has aged past each project's window:

```bash
# From the repository root
python -m app.cli.retention --dry-run     # report what would go, delete nothing
python -m app.cli.retention --json        # machine-readable result
python -m app.cli.retention               # perform the purge
```

Retention only works if something runs it. Schedule it with a systemd timer or a
Kubernetes CronJob; it is idempotent, so a second run over the same data removes
nothing. Each pass that removes anything writes an `evidence.retention_purged`
audit event with the counts.

A concrete daily schedule (a host cron entry; a systemd timer or Kubernetes
CronJob is equivalent):

```cron
# /etc/cron.d/aegis-retention
# Purge evidence past each project's window once a day at 03:15.
15 3 * * * root cd /opt/aegis && docker compose -f docker-compose.production.yml \
  exec -T backend python -m app.cli.retention --json >> /var/log/aegis-retention.log 2>&1
```

Run `--dry-run` once by hand before enabling the schedule, so the first live run
does not surprise you.

### What the window applies to

- **Evidence rows** — the prompts and responses. This is the sensitive payload.
- **Report artifacts** — the generated files on the report volume.

It does **not** apply to findings or to the report rows themselves. A finding is
the assessment result; deleting it because its supporting evidence aged out would
throw away the answer while keeping the metadata. An expired report keeps its
row as a record of what was produced, with `path` cleared so a stale download
cannot be served and re-generation is unambiguous.

### Secure deletion is not guaranteed

Deleting a file from the report volume is an unlink, not a secure erase. On
copy-on-write filesystems and SSDs, the old blocks may persist. Guaranteeing
otherwise needs volume encryption with key destruction, which is a deployment
concern. Database rows are removed through a normal transaction.

If you need a hard guarantee, encrypt the report volume and destroy the volume
key when you want the data unrecoverable.

## Operational note: encrypted volumes

Report artifacts are written to `AEGIS_REPORT_DIR`, which should be an
**encrypted volume** in production. Aegis Vuldris does not encrypt the volume itself —
that is the platform's responsibility, and the production Compose file mounts it
as a named volume so it can be backed by encrypted storage.

The same applies to database backups. See `docs/secrets-management.md` for the
`SECRET_KEY` rotation procedure, which invalidates stored credentials and must
be coordinated with a backup that still holds the old key.

## Verifying

```powershell
pytest tests/services/test_redaction.py tests/services/test_evidence_redaction.py tests/services/test_retention.py tests/api/test_evidence_handling.py
```

Covers detection precision, redaction of secrets and PII, fingerprint stability,
classification at each level, that the secret is absent from both the returned
object and the stored row, that redaction can be disabled without unlabelling,
that viewing evidence is audited, and the retention window: what is removed,
what survives, project scoping, idempotency, and that a dry run deletes
nothing.
