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
- Styles: `uv run artlab styles` lists them; `uv run artlab render (STYLE ... | --all) [--camera iso|hero|all] [--size N] [--no-render] [--save-blend]` writes `renders/<style>/manifest.json` and `iso.png`/`hero.png` (1024 px square) and prints each path; exit 1 when a style fails or changes content, 2 on usage errors or no Blender
- Contact sheet: `uv run artlab sheet [STYLE ...] [--camera iso|hero|all]` writes `renders/contact-sheet.png` (styles as columns, iso then hero rows) and prints its path

## Where things live
- `scripts/verify.sh`: the checks behind the verify command; `.github/workflows/ci.yml` runs it.
- `.githooks/`: `pre-commit` (format and lint on staged files, no commits on main) and `pre-push` (no pushes to main, no force pushes).
- `src/artlab/`: the `artlab` package; `cli.py` is the command line, `blender.py` finds Blender (`ARTLAB_BLENDER`, else PATH) and runs scripts in it headless, `styles.py` discovers styles and `render.py` runs one through `inblender/runner.py`.
- `src/artlab/inblender/`: code that runs inside Blender only (`testscene.py` builds the shared test scene from `station.py`, `train.py` and `people.py`, `cameras.py` adds its `iso` and `hero` cameras, and `runner.py` applies a style, refuses content changes, writes the manifest and renders each camera). It imports only the stdlib, `bpy`, `mathutils`, `bpy_extras` and itself; host modules and tests never import it in the pytest process, only probe scripts under `tests/blender_scripts/` launched through `run_blender`.
- `styles/<name>/build.py`: one style each, a `build(scene)` run in Blender after the test scene is built; it may change materials, modifiers, lights, world and render settings and add objects, never delete, rename, move, rotate, scale or hide content. `styles/plain` is the unstyled reference.
- `renders/`: render output, one `<style>/` dir each, git-ignored.

## Gotchas
- Blender MCP (`.mcp.json`, `mcp-for-blender==2.0.0`, telemetry off, `BLENDER_MCP_SAFE_MODE=1`) needs Blender open with the add-on's server started: 3D viewport, N sidebar, MCP for Blender tab, Start MCP Server (port 9876).
- Poly Haven access is a per-scene flag (`scene.blendermcp_use_polyhaven`), not a preference: tick it in the sidebar, or have a style script set it.
- The add-on lives outside the repo at `~/Library/Application Support/Blender/5.3/scripts/addons/blender_mcp.py`; reinstall it with `BLENDERMCP_ADDONS_DIR=<that dir> uvx mcp-for-blender==2.0.0 install-addon` when bumping the pinned version.
- Blender ignores `PYTHONPATH`: `import artlab` in a Blender script works because `run_blender` puts `src/` on `sys.path` before the script runs, so launch Blender through it, not by hand.
- The iso cutaway is applied by `artlab.inblender.cameras.use_camera(scene, key)`, which sets `scene.camera` and hides the `artlab_cutaway` objects (canopy roof and lamps) for `iso` only; `build_test_scene` leaves everything visible with `Cam.Iso` active. Styles never hide content: render each camera through `use_camera`.
