"""The `artlab` command line, run as a real process with the test interpreter."""

import subprocess
import sys
import sysconfig
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, check=False, capture_output=True, text=True, timeout=60
    )


def test_version_prints_package_version(tmp_path):
    # cwd is an unrelated dir, so the installed package is used, not ./src.
    result = run([sys.executable, "-m", "artlab", "--version"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "artlab 0.1.0"


def test_console_script_prints_version(tmp_path):
    # `uv run artlab --version`: the console script installed next to the interpreter.
    script = Path(sysconfig.get_path("scripts")) / "artlab"
    assert script.is_file(), f"no artlab console script at {script}"
    result = run([str(script), "--version"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "artlab 0.1.0"


def test_no_command_prints_usage_and_exits_2(tmp_path):
    result = run([sys.executable, "-m", "artlab"], tmp_path)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "usage:" in result.stderr.lower()
    assert "artlab" in result.stderr
    assert result.stdout == ""
