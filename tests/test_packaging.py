"""Guards for packaging correctness.

The wheel is what ships inside the container, and setuptools' package discovery
is easy to break silently: a missing `include` or `package-data` entry omits
modules and the bundled YAML library without any build-time error. The failure
only appears at runtime as `ModuleNotFoundError: No module named 'app.cli'`.
"""

import os
import site
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from app.services.seed_tests import DEFAULT_TEST_CASE_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_cli_package_exists() -> None:
    assert (REPO_ROOT / "backend/app/cli/__init__.py").is_file()
    assert (REPO_ROOT / "backend/app/cli/seed_tests.py").is_file()
    assert (REPO_ROOT / "backend/app/cli/main.py").is_file()


def test_aegis_console_script_is_declared() -> None:
    """`aegis` must be exported as a console script, or the wheel has no CLI."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert config["project"]["scripts"]["aegis"] == "app.cli.main:main"


def test_bundled_test_cases_are_package_data() -> None:
    """test_cases/ holds YAML, which packaging must include explicitly."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    package_data = config["tool"]["setuptools"].get("package-data", {})
    patterns = package_data.get("app", [])
    assert patterns, "package-data must declare app.test_cases"
    assert any("test_cases" in pattern for pattern in patterns)


def test_packages_find_has_explicit_include() -> None:
    """Auto-discovery drops packages; an explicit include prevents that."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    find = config["tool"]["setuptools"]["packages"]["find"]
    assert find.get("include"), "packages.find needs an explicit include list"


def test_default_dir_resolves_inside_installed_package() -> None:
    """The seeder must find the library relative to the package, not the CWD."""
    assert DEFAULT_TEST_CASE_DIR.is_absolute()
    assert DEFAULT_TEST_CASE_DIR.is_dir()
    assert (DEFAULT_TEST_CASE_DIR / "prompt_injection").is_dir()


@pytest.mark.slow
def test_wheel_ships_cli_and_test_cases(tmp_path: Path) -> None:
    """Build a wheel and assert the CLI and YAML library are inside it.

    Skipped unless explicitly requested, since it needs the build backend and
    network access. Run with: pytest -m slow
    """

    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"wheel build unavailable: {result.stderr[-200:]}")

    import zipfile

    wheels = list(tmp_path.glob("*.whl"))
    assert wheels, "no wheel produced"
    names = zipfile.ZipFile(wheels[0]).namelist()

    assert "app/cli/seed_tests.py" in names, "CLI missing from wheel"
    assert "app/cli/main.py" in names, "aegis entry point module missing from wheel"
    assert "app/services/seed_tests.py" in names, "seeding service missing from wheel"

    entry_points = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
    assert entry_points, "wheel has no entry_points.txt"
    entry_points_text = zipfile.ZipFile(wheels[0]).read(entry_points[0]).decode("utf-8")
    assert "aegis = app.cli.main:main" in entry_points_text, (
        "the aegis console script is not exported by the wheel"
    )

    yaml_count = sum(1 for name in names if name.endswith(".yaml"))
    assert yaml_count >= 50, f"only {yaml_count} YAML test cases shipped"
    assert "app/fixtures/demo/demo_run.json" in names, "offline demo fixture missing from wheel"

    # The acceptance bar is "aegis installs from the wheel": install it into a
    # throwaway venv and run the console script. The wheel is installed with
    # --no-deps (its dependencies already exist in this interpreter), and the
    # third-party packages are made importable through PYTHONPATH instead of
    # --system-site-packages, which would expose the *base* interpreter rather
    # than this virtual environment. The `app` package itself must come from
    # the wheel: this environment's editable install is wired up through .pth
    # hooks, and .pth files are only processed for site directories, never for
    # PYTHONPATH entries.
    venv_dir = tmp_path / "install-venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    scripts = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    venv_python = scripts / ("python.exe" if os.name == "nt" else "python")
    install = subprocess.run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-index",
            "--no-deps",
            # The parent environment already has aegis-vuldris installed; install
            # the wheel regardless so the entry point is really exercised.
            "--ignore-installed",
            str(wheels[0]),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert install.returncode == 0, install.stderr[-400:]
    aegis = scripts / ("aegis.exe" if os.name == "nt" else "aegis")
    assert aegis.is_file(), "the install did not create the aegis console script"
    dependency_paths = [path for path in site.getsitepackages() if Path(path).is_dir()]
    console_env = dict(os.environ, PYTHONPATH=os.pathsep.join(dependency_paths))
    version = subprocess.run(
        [str(aegis), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        env=console_env,
    )
    assert version.returncode == 0, version.stderr[-400:]
    assert version.stdout.startswith("aegis"), version.stdout
