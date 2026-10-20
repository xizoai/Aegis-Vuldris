# Extension Points

Aegis Vuldris is extensible through four **versioned contracts**, all discovered the
same way: Python entry points, loaded by
[`app/services/extensions.py`](../backend/app/services/extensions.py) and
guarded by the rules below. Nothing here introduces a new runtime dependency.

> The working reference implementation of everything on this page is the
> fixture plugin at
> [`tests/fixtures/plugins/fixture_plugin.py`](../tests/fixtures/plugins/fixture_plugin.py),
> which the test suite discovers through the real `importlib.metadata`
> machinery.

## Shared rules

| Rule | Enforcement |
|---|---|
| Contract version | Every extension object must expose `PLUGIN_API_VERSION` equal to `1` (`app.services.extensions.PLUGIN_API_VERSION`). Anything else is **rejected with a clear reason** and an audit entry (`plugin.rejected`), never loaded on a guess. |
| Policy switch | `ALLOW_THIRD_PARTY_PLUGINS=false` disables all discovery (community default: `true`, a self-hosted responsibility; a hosted pilot sets it to `false` so only first-party code runs). |
| Auditability | Pass a session to a `discover_*` call and it records `plugin.loaded` / `plugin.rejected` rows, so operators can see exactly what ran. |
| Broken plugins are not fatal | An extension that fails to import or violates its contract is reported and skipped; discovery of the remaining plugins continues. |

`aegis doctor` prints a one-line summary of discovered/rejected plugins.

## Declaring an extension

In your package's `pyproject.toml`:

```toml
[project.entry-points."aegis.graders"]
my-grader = "my_aegis_plugin:GRADER"
```

Install the package into the same environment as Aegis Vuldris, restart, and the
extension is discovered. The four groups:

| Group | Contract | Use |
|---|---|---|
| `aegis.graders` | A [`ResponseGrader`](#graders) — an object with `grade(response_output, test_config) -> GradingDecision` (or a zero-argument factory returning one) | Custom response evaluation |
| `aegis.report_exporters` | An object with a string `format` and `write_artifact(data, out_dir) -> Path` | New report formats (no change to `report_generation.py` needed) |
| `aegis.attack_plugins` | An object with `cases_dir`: a path to a directory of **YAML attack cases** | New attacks stay data — never imported code |
| `aegis.adapters` | An object with `provider` (an existing provider value) and `factory(credential_resolver=..., client=...) -> BaseTargetAdapter` | Substitute an adapter implementation for a provider |

## Graders

The engine grades every response through
[`ResponseGrader`](../backend/app/services/grading.py) and defaults to the
built-in deterministic keyword/regex grader. A third-party grader receives
**normalized response text and the test config only** — never credentials,
HTTP clients, sessions, or authorization objects — so a grader cannot bypass
those boundaries.

```python
from app.models.execution import ExecutionResult
from app.services.grading import GradingDecision

PLUGIN_API_VERSION = 1

class AlwaysRefuseGrader:
    PLUGIN_API_VERSION = 1
    grader_id = "acme/always-refuse"
    grader_version = "1.0.0"

    def grade(self, response_output: str, test_config: dict | None) -> GradingDecision:
        ...

GRADER = AlwaysRefuseGrader()
```

Grading **never changes fix state**: a finding becomes `fixed` only by a
human claim and `verified` only by a passed verification rerun, regardless of
which grader produced the finding. Keep graders deterministic where possible;
if yours calls a model, say so in its documentation and expect `INCONCLUSIVE`
on failure rather than a guessed verdict.

## Report exporters

```python
from pathlib import Path

PLUGIN_API_VERSION = 1

class CsvReportExporter:
    PLUGIN_API_VERSION = 1
    format = "csv"

    def write_artifact(self, data: dict, out_dir: Path) -> Path:
        ...  # write out_dir / f"report_{data['report_id']}_v{data['report_version']}.csv"
        return path

EXPORTER = CsvReportExporter()
```

Declare it under `aegis.report_exporters`; users then create reports with
`format="csv"` (`POST .../reports` or `aegis export --format csv`) and the
generator calls your exporter. The machine-readable `.data.json` snapshot is
always written first by the generator itself — your exporter only shapes the
human-facing artifact. An **unknown format is now an error** naming the
extension point instead of silently rendering JSON.

## Attack plugins

Attacks are **data, not code**: an attack extension is a directory of YAML
cases in exactly the [test-case schema](test-cases.md), loaded through the
same validating pipeline as the bundled 224-case library (see the
[Attack Plugin Guide](Attack-Plugin-Guide.md) for case authoring). Duplicate
`attack_id`/`version` identities are rejected at load time.

```python
from pathlib import Path

PLUGIN_API_VERSION = 1

class MyAttacks:
    PLUGIN_API_VERSION = 1
    cases_dir = Path(__file__).parent / "cases"

ATTACKS = MyAttacks()
```

## Target adapters

Adapters implement [`BaseTargetAdapter`](../backend/app/adapters/base.py).
A discovered adapter **overrides** the built-in adapter for its provider
value (`openai_compatible`, `ollama`, or `custom_rest`) when registered on an
`AdapterRegistry`; the engine then transparently uses it. The factory receives
the credential resolver — decrypting and using stored credentials remains the
adapter's contract with the platform, and the SSRF/network policy still
applies at connection time.

```python
PLUGIN_API_VERSION = 1

class MyAdapterBundle:
    PLUGIN_API_VERSION = 1
    provider = "openai_compatible"

    @staticmethod
    def factory(*, credential_resolver=None, client=None):
        return MyInstrumentedAdapter(credential_resolver=credential_resolver, client=client)
```

## Versioning

`PLUGIN_API_VERSION` changes only with a breaking contract change, announced
in the changelog and this document together. A plugin written for version N
keeps working until N is retired; on a mismatch Aegis Vuldris tells you exactly
which version it expected.

## Security notes

- Loading third-party code is a **self-hosted responsibility**: community
  installs allow it by default, hosted pilots disable it with
  `ALLOW_THIRD_PARTY_PLUGINS=false`.
- Graders receive no credentials or sessions; exporters receive report data
  (which includes evidence — handle artifacts accordingly); attacks are
  validated data; adapters get exactly the same inputs the built-ins do.
- Rejections and load events are auditable per run when a session is supplied
  to discovery.
