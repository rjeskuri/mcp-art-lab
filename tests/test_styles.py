"""`artlab.styles.discover` and the `artlab styles` command (#5).

None of these need Blender: style dirs are made in tmp_path, and the command runs
with ARTLAB_BLENDER unset and PATH an empty dir, so they run on CI. A style is a
subdirectory whose name matches `^[a-z][a-z0-9_-]*$` and that holds `build.py`.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# (tree entries, the styles discover must find, in name order). An entry ending
# in "/" is a directory; anything else is a file.
TICKET_TREE = (
    ["a/build.py", "b/", "Bad Name/build.py", "_wip/build.py", "c/build.py"],
    ["a", "c"],
)
VARIED_TREE = (
    [
        "zeta-9/build.py",
        "m_x/build.py",
        "q/build.py",
        "9lead/build.py",  # starts with a digit
        "Upper/build.py",  # upper case
        "-dash/build.py",  # starts with a dash
        "dot.name/build.py",  # a dot
        "has space/build.py",
        ".hidden/build.py",
        "nested/sub/build.py",  # build.py one level too deep
        "other/style.py",  # no build.py
        "loose",  # a file, not a directory
        "build.py",  # at the top, not in a style dir
    ],
    ["m_x", "q", "zeta-9"],
)


@pytest.fixture
def discover():
    from artlab.styles import discover

    return discover


def make_tree(root: Path, entries: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        path = root / entry
        if entry.endswith("/"):
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def build(scene):\n    pass\n")


def no_blender_env(tmp_path: Path) -> dict[str, str]:
    empty = tmp_path / "empty-path"
    empty.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "ARTLAB_BLENDER"}
    env["PATH"] = str(empty)
    return env


def run_styles(args: list[str], cwd: Path, env: dict[str, str]):
    return subprocess.run(
        [sys.executable, "-m", "artlab", "styles", *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    ("entries", "names"), [TICKET_TREE, VARIED_TREE], ids=["ticket", "varied"]
)
def test_discover_finds_style_dirs_with_build_py(tmp_path, discover, entries, names):
    root = tmp_path / "styles"
    make_tree(root, entries)

    found = discover(root)

    assert isinstance(found, dict)
    assert list(found) == names  # name order
    assert found == {name: root / name / "build.py" for name in names}
    assert all(isinstance(path, Path) for path in found.values())


def test_discover_missing_dir_returns_empty(tmp_path, discover):
    assert discover(tmp_path / "absent") == {}
    empty = tmp_path / "empty"
    empty.mkdir()
    assert discover(empty) == {}
    no_styles = tmp_path / "no-styles"
    make_tree(no_styles, ["Bad/build.py", "_wip/build.py", "x/notes.txt"])
    assert discover(no_styles) == {}


@pytest.mark.parametrize(
    ("entries", "names"), [TICKET_TREE, VARIED_TREE], ids=["ticket", "varied"]
)
def test_styles_command_lists_names(tmp_path, entries, names):
    root = tmp_path / "some styles"
    make_tree(root, entries)

    result = run_styles(["--styles-dir", str(root)], tmp_path, no_blender_env(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == names


def test_styles_command_prints_plain(tmp_path):
    env = no_blender_env(tmp_path)

    # `uv run artlab styles` in the repo: --styles-dir defaults to ./styles.
    in_repo = run_styles([], REPO, env)
    assert in_repo.returncode == 0, in_repo.stderr
    assert "plain" in in_repo.stdout.splitlines()

    # The default is relative to the cwd, not to the repo.
    make_tree(tmp_path / "styles", ["zed/build.py"])
    elsewhere = run_styles([], tmp_path, env)
    assert elsewhere.returncode == 0, elsewhere.stderr
    assert elsewhere.stdout.splitlines() == ["zed"]
