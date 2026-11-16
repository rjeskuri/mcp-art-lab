"""Repository hygiene: renders, downloaded assets and .blend files stay out of git."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_gitignore_covers_renders_assets_and_blend_files():
    paths = ["renders/x.png", "assets/x.hdr", "scene.blend", "scene.blend1"]
    result = subprocess.run(
        ["git", "check-ignore", *paths],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    matched = set(result.stdout.split())
    assert matched == set(paths), f"not ignored: {sorted(set(paths) - matched)}"
    # A source file must stay tracked, so a blanket ignore cannot pass.
    probe = subprocess.run(
        ["git", "check-ignore", "-q", "src/artlab/cli.py"],
        cwd=REPO,
        check=False,
        timeout=30,
    )
    assert probe.returncode == 1
