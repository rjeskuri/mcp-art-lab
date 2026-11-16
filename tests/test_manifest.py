"""artlab.inblender.manifest: the deterministic scene manifest.

Every test is marked `blender`. The probe `blender_scripts/probe_manifest.py`
builds a small fixed scene and writes its manifest; it runs once per variant
(module-scoped fixtures) and once more for the byte-identity test. "base" is the
scene the ticket describes; "noworld" has the same objects with other values,
tags and render settings, and no world, so a hard-coded answer cannot pass both.
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from artlab.blender import run_blender

pytestmark = pytest.mark.blender

PROBE = Path(__file__).resolve().parent / "blender_scripts" / "probe_manifest.py"

TOP_KEYS = {"blender", "style", "render", "world", "objects", "materials"}
RENDER_KEYS = {
    "engine",
    "resolution",
    "film_transparent",
    "view_transform",
    "use_freestyle",
}
OBJECT_KEYS = {
    "type",
    "content",
    "role",
    "location",
    "rotation_deg",
    "scale",
    "hide_render",
    "modifiers",
    "materials",
}
EXTRA_KEYS = {
    "MESH": {"vertices", "faces", "smooth_faces"},
    "CAMERA": {"camera"},
    "LIGHT": {"light"},
}
OBJECT_TYPES = {"Box": "MESH", "Ball": "MESH", "Cam": "CAMERA", "Sun": "LIGHT"}

# What the probe sets, per variant.
STYLE = {"base": "plain", "noworld": "toon-test"}
RENDER = {
    "base": {
        "engine": "BLENDER_WORKBENCH",
        "resolution": [640, 360],
        "film_transparent": True,
        "view_transform": "Standard",
        "use_freestyle": True,
    },
    "noworld": {
        "engine": "CYCLES",
        "resolution": [320, 240],
        "film_transparent": False,
        "view_transform": "AgX",
        "use_freestyle": False,
    },
}

PRINCIPLED = ["ShaderNodeBsdfPrincipled", "ShaderNodeOutputMaterial"]
RAMP = "ShaderNodeValToRGB"

# A 32x16 UV sphere: 448 quads + 64 pole triangles = 512 faces, 482 vertices,
# 992 edges. Level-1 subsurf: a quad gives 4 faces, a triangle 3, so
# 448*4 + 64*3 = 1984 faces and V + E + F = 482 + 992 + 512 = 1986 vertices.
# Only the 64 triangles are smooth: 64*3 = 192 smooth faces once evaluated.
BALL_GEOMETRY = {"vertices": 1986, "faces": 1984, "smooth_faces": 192}
BOX_GEOMETRY = {"vertices": 8, "faces": 6, "smooth_faces": 0}

# "-0.0" as a whole JSON number (not the start of "-0.05").
NEGATIVE_ZERO = re.compile(r"-0\.0+(?![0-9eE])")


@dataclass
class Run:
    text: str
    data: dict
    dict_data: dict
    facts: dict


def run_probe(out_dir: Path, variant: str) -> Run:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "manifest.json"
    run_blender(PROBE, [str(out), variant])
    text = out.read_text()
    return Run(
        text=text,
        data=json.loads(text),
        dict_data=json.loads(Path(f"{out}.dict.json").read_text()),
        facts=json.loads(Path(f"{out}.facts.json").read_text()),
    )


@pytest.fixture(scope="module")
def runs(tmp_path_factory) -> dict[str, Run]:
    root = tmp_path_factory.mktemp("manifest")
    return {v: run_probe(root / v, v) for v in ("base", "noworld")}


def floats_in(value):
    if isinstance(value, float):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from floats_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from floats_in(item)


def is_float_triple(value) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(type(x) is float for x in value)
    )


# --- broad: shape and format -------------------------------------------------


@pytest.mark.parametrize("variant", ["base", "noworld"])
def test_manifest_has_the_documented_shape(runs, variant):
    run = runs[variant]
    text, m = run.text, run.data

    # Format: sorted keys, 2-space indent, one trailing newline.
    assert text == json.dumps(m, sort_keys=True, indent=2) + "\n"
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert text.splitlines()[1].startswith('  "blender": ')

    # scene_manifest returns the same dict write_manifest writes.
    assert run.dict_data == m

    assert set(m) == TOP_KEYS
    assert m["blender"] == run.facts["blender"]
    assert m["style"] == STYLE[variant]
    assert m["render"] == RENDER[variant]
    assert set(m["render"]) == RENDER_KEYS
    assert all(type(x) is int for x in m["render"]["resolution"])

    assert set(m["objects"]) == set(OBJECT_TYPES)
    for name, obj in m["objects"].items():
        kind = OBJECT_TYPES[name]
        assert obj["type"] == kind, name
        assert set(obj) == OBJECT_KEYS | EXTRA_KEYS[kind], name
        assert type(obj["content"]) is bool, name
        assert obj["role"] is None or isinstance(obj["role"], str), name
        assert type(obj["hide_render"]) is bool, name
        for key in ("location", "rotation_deg", "scale"):
            assert is_float_triple(obj[key]), (name, key, obj[key])
        assert all(isinstance(x, str) for x in obj["modifiers"]), name
        assert all(isinstance(x, str) for x in obj["materials"]), name
        for key in EXTRA_KEYS["MESH"] & set(obj):
            assert type(obj[key]) is int, (name, key)
    assert set(m["objects"]["Cam"]["camera"]) == {"type", "lens", "ortho_scale"}
    assert set(m["objects"]["Sun"]["light"]) == {"type", "energy", "color"}

    hidden = {name for name, obj in m["objects"].items() if obj["hide_render"]}
    assert hidden == {"Ball"}

    for name, mat in m["materials"].items():
        assert set(mat) == {"nodes", "color_ramps"}, name
        assert all(isinstance(x, str) for x in mat["nodes"]), name
        assert all(isinstance(x, str) for x in mat["color_ramps"]), name

    if m["world"] is not None:
        assert set(m["world"]) == {"name", "nodes"}


def test_manifest_is_byte_identical_across_runs(runs, tmp_path):
    again = run_probe(tmp_path / "again", "base")

    first = runs["base"].text.encode()
    assert (tmp_path / "again" / "manifest.json").read_bytes() == first
    assert again.data == runs["base"].data


# --- custom properties --------------------------------------------------------


def test_content_and_role_come_from_custom_properties(runs):
    base = runs["base"].data["objects"]
    assert (base["Box"]["content"], base["Box"]["role"]) == (True, "wall")
    for name in ("Ball", "Cam", "Sun"):
        assert (base[name]["content"], base[name]["role"]) == (False, None), name

    # The other variant moves the tags: Ball has artlab_content = 1 (an int),
    # Box has none.
    other = runs["noworld"].data["objects"]
    assert (other["Ball"]["content"], other["Ball"]["role"]) == (True, "prop")
    for name in ("Box", "Cam", "Sun"):
        assert (other[name]["content"], other[name]["role"]) == (False, None), name


# --- geometry -------------------------------------------------------------------


@pytest.mark.parametrize("variant", ["base", "noworld"])
def test_manifest_reports_evaluated_geometry(runs, variant):
    objects = runs[variant].data["objects"]
    ball, box = objects["Ball"], objects["Box"]

    assert ball["modifiers"] == ["SUBSURF"]
    assert {k: ball[k] for k in BALL_GEOMETRY} == BALL_GEOMETRY
    assert box["modifiers"] == []
    assert {k: box[k] for k in BOX_GEOMETRY} == BOX_GEOMETRY
    for name in ("Cam", "Sun"):
        assert objects[name]["modifiers"] == [], name


# --- materials ------------------------------------------------------------------


@pytest.mark.parametrize("variant", ["base", "noworld"])
def test_manifest_lists_material_nodes_and_ramps(runs, variant):
    m = runs[variant].data
    objects, materials = m["objects"], m["materials"]

    # Slot names in slot order (not sorted).
    assert objects["Box"]["materials"] == ["Box.Mat"]
    assert objects["Ball"]["materials"] == ["Ball.Mat", "Accent.Mat"]
    assert objects["Cam"]["materials"] == []
    assert objects["Sun"]["materials"] == []

    if variant == "base":
        assert materials["Box.Mat"] == {
            "nodes": sorted([*PRINCIPLED, RAMP]),
            "color_ramps": ["CONSTANT"],
        }
    else:
        assert materials["Box.Mat"] == {"nodes": sorted(PRINCIPLED), "color_ramps": []}
    # Two ramps, created "Ramp.B" (CONSTANT) then "Ramp.A" (LINEAR): one entry in
    # nodes, and color_ramps in node-name order.
    assert materials["Ball.Mat"] == {
        "nodes": sorted(["ShaderNodeEmission", "ShaderNodeOutputMaterial", RAMP]),
        "color_ramps": ["LINEAR", "CONSTANT"],
    }
    assert materials["Accent.Mat"] == {
        "nodes": ["ShaderNodeOutputMaterial"],
        "color_ramps": [],
    }


@pytest.mark.parametrize("variant", ["base", "noworld"])
def test_unused_materials_are_left_out(runs, variant):
    m = runs[variant].data

    # Orphan.Mat has no users; Stray.Mat is used only by an object outside the scene.
    assert set(m["materials"]) == {"Box.Mat", "Ball.Mat", "Accent.Mat"}
    assert "Orphan.Mat" not in m["materials"]
    assert "Stray.Mat" not in m["materials"]
    assert "Stray" not in m["objects"]


# --- cameras and lights ---------------------------------------------------------


def test_cameras_and_lights_are_described(runs):
    base = runs["base"].data["objects"]
    assert base["Cam"]["camera"] == {"type": "ORTHO", "lens": 35.0, "ortho_scale": 12.5}
    assert base["Sun"]["light"] == {
        "type": "SUN",
        "energy": 3.5,
        "color": [1.0, 0.9, 0.8],
    }

    other = runs["noworld"].data["objects"]
    assert other["Cam"]["camera"] == {
        "type": "PERSP",
        "lens": 85.0,
        "ortho_scale": 4.25,
    }
    assert other["Sun"]["light"] == {
        "type": "SUN",
        "energy": 0.25,
        "color": [0.6, 0.7, 1.0],
    }


# --- rounding -------------------------------------------------------------------


def test_floats_are_rounded_and_negative_zero_normalised(runs):
    base = runs["base"].data["objects"]
    assert base["Box"]["location"] == [0.0, 1.2346, 2.0]
    assert base["Box"]["rotation_deg"] == [30.0, 0.0, -45.0]
    assert base["Box"]["scale"] == [1.0, 2.0, 0.5]
    # Ball's z rotation is -0.0 in Blender.
    assert base["Ball"]["rotation_deg"] == [0.0, 0.0, 0.0]
    assert base["Ball"]["location"] == [3.0, 0.0, 0.0]
    assert base["Cam"]["location"] == [10.0, -10.0, 8.0]
    assert base["Cam"]["rotation_deg"] == [60.0, 0.0, 45.0]
    assert base["Sun"]["rotation_deg"] == [50.0, 0.0, 30.0]

    other = runs["noworld"].data["objects"]
    assert other["Box"]["location"] == [0.5, 0.0, -2.25]
    assert other["Box"]["rotation_deg"] == [0.0, 90.0, 0.0]
    assert other["Box"]["scale"] == [3.0, 3.0, 3.0]

    for variant, run in runs.items():
        assert not NEGATIVE_ZERO.search(run.text), variant
        for f in floats_in(run.data):
            assert round(f, 4) == f, (variant, f)
            if f == 0.0:
                assert math.copysign(1.0, f) == 1.0, variant


# --- world ----------------------------------------------------------------------


def test_world_is_null_without_a_world(runs):
    assert runs["base"].data["world"] == {
        "name": "Probe.World",
        "nodes": [
            "ShaderNodeBackground",
            "ShaderNodeOutputWorld",
            "ShaderNodeTexGradient",
        ],
    }

    other = runs["noworld"].data
    assert "world" in other
    assert other["world"] is None
    assert '"world": null' in runs["noworld"].text
