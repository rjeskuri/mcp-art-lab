<!--
Maintainer notes (HTML comments are stripped before Claude sees this file, so they cost no context).
Scaffolded by harness-scaffold (none, 2026). Keep it short: only what Claude cannot infer
from the code. The loop's rules (board, branches, tests first) live in ~/.claude/CLAUDE.md and the
hooks, not here. When Claude makes the same mistake twice, add one line here.
-->

# mcp-art-lab

A lab for exploring 3D, 2.5D and pixel-sprite art styles in Blender, driven by Claude through the Blender MCP; output is renders for the owner to judge by eye, and "correct" means a style script rebuilds the same scene every run.

## Commands
- Verify, the whole suite plus lint (CI runs the same): `scripts/verify.sh`
- The style lab CLI: `uv run artlab` (`uv run artlab --help` lists its commands)

## Where things live
- `scripts/verify.sh`: the checks behind the verify command; `.github/workflows/ci.yml` runs it.
- `.githooks/`: `pre-commit` (format and lint on staged files, no commits on main) and `pre-push` (no pushes to main, no force pushes).
- `src/artlab/`: the `artlab` package; `cli.py` is the command line, `blender.py` finds Blender (`ARTLAB_BLENDER`, else PATH) and runs scripts in it headless.

## Gotchas
- Blender MCP (`.mcp.json`, `mcp-for-blender==2.0.0`, telemetry off, `BLENDER_MCP_SAFE_MODE=1`) needs Blender open with the add-on's server started: 3D viewport, N sidebar, MCP for Blender tab, Start MCP Server (port 9876).
- Poly Haven access is a per-scene flag (`scene.blendermcp_use_polyhaven`), not a preference: tick it in the sidebar, or have a style script set it.
- The add-on lives outside the repo at `~/Library/Application Support/Blender/5.3/scripts/addons/blender_mcp.py`; reinstall it with `BLENDERMCP_ADDONS_DIR=<that dir> uvx mcp-for-blender==2.0.0 install-addon` when bumping the pinned version.
- Blender ignores `PYTHONPATH`: `import artlab` in a Blender script works because `run_blender` puts `src/` on `sys.path` before the script runs, so launch Blender through it, not by hand.
