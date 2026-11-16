"""The `artlab render` command, `artlab.render.render_style` and the `plain` style (#5).

Tests marked `blender` run the command in a real Blender. The rest run with no
Blender (ARTLAB_BLENDER unset and PATH an empty dir, or ARTLAB_BLENDER a stub
that records whether it was launched), so they run on CI. Styles written to
tmp_path run inside Blender and may import bpy; the "recorder" style appends a
`render_pre` handler that logs, per render, `scene.camera` and the objects with
`hide_render`, which is how the tests see what each render was made with.

Sizes stay at 32 px or less and `--no-render` is used wherever no PNG is needed:
EEVEE dominates Blender time. PNG facts come from the header (width and height
are big-endian uint32s at bytes 16-24, then bit depth and color type), not from
an image library or the code under test.
"""

import json
import os
import re
import secrets
import struct
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from artlab.blender import BlenderNotFound, run_blender

REPO = Path(__file__).resolve().parents[1]
REPO_STYLES = REPO / "styles"
PROBES = REPO / "tests" / "blender_scripts"
BLEND_PROBE = PROBES / "probe_blend.py"
BARE_PROBE = PROBES / "probe_bare_scene.py"
TIMEOUT = 300

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RGBA_8 = (8, 6)  # PNG bit depth, color type 6 (truecolor with alpha)
CAMERA_NAMES = {"iso": "Cam.Iso", "hero": "Cam.Hero"}
CUTAWAY = ["Canopy.Roof", "Platform.Lamps"]
# Content these tests name; the test scene has more, which plain must keep too.
NAMED_CONTENT = {
    "Ground",
    "Bench",
    "Sign",
    "Canopy.Roof",
    "Platform.Lamps",
    "Train.Body",
    "Person.2.Head",
}
CONTENT_KEYS = ("location", "rotation_deg", "scale", "hide_render")

NOOP = """\
def build(scene):
    pass
"""
RECORDER = """\
import json

import bpy

LOG = __LOG__


def record(scene, *args):
    hidden = sorted(obj.name for obj in scene.objects if obj.hide_render)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"camera": scene.camera.name, "hidden": hidden}) + "\\n")


def build(scene):
    bpy.app.handlers.render_pre.append(record)
"""
ADD_LIGHT = """\
import bpy


def build(scene):
    light = bpy.data.lights.new("Beta.Light", "POINT")
    obj = bpy.data.objects.new("Beta.Light", light)
    scene.collection.objects.link(obj)
"""


def raising(message: str) -> str:
    return f"def build(scene):\n    raise RuntimeError({message!r})\n"


# --- helpers ------------------------------------------------------------------


def run_cli(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "artlab", *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def render(args: list[str], cwd: Path, env: dict[str, str] | None = None):
    return run_cli(["render", *args], cwd, env)


def explain(result: subprocess.CompletedProcess[str]) -> str:
    return (
        f"exit {result.returncode}\n--- stdout\n{result.stdout}"
        f"\n--- stderr\n{result.stderr}"
    )


def printed_paths(result: subprocess.CompletedProcess[str], cwd: Path) -> list[Path]:
    """Each non-empty stdout line as a path, resolved against the cwd it ran in."""
    return [
        (cwd / line.strip()).resolve()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def resolved(*paths: Path) -> list[Path]:
    return sorted(p.resolve() for p in paths)


def write_style(styles_dir: Path, name: str, source: str) -> Path:
    path = styles_dir / name / "build.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source))
    return path


def recorder_style(styles_dir: Path, name: str, log: Path) -> Path:
    return write_style(styles_dir, name, RECORDER.replace("__LOG__", repr(str(log))))


def records(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def png_header(path: Path) -> tuple[int, int, int, int]:
    """(width, height, bit depth, color type) from the PNG's IHDR chunk."""
    assert path.is_file(), f"no {path}"
    head = path.read_bytes()[:26]
    assert head[:8] == PNG_SIGNATURE, f"{path} is not a PNG"
    assert head[12:16] == b"IHDR", path
    width, height = struct.unpack(">II", head[16:24])
    return width, height, head[24], head[25]


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def pngs_under(root: Path) -> list[Path]:
    return [p for p in files_under(root) if p.suffix == ".png"]


def no_blender_env(tmp_path: Path) -> dict[str, str]:
    """This environment with ARTLAB_BLENDER unset and PATH an empty dir."""
    empty = tmp_path / "empty-path"
    empty.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "ARTLAB_BLENDER"}
    env["PATH"] = str(empty)
    return env


def open_blend(blend: Path, out_json: Path) -> dict:
    assert blend.is_file(), f"no {blend}"
    run_blender(BLEND_PROBE, [str(blend), str(out_json)])
    return json.loads(out_json.read_text())


def content_of(manifest: Path) -> dict:
    data = json.loads(manifest.read_text())
    return {
        name: {key: obj[key] for key in CONTENT_KEYS}
        for name, obj in data["objects"].items()
        if obj["content"]
    }


def committed_styles() -> list[str]:
    """discover(<repo>/styles), to parametrize over every committed style."""
    try:
        from artlab.styles import discover
    except ModuleNotFoundError:
        # Before #5 lands, still collect the plain case so it fails on its own.
        return ["plain"]
    return list(discover(REPO_STYLES))


@pytest.fixture
def discover():
    from artlab.styles import discover

    return discover


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """`render STYLE --no-render` of a committed style, once per style per module."""
    cache: dict[str, Path] = {}

    def build(style: str) -> Path:
        if style not in cache:
            out = tmp_path_factory.mktemp(f"built-{style}")
            result = render(
                [style, "--no-render", "--renders-dir", str(out)]
                + ["--styles-dir", str(REPO_STYLES)],
                cwd=out,
            )
            assert result.returncode == 0, explain(result)
            cache[style] = out / style / "manifest.json"
        return cache[style]

    return build


def refused_run(tmp_path: Path, name: str, source: str):
    """Render the tmp style `name` at 16 px, both cameras: (result, its output dir)."""
    styles, out = tmp_path / "styles", tmp_path / "out"
    write_style(styles, name, source)
    result = render(
        [name, "--size", "16", "--renders-dir", str(out), "--styles-dir", str(styles)],
        cwd=tmp_path,
    )
    return result, out / name


# --- broad: render plain --------------------------------------------------------


@pytest.mark.blender
def test_render_plain_writes_cameras_and_manifest(tmp_path):
    out = tmp_path / "out"
    result = render(
        ["plain", "--size", "32", "--renders-dir", str(out)]
        + ["--styles-dir", str(REPO_STYLES)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, explain(result)
    style_dir = out / "plain"
    iso, hero = style_dir / "iso.png", style_dir / "hero.png"
    manifest = style_dir / "manifest.json"
    for png in (iso, hero):
        assert png_header(png) == (32, 32, *RGBA_8), png
    data = json.loads(manifest.read_text())
    assert data["style"] == "plain"
    assert data["render"]["resolution"] == [32, 32]
    content = {name for name, obj in data["objects"].items() if obj["content"]}
    assert NAMED_CONTENT <= content, sorted(content)
    # stdout is the written paths, one per line.
    assert sorted(printed_paths(result, tmp_path)) == resolved(iso, hero, manifest)
    assert not (style_dir / "scene.blend").exists()


# --- the cutaway: per camera in the renders, never in the saved scene -----------


@pytest.mark.blender
def test_cutaway_applies_to_the_iso_render_only(tmp_path):
    styles, out, log = tmp_path / "styles", tmp_path / "out", tmp_path / "log.jsonl"
    recorder_style(styles, "recorder", log)

    result = render(
        ["recorder", "--size", "16", "--renders-dir", str(out)]
        + ["--styles-dir", str(styles)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, explain(result)
    assert records(log) == [
        {"camera": "Cam.Iso", "hidden": CUTAWAY},
        {"camera": "Cam.Hero", "hidden": []},
    ]
    for key in ("iso", "hero"):
        assert png_header(out / "recorder" / f"{key}.png") == (16, 16, *RGBA_8), key


@pytest.mark.blender
def test_manifest_and_blend_show_the_scene_uncut(tmp_path):
    out = tmp_path / "out"
    result = render(
        ["plain", "--camera", "iso", "--save-blend", "--size", "16"]
        + ["--renders-dir", str(out), "--styles-dir", str(REPO_STYLES)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, explain(result)
    style_dir = out / "plain"
    manifest_path, blend = style_dir / "manifest.json", style_dir / "scene.blend"
    manifest = json.loads(manifest_path.read_text())
    for name in CUTAWAY:
        assert manifest["objects"][name]["hide_render"] is False, name
    assert manifest["render"]["resolution"] == [16, 16]

    saved = open_blend(blend, tmp_path / "blend.json")["objects"]
    for name in CUTAWAY:
        assert name in saved, sorted(saved)
        assert saved[name]["hide_render"] is False, name
    assert [name for name, obj in saved.items() if obj["hide_render"]] == []

    assert png_header(style_dir / "iso.png")[:2] == (16, 16)
    assert not (style_dir / "hero.png").exists()
    assert sorted(printed_paths(result, tmp_path)) == resolved(
        manifest_path, blend, style_dir / "iso.png"
    )


# --- the flags ------------------------------------------------------------------


@pytest.mark.blender
def test_camera_flag_renders_only_that_camera(tmp_path):
    styles, out, log = tmp_path / "styles", tmp_path / "out", tmp_path / "log.jsonl"
    recorder_style(styles, "hero-only", log)

    result = render(
        ["hero-only", "--camera", "hero", "--size", "16"]
        + ["--renders-dir", str(out), "--styles-dir", str(styles)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, explain(result)
    style_dir = out / "hero-only"
    assert png_header(style_dir / "hero.png")[:2] == (16, 16)
    assert not (style_dir / "iso.png").exists()
    assert records(log) == [{"camera": "Cam.Hero", "hidden": []}]
    assert sorted(printed_paths(result, tmp_path)) == resolved(
        style_dir / "manifest.json", style_dir / "hero.png"
    )


@pytest.mark.blender
def test_no_render_writes_manifest_only(tmp_path):
    # Also the defaults: --styles-dir styles and --renders-dir renders, both in the
    # cwd, and --size 1024.
    log = tmp_path / "log.jsonl"
    recorder_style(tmp_path / "styles", "bare", log)

    result = render(["bare", "--no-render"], cwd=tmp_path)

    assert result.returncode == 0, explain(result)
    manifest = tmp_path / "renders" / "bare" / "manifest.json"
    data = json.loads(manifest.read_text())
    assert data["style"] == "bare"
    assert data["render"]["resolution"] == [1024, 1024]
    assert pngs_under(tmp_path) == []
    assert records(log) == []  # nothing was rendered, not just nothing saved
    assert not (manifest.parent / "scene.blend").exists()
    assert printed_paths(result, tmp_path) == [manifest.resolve()]


@pytest.mark.blender
def test_save_blend_writes_scene_file(tmp_path):
    out = tmp_path / "out"
    result = render(
        ["plain", "--no-render", "--save-blend", "--size", "24"]
        + ["--renders-dir", str(out), "--styles-dir", str(REPO_STYLES)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, explain(result)
    style_dir = out / "plain"
    manifest, blend = style_dir / "manifest.json", style_dir / "scene.blend"
    saved = open_blend(blend, tmp_path / "blend.json")
    content = {name for name, obj in saved["objects"].items() if obj["content"]}
    assert NAMED_CONTENT <= content, sorted(content)
    assert set(CAMERA_NAMES.values()) <= set(saved["objects"])
    assert saved["resolution"] == [24, 24]
    assert json.loads(manifest.read_text())["render"]["resolution"] == [24, 24]
    assert pngs_under(out) == []
    assert sorted(printed_paths(result, tmp_path)) == resolved(manifest, blend)


@pytest.mark.blender
def test_render_all_builds_every_style(tmp_path, discover):
    styles, out = tmp_path / "styles", tmp_path / "out"
    write_style(styles, "gamma_x", NOOP)
    write_style(styles, "alpha", NOOP)
    write_style(styles, "beta-2", ADD_LIGHT)
    write_style(styles, "_wip", raising("not a style, never run"))
    (styles / "empty").mkdir()
    names = ["alpha", "beta-2", "gamma_x"]
    assert list(discover(styles)) == names

    result = render(
        ["--all", "--no-render", "--renders-dir", str(out)]
        + ["--styles-dir", str(styles)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, explain(result)
    manifests = [out / name / "manifest.json" for name in names]
    # In name order, one path per line.
    assert printed_paths(result, tmp_path) == [m.resolve() for m in manifests]
    for name, manifest in zip(names, manifests, strict=True):
        data = json.loads(manifest.read_text())
        assert data["style"] == name
        # Each manifest is its own style's build: only beta-2 adds the light.
        assert ("Beta.Light" in data["objects"]) == (name == "beta-2"), name
    assert sorted(p.name for p in out.iterdir()) == names
    assert pngs_under(out) == []


@pytest.mark.blender
def test_styles_run_in_name_order_and_stop_at_the_first_failure(tmp_path):
    token = secrets.token_hex(4)
    styles, out = tmp_path / "styles", tmp_path / "out"
    write_style(styles, "c-ok", NOOP)
    write_style(styles, "a-ok", NOOP)
    write_style(styles, "b-bad", raising(f"bad-{token}"))

    result = render(
        ["c-ok", "b-bad", "a-ok", "--no-render", "--renders-dir", str(out)]
        + ["--styles-dir", str(styles)],
        cwd=tmp_path,
    )

    assert result.returncode == 1, explain(result)
    assert f"bad-{token}" in result.stderr
    assert (out / "a-ok" / "manifest.json").is_file(), explain(result)
    assert not (out / "b-bad" / "manifest.json").exists()
    assert not (out / "c-ok" / "manifest.json").exists()


# --- every committed style ------------------------------------------------------


@pytest.mark.blender
@pytest.mark.parametrize("style", committed_styles())
def test_every_style_is_deterministic(style, built, tmp_path):
    first = built(style)
    again = tmp_path / "again"

    result = render(
        [style, "--no-render", "--renders-dir", str(again)]
        + ["--styles-dir", str(REPO_STYLES)],
        cwd=tmp_path,
    )

    assert result.returncode == 0, explain(result)
    second = again / style / "manifest.json"
    assert second.read_bytes() == first.read_bytes()


@pytest.mark.blender
@pytest.mark.parametrize("style", committed_styles())
def test_every_style_keeps_the_content(style, built):
    reference = content_of(built("plain"))
    assert NAMED_CONTENT <= set(reference), sorted(reference)
    assert [name for name, obj in reference.items() if obj["hide_render"]] == []

    assert content_of(built(style)) == reference


@pytest.mark.blender
def test_plain_is_the_test_scene_unstyled(built, tmp_path):
    bare = tmp_path / "bare.json"
    run_blender(BARE_PROBE, [str(bare)])

    assert json.loads(built("plain").read_text()) == json.loads(bare.read_text())


# --- usage errors: no Blender needed ----------------------------------------------


def test_unknown_style_exits_2_and_lists_styles(tmp_path):
    styles, out = tmp_path / "styles", tmp_path / "out"
    write_style(styles, "a", NOOP)
    write_style(styles, "kappa-7", NOOP)
    write_style(styles, "_wip", NOOP)
    env = no_blender_env(tmp_path)

    # Every name is checked before Blender is looked up or anything runs.
    for args, unknown in [(["nope"], "nope"), (["a", "zzz-missing"], "zzz-missing")]:
        result = render(
            [*args, "--renders-dir", str(out), "--styles-dir", str(styles)],
            cwd=tmp_path,
            env=env,
        )
        assert result.returncode == 2, (args, explain(result))
        assert unknown in result.stderr, args
        assert re.search(r"(?<![\w.-])a(?![\w.-])", result.stderr), args
        assert "kappa-7" in result.stderr, args
        assert "_wip" not in result.stderr, args
        assert "Traceback" not in result.stderr, args
    assert files_under(out) == []


def test_missing_blender_exits_2_with_hint(tmp_path):
    styles, out = tmp_path / "styles", tmp_path / "out"
    write_style(styles, "a", NOOP)
    unset = no_blender_env(tmp_path)
    bad = dict(unset, ARTLAB_BLENDER=str(tmp_path / "no-such" / "blender"))

    for label, env in [("unset", unset), ("bad ARTLAB_BLENDER", bad)]:
        result = render(
            ["a", "--renders-dir", str(out), "--styles-dir", str(styles)],
            cwd=tmp_path,
            env=env,
        )
        assert result.returncode == 2, (label, explain(result))
        assert "ARTLAB_BLENDER" in result.stderr, label
        assert "Traceback" not in result.stderr, label
    assert files_under(out) == []


def test_bad_render_arguments_exit_2_without_launching_blender(tmp_path):
    styles, out = tmp_path / "styles", tmp_path / "out"
    write_style(styles, "a", NOOP)
    (tmp_path / "no-styles").mkdir()
    marker = tmp_path / "blender-was-launched"
    stub = tmp_path / "bin" / "blender"
    stub.parent.mkdir()
    stub.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
    stub.chmod(0o755)
    env = dict(no_blender_env(tmp_path), ARTLAB_BLENDER=str(stub))
    styles_flag = ["--styles-dir", str(styles)]

    for args in [
        [*styles_flag],  # neither STYLE nor --all
        ["a", "--all", *styles_flag],
        ["a", "--camera", "top", *styles_flag],
        ["a", "--size", "0", *styles_flag],
        ["a", "--size", "big", *styles_flag],
        ["--all", "--styles-dir", str(tmp_path / "no-styles")],  # no styles
        ["--all", "--styles-dir", str(tmp_path / "absent")],
    ]:
        result = render([*args, "--renders-dir", str(out)], cwd=tmp_path, env=env)
        assert result.returncode == 2, (args, explain(result))
        assert "Traceback" not in result.stderr, args
        assert not marker.exists(), f"Blender was launched for {args}"
    assert files_under(out) == []

    # The control: the same command with good arguments does launch the stub,
    # so the refusals above are about the arguments, not a missing command.
    render(["a", "--no-render", *styles_flag, "--renders-dir", str(out)], tmp_path, env)
    assert marker.exists(), "a valid render never launched ARTLAB_BLENDER"


# --- styles that fail or break the rules -----------------------------------------


@pytest.mark.blender
def test_style_error_exits_1_with_traceback(tmp_path):
    message = f"boom-5678-{secrets.token_hex(4)}"
    result, style_dir = refused_run(tmp_path, "raiser", raising(message))

    assert result.returncode == 1, explain(result)
    assert message in result.stderr
    assert "Traceback" in result.stderr
    assert "RuntimeError" in result.stderr
    assert "raiser/build.py" in result.stderr  # the style's own frame
    assert pngs_under(tmp_path / "out") == []


@pytest.mark.blender
def test_style_that_moves_content_is_refused(tmp_path):
    result, style_dir = refused_run(
        tmp_path,
        "mover",
        """\
        import bpy


        def build(scene):
            bpy.data.objects["Bench"].location.x += 1
        """,
    )

    assert result.returncode == 1, explain(result)
    assert "Bench" in result.stderr
    assert "Vending.Front" not in result.stderr  # only what changed is named
    assert pngs_under(tmp_path / "out") == []
    assert not (style_dir / "manifest.json").exists()


@pytest.mark.blender
def test_style_that_deletes_content_is_refused(tmp_path):
    result, style_dir = refused_run(
        tmp_path,
        "deleter",
        """\
        import bpy


        def build(scene):
            bpy.data.objects.remove(bpy.data.objects["Sign"], do_unlink=True)
        """,
    )

    assert result.returncode == 1, explain(result)
    assert "Sign" in result.stderr
    assert "Vending.Front" not in result.stderr
    assert pngs_under(tmp_path / "out") == []
    assert not (style_dir / "manifest.json").exists()


@pytest.mark.blender
def test_style_that_hides_cutaway_content_is_refused(tmp_path):
    result, style_dir = refused_run(
        tmp_path,
        "hider",
        """\
        import bpy


        def build(scene):
            bpy.data.objects["Canopy.Roof"].hide_render = True
        """,
    )

    assert result.returncode == 1, explain(result)
    assert "Canopy.Roof" in result.stderr
    assert "Vending.Front" not in result.stderr
    assert pngs_under(tmp_path / "out") == []
    assert not (style_dir / "manifest.json").exists()


@pytest.mark.blender
def test_every_kind_of_content_change_is_named(tmp_path):
    # One style making every forbidden change at once: each changed object is
    # named, and none of the untouched ones is.
    result, style_dir = refused_run(
        tmp_path,
        "vandal",
        """\
        import bpy


        def build(scene):
            objects = bpy.data.objects
            objects["Train.Nose"].rotation_euler.z += 0.01  # rotated
            head = objects["Person.2.Head"]
            head.scale = head.scale * 1.01  # scaled
            objects["Vending.Body"].name = "Vending.Box"  # renamed
            # Moved in world space only: parented to a raised empty.
            rig = objects.new("Style.Rig", None)
            scene.collection.objects.link(rig)
            rig.location = (0.0, 0.0, 2.0)
            objects["Track.Rails"].parent = rig
            objects["Platform.Deck"].location.z += 1e-3  # past the 1e-4 tolerance
            objects["Ground"].hide_render = True  # hidden
            objects["Platform.Lamps"].hide_render = True  # a hidden cutaway object
        """,
    )
    changed = [
        "Train.Nose",
        "Person.2.Head",
        "Vending.Body",
        "Track.Rails",
        "Platform.Deck",
        "Ground",
        "Platform.Lamps",
    ]
    untouched = ["Train.Body", "Person.2.Body", "Vending.Front", "Bench", "Sign"]

    assert result.returncode == 1, explain(result)
    assert [name for name in changed if name not in result.stderr] == [], explain(
        result
    )
    assert [name for name in untouched if name in result.stderr] == [], explain(result)
    assert pngs_under(tmp_path / "out") == []
    assert not (style_dir / "manifest.json").exists()


@pytest.mark.blender
def test_style_without_build_is_refused(tmp_path):
    result, style_dir = refused_run(
        tmp_path,
        "lacking",
        """\
        def make(scene):  # not called build
            pass
        """,
    )

    assert result.returncode == 1, explain(result)
    # Names the missing function: "build" as a word, not just the file build.py.
    assert re.search(r"\bbuild\b(?!\.py)", result.stderr), explain(result)
    assert pngs_under(tmp_path / "out") == []
    assert not (style_dir / "manifest.json").exists()


# --- the Python API -------------------------------------------------------------


@pytest.mark.blender
def test_render_style_returns_the_written_paths(tmp_path):
    from artlab.render import RenderResult, render_style

    out = tmp_path / "out"
    result = render_style(
        "plain",
        styles_dir=REPO_STYLES,
        renders_dir=out,
        cameras=("hero",),
        size=8,
        save_blend=True,
    )

    assert isinstance(result, RenderResult)
    style_dir = out / "plain"
    assert {k: Path(v).resolve() for k, v in result.images.items()} == {
        "hero": (style_dir / "hero.png").resolve()
    }
    assert Path(result.manifest).resolve() == (style_dir / "manifest.json").resolve()
    assert result.blend is not None
    assert Path(result.blend).resolve() == (style_dir / "scene.blend").resolve()
    assert png_header(style_dir / "hero.png")[:2] == (8, 8)
    assert not (style_dir / "iso.png").exists()


def test_render_style_checks_the_name_before_looking_for_blender(tmp_path, monkeypatch):
    from artlab.render import UnknownStyle, render_style

    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.delenv("ARTLAB_BLENDER", raising=False)
    monkeypatch.setenv("PATH", str(empty))
    styles = tmp_path / "styles"
    write_style(styles, "a", NOOP)

    with pytest.raises(UnknownStyle) as excinfo:
        render_style("nope-3", styles_dir=styles, renders_dir=tmp_path / "out")
    assert "nope-3" in str(excinfo.value)
    with pytest.raises(BlenderNotFound):
        render_style("a", styles_dir=styles, renders_dir=tmp_path / "out")
    assert files_under(tmp_path / "out") == []
