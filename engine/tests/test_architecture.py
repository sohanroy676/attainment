"""A16: the engine is pure. No Django, no database, no floats in the calculation path."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ENGINE = Path(__file__).resolve().parent.parent
FORBIDDEN = ("django", "psycopg", "apps", "config")


def _sources() -> list[Path]:
    return [p for p in ENGINE.rglob("*.py") if "tests" not in p.parts]


def test_a16_engine_imports_nothing_from_django_or_the_apps() -> None:
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN, f"{path.name} imports {name}"


def test_a16_importing_and_running_the_engine_does_not_load_django() -> None:
    code = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import engine.pipeline, engine.__main__\n"
        "assert 'django' not in sys.modules, 'django was imported'\n"
    )
    done = subprocess.run(  # noqa: S603 - fixed arguments, our own interpreter
        [sys.executable, "-I", "-c", code, str(ENGINE.parent)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr


def test_no_float_in_the_calculation_path() -> None:
    """No float() calls or float literals in engine code (JSON numbers are read as Decimal)."""
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                pytest.fail(f"{path.name}:{node.lineno} has a float literal")
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "float":
                pytest.fail(f"{path.name}:{node.lineno} calls float()")
