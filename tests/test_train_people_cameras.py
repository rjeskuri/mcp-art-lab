"""The train, the people and the cameras (#12), on top of #4's station.

Every test here is marked `blender`. A module-scoped fixture runs the probe
tests/blender_scripts/probe_train_people_cameras.py once in a real Blender and
the tests assert on the JSON it writes; the determinism test runs it a second
time in a fresh process. The probe records any step that raised under
"errors", and every assertion message here carries them, so a missing module or
object fails the test that needs it and says why.

Bound boxes are world-space; an object's top and bottom are the highest and
lowest z of its bound box, the deck top is `Platform.Deck`'s top, and centers
are bound-box centers. Framing uses `world_to_camera_view` at a square
resolution: a corner is framed when x and y are in [0, 1] and its depth z is
past 0 and within the camera's clip range.
"""

import json
import math
import re
from pathlib import Path

import pytest

from artlab.blender import run_blender

pytestmark = pytest.mark.blender

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "tests" / "blender_scripts" / "probe_train_people_cameras.py"

# #4's station content, as (name, role), which CONTENT must still start with.
STATION = (
    ("Ground", "ground"),
    ("Viaduct", "concrete"),
    ("Platform.Deck", "platform"),
    ("Platform.Tactile", "tactile"),
    ("Track.Bed", "concrete"),
    ("Track.Rails", "rail"),
    ("Canopy.Posts", "steel"),
    ("Canopy.Roof", "roof"),
    ("Platform.Lamps", "lamp"),
    ("Sign", "sign"),
    ("Bench", "bench"),
    ("Vending.Body", "vending"),
    ("Vending.Front", "vending_glow"),
)
PEOPLE = (1, 2, 3)
HEADS = tuple(f"Person.{n}.Head" for n in PEOPLE)
BODIES = tuple(f"Person.{n}.Body" for n in PEOPLE)
# The content this ticket adds, as (name, role).
TRAIN_AND_PEOPLE = (
    ("Train.Body", "train_body"),
    ("Train.Nose", "train_body"),
    ("Train.Windows", "train_window"),
    ("Train.Headlights", "train_light"),
    *((name, "person_skin") for name in HEADS),
    *((name, "person_cloth") for name in BODIES),
)
CUTAWAY = ("Canopy.Roof", "Platform.Lamps")
CAMERAS = {"iso": "Cam.Iso", "hero": "Cam.Hero"}
# What the probe passes to use_camera, in order, and the keys it must refuse.
USE_SEQUENCE = ["hero", "iso", "iso", "hero", "hero", "iso"]
BAD_KEYS = ["top", "ISO", "Iso", "Cam.Iso", "Cam.Hero", ""]

TOUCH = 0.05  # how close a bottom must be to the surface it stands on
ANGLE_TOLERANCE = 0.01  # degrees
ISO_ROTATION = (60.0, 0.0, 45.0)
MIN_ISO_EXTENT = 0.6
HERO_FRAMED = (*HEADS, *BODIES, "Vending.Body", "Vending.Front")
HERO_FRAMED += ("Train.Nose", "Train.Headlights")


def run_probe(tmp_path_factory, label):
    out = tmp_path_factory.mktemp(label) / "train_people_cameras.json"
    run_blender(PROBE, [str(out)])
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    return run_probe(tmp_path_factory, "scene")


@pytest.fixture(scope="module")
def scene_again(tmp_path_factory):
    return run_probe(tmp_path_factory, "scene-again")


# --- reading the probe's JSON -------------------------------------------------


def need(data, key):
    """`data[key]`, failing with the probe's errors when that step did not run."""
    value = data.get(key)
    assert value is not None, f"the probe has no {key!r}; errors: {data['errors']}"
    return value


def obj(data, name):
    objects = data["objects"]
    assert name in objects, (
        f"no object {name!r}; the scene has {sorted(objects)}; "
        f"probe errors: {data['errors']}"
    )
    return objects[name]


def content_pairs(data):
    return [tuple(pair) for pair in need(data, "constants")["CONTENT"]]


def bottom(o):
    return o["bbox_min"][2]


def top(o):
    return o["bbox_max"][2]


def deck_top(data):
    return top(obj(data, "Platform.Deck"))


def union(*objs):
    """The combined bound box of `objs`, as (min, max)."""
    lo = [min(o["bbox_min"][i] for o in objs) for i in range(3)]
    hi = [max(o["bbox_max"][i] for o in objs) for i in range(3)]
    return lo, hi


def center(lo, hi):
    return [(a + b) / 2 for a, b in zip(lo, hi, strict=True)]


def bbox_center(o):
    return center(o["bbox_min"], o["bbox_max"])


def inside_xy(point, o):
    return all(o["bbox_min"][i] <= point[i] <= o["bbox_max"][i] for i in range(2))


def camera(data, name):
    o = obj(data, name)
    assert o["type"] == "CAMERA", (name, o["type"])
    return o


def projected(data, cam_name):
    framing = need(data, "framing")
    assert cam_name in framing, (
        f"no framing through {cam_name}; probe errors: {data['errors']}"
    )
    view = framing[cam_name]
    width, height = view["resolution"]
    assert width == height, f"framing must use a square resolution: {view}"
    return view["objects"]


def unframed_corners(data, cam_name, names):
    """Problems for each corner of `names` that falls outside `cam_name`'s frame."""
    clip = camera(data, cam_name)["camera"]
    views = projected(data, cam_name)
    problems = []
    for name in names:
        assert name in views, f"{name} was not projected; it is not content"
        corners = views[name]["corners"]
        assert len(corners) == 8, (name, corners)
        for x, y, z in corners:
            inside = 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
            in_depth = z > 0 and clip["clip_start"] <= z <= clip["clip_end"]
            if not (inside and in_depth):
                problems.append(f"{name}: corner at ({x:.3f}, {y:.3f}, z={z:.3f})")
    return problems


# --- broad: what the build adds -----------------------------------------------


def test_adds_the_train_and_people_with_roles(scene):
    pairs = content_pairs(scene)
    names = [name for name, _ in pairs]
    assert len(names) == len(set(names)), f"CONTENT repeats a name: {names}"
    # #4's entries are untouched and this ticket's are appended after them.
    assert pairs[: len(STATION)] == list(STATION), pairs
    assert set(pairs[len(STATION) :]) == set(TRAIN_AND_PEOPLE), pairs
    assert len(pairs) == len(STATION) + len(TRAIN_AND_PEOPLE), pairs

    problems = []
    for name, role in TRAIN_AND_PEOPLE:
        o = obj(scene, name)
        if o["type"] != "MESH":
            problems.append(f"{name} is a {o['type']}, not a MESH")
            continue
        if not o["vertices"]:
            problems.append(f"{name} has no evaluated vertices")
        if o["props"].get("artlab_content") is not True:
            problems.append(f"{name} is not tagged artlab_content: {o['props']}")
        if o["props"].get("artlab_role") != role:
            problems.append(f"{name} has role {o['props'].get('artlab_role')!r}")
    assert not problems, problems

    tagged = {
        n for n, o in scene["objects"].items() if o["props"].get("artlab_content")
    }
    assert tagged == set(names)


def test_people_stand_on_the_deck(scene):
    deck = obj(scene, "Platform.Deck")
    surface = deck_top(scene)
    problems = []
    for n in PEOPLE:
        head = obj(scene, f"Person.{n}.Head")
        body = obj(scene, f"Person.{n}.Body")
        lo, hi = union(head, body)
        height = hi[2] - lo[2]
        if not 1.5 <= height <= 1.9:
            problems.append(f"Person.{n} is {height:.3f} m tall")
        gap = bottom(body) - surface
        if abs(gap) > TOUCH:
            problems.append(f"Person.{n}.Body's bottom is {gap:+.3f} from the deck")
        if not inside_xy(center(lo, hi), deck):
            problems.append(f"Person.{n}'s XY center {center(lo, hi)[:2]} is off it")
        if bbox_center(head)[2] <= bbox_center(body)[2]:
            problems.append(f"Person.{n}.Head's center is not above the body's")
    assert not problems, problems


def test_train_sits_on_the_rails_partly_alongside_the_platform(scene):
    body = obj(scene, "Train.Body")
    nose = obj(scene, "Train.Nose")
    rails = obj(scene, "Track.Rails")
    bed = obj(scene, "Track.Bed")
    deck = obj(scene, "Platform.Deck")

    rail_top = top(rails)
    assert rail_top <= bottom(body) <= rail_top + 1.0, (bottom(body), rail_top)
    assert inside_xy(bbox_center(body), rails), "the train is not over the rails"

    spans = [bed["bbox_max"][i] - bed["bbox_min"][i] for i in range(2)]
    axis = 0 if spans[0] >= spans[1] else 1
    lo, hi = union(body, nose)
    train = (lo[axis], hi[axis])
    platform = (deck["bbox_min"][axis], deck["bbox_max"][axis])
    overlap = min(train[1], platform[1]) - max(train[0], platform[0])
    assert overlap > 0, f"the train {train} is not alongside the deck {platform}"
    past = [train[0] < platform[0], train[1] > platform[1]]
    # Pulling in: past one end of the deck, not alongside all of it.
    assert sum(past) == 1, f"the train {train} vs the deck {platform}"
    # The cab front is the end at the platform.
    nose_at = bbox_center(nose)[axis]
    assert platform[0] <= nose_at <= platform[1], (nose_at, platform)


def test_round_parts_are_smooth(scene):
    problems = []
    for name in (*HEADS, "Train.Nose"):
        o = obj(scene, name)
        if not o["polygons"]:
            problems.append(f"{name} has no evaluated polygons")
        elif o["smooth_polygons"] != o["polygons"]:
            flat = o["polygons"] - o["smooth_polygons"]
            problems.append(f"{name}: {flat} of {o['polygons']} polygons are flat")
    assert not problems, problems
    modifiers = obj(scene, "Train.Nose")["modifiers"]
    subsurf = [
        m
        for m in modifiers
        if m["type"] == "SUBSURF" and m["show_render"] and m["render_levels"] >= 1
    ]
    assert subsurf, f"Train.Nose has no SUBSURF that renders: {modifiers}"


def test_train_lights(scene):
    lights = {n: o for n, o in scene["objects"].items() if o["type"] == "LIGHT"}
    groups = {}
    for name, o in lights.items():
        groups.setdefault(o["props"].get("artlab_light"), []).append(name)

    assert groups.get("headlight") == ["Light.Headlight"], groups
    assert lights["Light.Headlight"]["light"]["type"] == "SPOT"
    windows = groups.get("windows", [])
    assert windows, f"no light is tagged windows: {groups}"
    for name in windows:
        assert re.fullmatch(r"Light\.Windows(\.\d+)?", name), name
    for name in ("Light.Headlight", *windows):
        assert lights[name]["light"]["energy"] > 0, (name, lights[name]["light"])


# --- the camera module ----------------------------------------------------------


def test_camera_constants(scene):
    constants = need(scene, "camera_constants")
    assert constants["types"] == {
        "CAMERAS": "dict",
        "CAMERA_ORDER": "tuple",
        "CUTAWAY_CAMERAS": "frozenset",
    }
    assert constants["CAMERAS"] == CAMERAS
    assert constants["CAMERA_ORDER"] == ["iso", "hero"]
    assert constants["CUTAWAY_CAMERAS"] == ["iso"]
    for name in CAMERAS.values():
        assert not camera(scene, name)["props"].get("artlab_content"), name


# --- the iso camera -------------------------------------------------------------


def test_iso_camera_is_2_to_1_dimetric_orthographic(scene):
    cam = camera(scene, "Cam.Iso")
    assert cam["camera"]["type"] == "ORTHO", cam["camera"]
    assert cam["rotation_mode"] == "XYZ", cam["rotation_mode"]
    for key in ("rotation_euler_deg", "world_rotation_deg"):
        for got, want in zip(cam[key], ISO_ROTATION, strict=True):
            assert abs(got - want) <= ANGLE_TOLERANCE, (key, cam[key])


def test_iso_frames_all_uncut_content(scene):
    cutaway = set(need(scene, "constants")["CUTAWAY"])
    uncut = [name for name, _ in content_pairs(scene) if name not in cutaway]
    expected = {name for name, _ in (*STATION, *TRAIN_AND_PEOPLE)} - set(CUTAWAY)
    assert expected <= set(uncut), sorted(expected - set(uncut))

    problems = unframed_corners(scene, "Cam.Iso", uncut)
    assert not problems, problems

    views = projected(scene, "Cam.Iso")
    corners = [c for name in uncut for c in views[name]["corners"]]
    extents = [max(c[i] for c in corners) - min(c[i] for c in corners) for i in (0, 1)]
    assert max(extents) >= MIN_ISO_EXTENT, f"content spans {extents} of the frame"


def test_iso_looks_across_the_platform_at_the_track(scene):
    at = camera(scene, "Cam.Iso")["location"][:2]
    to_track = math.dist(at, bbox_center(obj(scene, "Track.Bed"))[:2])
    to_deck = math.dist(at, bbox_center(obj(scene, "Platform.Deck"))[:2])
    assert to_track > to_deck, (to_track, to_deck)


# --- the hero camera ------------------------------------------------------------


def test_hero_is_a_platform_level_perspective(scene):
    cam = camera(scene, "Cam.Hero")
    assert cam["camera"]["type"] == "PERSP", cam["camera"]
    above = cam["location"][2] - deck_top(scene)
    assert 1.0 <= above <= 2.5, f"Cam.Hero is {above:.3f} m above the deck"


def test_hero_frames_people_vending_and_train_front(scene):
    problems = unframed_corners(scene, "Cam.Hero", HERO_FRAMED)
    assert not problems, problems


def test_hero_composition(scene):
    at = camera(scene, "Cam.Hero")["location"]

    def distance(point):
        return math.dist(at, point)

    nose = distance(bbox_center(obj(scene, "Train.Nose")))
    for n in PEOPLE:
        lo, hi = union(obj(scene, f"Person.{n}.Head"), obj(scene, f"Person.{n}.Body"))
        person = distance(center(lo, hi))
        assert person < nose, f"Person.{n} is {person:.2f} m away, the nose {nose:.2f}"
    lights = distance(bbox_center(obj(scene, "Train.Headlights")))
    body = distance(bbox_center(obj(scene, "Train.Body")))
    assert lights < body, (lights, body)
    x = projected(scene, "Cam.Hero")["Vending.Body"]["center"][0]
    assert x < 0.4 or x > 0.6, f"the vending machine is centered at x = {x:.3f}"


# --- the cutaway ------------------------------------------------------------------


def test_use_camera_applies_the_cutaway_per_camera(scene):
    cutaway = sorted(need(scene, "constants")["CUTAWAY"])
    assert cutaway == sorted(CUTAWAY)
    report = need(scene, "use_camera")
    steps = report["steps"]
    assert [step["key"] for step in steps] == USE_SEQUENCE
    expected = {"iso": ("Cam.Iso", cutaway), "hero": ("Cam.Hero", [])}
    for i, step in enumerate(steps):
        got = (step["camera"], step["hidden"])
        assert got == expected[step["key"]], (i, step)
    assert report["refused"] == {key: "KeyError" for key in BAD_KEYS}


def test_built_scene_is_uncut_with_iso_active(scene):
    names = [name for name, _ in content_pairs(scene)]
    assert {name for name, _ in TRAIN_AND_PEOPLE} <= set(names), names
    hidden = [name for name in names if obj(scene, name)["hide_render"]]
    assert hidden == [], f"hidden after the build: {hidden}"
    assert scene["scene_camera"] == "Cam.Iso", (
        f"scene.camera is {scene['scene_camera']!r}; probe errors: {scene['errors']}"
    )


# --- determinism ------------------------------------------------------------------


def test_build_is_deterministic(scene, scene_again):
    first = need(scene, "fingerprint")
    rows = {row[0]: row for row in first["objects"]}
    # The fingerprint covers all the content, the new lights and both cameras.
    for name, _ in (*STATION, *TRAIN_AND_PEOPLE):
        assert name in rows, f"{name} is not in the fingerprint"
        assert rows[name][4], f"{name} has no evaluated vertices"
    lights = {row[0] for row in first["lights"]}
    assert "Light.Headlight" in lights, lights
    assert {row[0] for row in first["cameras"]} == set(CAMERAS.values())
    assert scene_again["errors"] == scene["errors"] == {}
    assert need(scene_again, "fingerprint") == first
