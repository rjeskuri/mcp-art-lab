"""Locate Blender and run Python scripts in it headless."""

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

ENV_VAR = "ARTLAB_BLENDER"
OUTPUT_TAIL_LINES = 60

# The `src/` dir holding this package. Blender ignores PYTHONPATH, so run_blender
# puts this on sys.path before the script runs.
SRC_DIR = Path(__file__).resolve().parents[1]


class BlenderNotFound(RuntimeError):
    """No usable Blender executable, or ARTLAB_BLENDER names a bad one."""


class BlenderError(RuntimeError):
    """Blender exited non-zero or timed out; `output` is the tail of its output."""

    def __init__(self, message: str, returncode: int | None, output: str) -> None:
        super().__init__(f"{message}\n{output}" if output else message)
        self.returncode = returncode
        self.output = output


def find_blender() -> Path | None:
    """$ARTLAB_BLENDER when set, else `blender` on PATH, else None."""
    configured = os.environ.get(ENV_VAR)
    if configured:
        path = Path(configured)
        if not (path.is_file() and os.access(path, os.X_OK)):
            raise BlenderNotFound(
                f"{ENV_VAR}={configured!r} is not an executable file; "
                f"point it at the Blender binary or unset it"
            )
        return path
    found = shutil.which("blender")
    return Path(found) if found else None


def blender_skip_reason() -> str | None:
    """None when Blender is found, else why tests that need it are skipped."""
    if find_blender() is not None:
        return None
    return f"Blender not found (set {ENV_VAR} or put blender on PATH)"


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _tail(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    lines = (_text(stdout) + _text(stderr)).splitlines()
    return "\n".join(lines[-OUTPUT_TAIL_LINES:])


def run_blender(
    script: Path, args: Sequence[str] = (), *, timeout: float = 600.0
) -> subprocess.CompletedProcess[str]:
    """Run `script` in Blender headless, with `args` after `--` in sys.argv."""
    blender = find_blender()
    if blender is None:
        raise BlenderNotFound(blender_skip_reason())
    cmd = [
        str(blender),
        "-b",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python-expr",
        f"import sys; sys.path.insert(0, {str(SRC_DIR)!r})",
        "--python",
        str(script),
        "--",
        *args,
    ]
    try:
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise BlenderError(
            f"Blender timed out after {timeout:g}s running {script}",
            None,
            _tail(exc.stdout, exc.stderr),
        ) from exc
    if result.returncode != 0:
        raise BlenderError(
            f"Blender exited {result.returncode} running {script}",
            result.returncode,
            _tail(result.stdout, result.stderr),
        )
    return result
