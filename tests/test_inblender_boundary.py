"""The `artlab.inblender` boundary, checked without Blender so it runs on CI.

`src/artlab/inblender/` runs inside Blender only. No host module and no test
imports it in the pytest process (probes in tests/blender_scripts/ do, inside
Blender), and it imports only the stdlib, bpy, mathutils and bpy_extras.
"""

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
INBLENDER = SRC / "artlab" / "inblender"
PROBES = REPO / "tests" / "blender_scripts"
BLENDER_MODULES = {"bpy", "mathutils", "bpy_extras"}
INIT_LINE = (
    '"""Runs inside Blender only: imports the stdlib, bpy, mathutils and bpy_extras."""'
)


def imported(source: str, package: str = "") -> list[str]:
    """What `source` imports, as absolute dotted names.

    `import a.b` gives `a.b`; `from a import b` gives `a.b`, with relative
    imports resolved against `package`; `importlib.import_module("a.b")` and
    `__import__("a.b")` with a literal name give `a.b`. Imports anywhere in the
    file count, inside functions too.
    """
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = []
            if node.level:
                parts = package.split(".") if package else []
                base = parts[: len(parts) - node.level + 1]
            module = ".".join([*base, *([node.module] if node.module else [])])
            names += [f"{module}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else None
            called = func.id if isinstance(func, ast.Name) else called
            first = node.args[0]
            if called in {"import_module", "__import__"} and isinstance(
                first, ast.Constant
            ):
                names.append(str(first.value))
    return names


def is_inblender(name: str) -> bool:
    return name == "artlab.inblender" or name.startswith("artlab.inblender.")


def package_of(path: Path) -> str:
    """The package a file under src/ belongs to, for resolving relative imports."""
    return ".".join(path.relative_to(SRC).parts[:-1])


def test_import_scan_catches_every_form():
    caught = [
        ("import artlab.inblender.testscene", ""),
        ("from artlab.inblender import testscene", ""),
        ("from artlab.inblender.station import build", ""),
        ("from artlab import inblender", ""),
        ("from . import inblender", "artlab"),
        ("from .inblender.testscene import CONTENT", "artlab"),
        ("from .. import inblender", "artlab.sub"),
        ("def f():\n    import artlab.inblender\n", ""),
        ("import importlib\nimportlib.import_module('artlab.inblender')", ""),
    ]
    for source, package in caught:
        assert any(is_inblender(n) for n in imported(source, package)), source
    ignored = [
        ("from artlab.blender import run_blender", ""),
        ("import artlab", ""),
        ("from . import blender", "artlab"),
        ("from . import inblender", "other"),
        ("NAME = 'artlab.inblender'", ""),
    ]
    for source, package in ignored:
        assert not any(is_inblender(n) for n in imported(source, package)), source
    # Relative imports inside the package resolve to it.
    assert imported("from . import station", "artlab.inblender") == [
        "artlab.inblender.station"
    ]


def test_host_and_tests_never_import_inblender():
    host = [p for p in (SRC / "artlab").rglob("*.py") if INBLENDER not in p.parents]
    tests = [p for p in (REPO / "tests").rglob("*.py") if PROBES not in p.parents]
    scanned = {p.relative_to(REPO).as_posix() for p in host + tests}
    assert {
        "src/artlab/cli.py",
        "src/artlab/blender.py",
        "tests/conftest.py",
        "tests/test_station.py",
    } <= scanned, scanned

    offenders = []
    for path in host + tests:
        package = package_of(path) if path.is_relative_to(SRC) else ""
        for name in imported(path.read_text(), package):
            if is_inblender(name):
                offenders.append(f"{path.relative_to(REPO)}: {name}")
    assert not offenders, offenders

    # Collection has imported every test module and the host modules they use.
    assert not [m for m in sys.modules if is_inblender(m)]
    assert "bpy" not in sys.modules


def test_inblender_imports_only_blender_python():
    files = sorted(INBLENDER.rglob("*.py"))
    assert {"__init__.py", "testscene.py", "station.py"} <= {p.name for p in files}
    allowed = set(sys.stdlib_module_names) | BLENDER_MODULES
    offenders = []
    for path in files:
        for name in imported(path.read_text(), package_of(path)):
            if name.split(".")[0] not in allowed and not is_inblender(name):
                offenders.append(f"{path.relative_to(REPO)}: {name}")
    assert not offenders, offenders


def test_inblender_init_is_the_shared_docstring():
    # #11 creates the same file with the same line, so the two merge cleanly.
    init = INBLENDER / "__init__.py"
    assert init.is_file(), f"{init.relative_to(REPO)} does not exist"
    assert init.read_text() == INIT_LINE + "\n"
