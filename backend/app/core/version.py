"""The application version, single-sourced from the installed package.

The version lives in ``pyproject.toml`` and reaches the running app through
the installed distribution metadata. Refusing to start when the package is
not installed is deliberate: a hardcoded copy in the source would let
``/system/info`` report a stale version after a bump, which is exactly what
the release process promises cannot happen.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    APP_VERSION = _distribution_version("aegis-vuldris")
except PackageNotFoundError as exc:  # pragma: no cover - requires an uninstalled tree
    raise RuntimeError(
        "The aegis-vuldris package is not installed in this environment. Install it "
        "with `pip install .` (see docs/development.md) so the reported version "
        "is the real one, not a hardcoded copy."
    ) from exc

__all__ = ["APP_VERSION"]
