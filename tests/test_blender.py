"""artlab.blender: locating Blender and running scripts in it headless.

Tests marked `blender` launch the real Blender once each; the rest use shell
stubs in tmp_path, so they run on CI where there is no Blender.
"""

import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from artlab.blender import (
    BlenderError,
    BlenderNotFound,
    blender_skip_reason,
    find_blender,
    run_blender,
)

REPO = Path(__file__).resolve().parents[1]


def make_exe(path: Path, body: str = "exit 0\n", mode: int = 0o755) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(mode)
    return path


def same(a: Path | None, b: Path) -> bool:
    return a is not None and Path(a).resolve() == b.resolve()


@pytest.fixture
def no_blender(tmp_path, monkeypatch):
    """No ARTLAB_BLENDER and an empty PATH."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.delenv("ARTLAB_BLENDER", raising=False)
    monkeypatch.setenv("PATH", str(empty))
    return empty


# --- run_blender against the real Blender (broad behavior) -------------------

PROBE_ARGS = """\
import json
import sys

import artlab
import bpy

after = sys.argv[sys.argv.index("--") + 1 :]
with open(after[0], "w") as fh:
    json.dump(
        {
            "after": after,
            "version": artlab.__version__,
            "artlab_file": artlab.__file__,
            "blender": bpy.app.version_string,
            "background": bpy.app.background,
        },
        fh,
    )
"""


@pytest.mark.blender
def test_run_blender_passes_args_and_imports_artlab(tmp_path):
    script = tmp_path / "probe_args.py"
    script.write_text(PROBE_ARGS)
    out = tmp_path / "out.json"
    token = secrets.token_hex(4)
    args = [str(out), f"alpha-{token}", "two words", "--flag=3", "-x", ""]

    result = run_blender(script, args)

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0
    data = json.loads(out.read_text())
    assert data["after"] == args
    assert data["version"] == "0.1.0"
    # artlab is imported from this repo's src/, not from some other install.
    assert Path(data["artlab_file"]).resolve().is_relative_to(REPO / "src" / "artlab")
    assert re.match(r"^\d+\.\d+", data["blender"]), data["blender"]
    assert data["background"] is True


@pytest.mark.blender
def test_run_blender_raises_with_traceback_on_script_error(tmp_path):
    message = f"boom-1234-{secrets.token_hex(4)}"
    script = tmp_path / "probe_error.py"
    script.write_text(f"raise RuntimeError({message!r})\n")

    with pytest.raises(BlenderError) as excinfo:
        run_blender(script)

    err = excinfo.value
    assert err.returncode is not None and err.returncode != 0
    assert "boom-1234" in str(err)
    assert message in str(err)
    assert "RuntimeError" in str(err)
    assert message in err.output


# --- find_blender -------------------------------------------------------------


def test_find_blender_prefers_env_var(tmp_path, monkeypatch):
    on_path = make_exe(tmp_path / "bin" / "blender")
    env_stub = make_exe(tmp_path / "custom" / "my-blender-5")
    monkeypatch.setenv("PATH", str(on_path.parent))
    monkeypatch.setenv("ARTLAB_BLENDER", str(env_stub))

    found = find_blender()

    assert isinstance(found, Path)
    assert same(found, env_stub)
    assert not same(found, on_path)


def test_find_blender_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.delenv("ARTLAB_BLENDER", raising=False)
    first = make_exe(tmp_path / "a" / "blender")
    second = make_exe(tmp_path / "b" / "blender")
    # A non-executable `blender` earlier on PATH does not count.
    make_exe(tmp_path / "noexec" / "blender", mode=0o644)

    for path_dirs, expected in [
        ([first.parent], first),
        ([second.parent], second),
        ([tmp_path / "noexec", second.parent, first.parent], second),
    ]:
        monkeypatch.setenv("PATH", os.pathsep.join(str(d) for d in path_dirs))
        found = find_blender()
        assert isinstance(found, Path), path_dirs
        assert same(found, expected), (path_dirs, found)


def test_find_blender_returns_none_when_absent(no_blender):
    assert find_blender() is None


def test_find_blender_rejects_bad_env_var(tmp_path, monkeypatch):
    # A valid blender on PATH must not hide a bad ARTLAB_BLENDER.
    make_exe(tmp_path / "bin" / "blender")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    not_executable = make_exe(tmp_path / "plain.txt", mode=0o644)
    a_directory = tmp_path / "a-directory"
    a_directory.mkdir()

    for bad in [tmp_path / "missing" / "blender", not_executable, a_directory]:
        monkeypatch.setenv("ARTLAB_BLENDER", str(bad))
        with pytest.raises(BlenderNotFound) as excinfo:
            find_blender()
        assert "ARTLAB_BLENDER" in str(excinfo.value), bad


# --- run_blender with stubs (runs on CI) --------------------------------------


def test_run_blender_raises_when_absent(no_blender, tmp_path, monkeypatch):
    script = tmp_path / "never.py"
    script.write_text("print('should not run')\n")

    def no_process(*args, **kwargs):
        raise AssertionError(f"a process was started: {args!r}")

    monkeypatch.setattr(subprocess, "Popen", no_process)
    with pytest.raises(BlenderNotFound):
        run_blender(script, ["x"])


def test_run_blender_invokes_stub_headless_with_args_after_double_dash(
    tmp_path, monkeypatch
):
    argv_file = tmp_path / "argv.bin"
    token = secrets.token_hex(4)
    stub = make_exe(
        tmp_path / "bin" / "fake-blender",
        f"printf '%s\\0' \"$@\" > '{argv_file}'\necho stub-out-{token}\nexit 0\n",
    )
    monkeypatch.setenv("ARTLAB_BLENDER", str(stub))
    script = tmp_path / "scene script.py"
    script.write_text("pass\n")
    args = [f"one-{token}", "two words", "--three"]

    result = run_blender(script, args)

    assert result.returncode == 0
    assert f"stub-out-{token}" in result.stdout
    argv = argv_file.read_bytes().split(b"\0")[:-1]
    argv = [a.decode() for a in argv]
    assert "-b" in argv or "--background" in argv
    dash = argv.index("--")
    assert argv[dash + 1 :] == args
    before = argv[:dash]
    assert str(script) in before
    assert before[before.index(str(script)) - 1] == "--python"


def test_run_blender_raises_with_output_tail_on_nonzero_exit(tmp_path, monkeypatch):
    token = secrets.token_hex(4)
    stub = make_exe(
        tmp_path / "bin" / "fake-blender",
        "i=0\n"
        "while [ $i -lt 200 ]; do printf 'out-%03d\\n' $i; i=$((i+1)); done\n"
        f"echo stub-err-{token} >&2\n"
        "exit 3\n",
    )
    monkeypatch.setenv("ARTLAB_BLENDER", str(stub))
    script = tmp_path / "s.py"
    script.write_text("pass\n")

    with pytest.raises(BlenderError) as excinfo:
        run_blender(script)

    err = excinfo.value
    assert err.returncode == 3
    assert f"stub-err-{token}" in str(err)
    assert "out-199" in err.output and "out-199" in str(err)
    # Only the tail is kept.
    assert "out-000" not in err.output


def test_run_blender_raises_on_timeout(tmp_path, monkeypatch):
    stub = make_exe(tmp_path / "bin" / "fake-blender", "exec sleep 30\n")
    monkeypatch.setenv("ARTLAB_BLENDER", str(stub))
    script = tmp_path / "s.py"
    script.write_text("pass\n")

    with pytest.raises(BlenderError) as excinfo:
        run_blender(script, timeout=1.0)

    assert excinfo.value.returncode is None


# --- blender_skip_reason and the conftest skip --------------------------------


def test_skip_reason_names_the_fix(tmp_path, monkeypatch, no_blender):
    reason = blender_skip_reason()
    assert isinstance(reason, str)
    assert "ARTLAB_BLENDER" in reason

    make_exe(no_blender / "blender")
    assert blender_skip_reason() is None

    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    monkeypatch.setenv("ARTLAB_BLENDER", str(make_exe(tmp_path / "other" / "b")))
    assert blender_skip_reason() is None


def run_inner_pytest(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run only this file's `blender` tests in a child pytest with `env`."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(Path(__file__).resolve()),
            "-m",
            "blender",
            "-ra",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(REPO),
        ],
        cwd=REPO,
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_blender_tests_skip_with_reason_when_absent(tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "ARTLAB_BLENDER"}
    env["PATH"] = str(empty)

    result = run_inner_pytest(env)
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "2 skipped" in output, output
    assert "Blender not found (set ARTLAB_BLENDER or put blender on PATH)" in output
    assert "passed" not in output and "failed" not in output, output


def test_bad_env_var_fails_the_run_instead_of_skipping(tmp_path):
    env = dict(os.environ)
    env["ARTLAB_BLENDER"] = str(tmp_path / "no-such-blender")

    result = run_inner_pytest(env)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "ARTLAB_BLENDER" in output
    assert "skipped" not in output, output
