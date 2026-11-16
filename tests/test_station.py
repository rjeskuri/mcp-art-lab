"""The station half of the test scene (#4): `artlab.inblender.testscene`.

Every test here is marked `blender`. A module-scoped fixture runs the probe
tests/blender_scripts/probe_station.py once in a real Blender and the tests
assert on the JSON it writes; the determinism test runs it a second time in a
fresh process. `CONTENT` is read through the probe at run time, so these stay
green when #12 appends the train and people to it. Bound boxes are world-space;
an object's top and bottom are the highest and lowest z of its own bound box.
"""

import json
import math
import re
from pathlib import Path

import pytest

from artlab.blender import run_blender

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "tests" / "blender_scripts" / "probe_station.py"

# The station content the ticket lists, as (name, role). #12 appends more.
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
ALL_ROLES = {
    "ground",
    "concrete",
    "platform",
    "tactile",
    "rail",
    "steel",
    "roof",
    "lamp",
    "sign",
    "bench",
    "vending",
    "vending_glow",
    "train_body",
    "train_window",
    "train_light",
    "person_skin",
    "person_cloth",
}
EMISSIVE = ("lamp", "vending_glow", "train_window", "train_light")
TOUCH = 0.05  # how close a bottom must be to the surface it stands on


def run_probe(tmp_path_factory, label):
    out = tmp_path_factory.mktemp(label) / "station.json"
    run_blender(PROBE, [str(out)])
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def station(tmp_path_factory):
    return run_probe(tmp_path_factory, "station")


@pytest.fixture(scope="module")
def station_again(tmp_path_factory):
    return run_probe(tmp_path_factory, "station-again")


def obj(data, name):
    objects = data["objects"]
    assert name in objects, f"no object {name!r}; the scene has {sorted(objects)}"
    return objects[name]


def bottom(o):
    return o["bbox_min"][2]


def top(o):
    return o["bbox_max"][2]


def xy_center(o):
    return tuple((o["bbox_min"][i] + o["bbox_max"][i]) / 2 for i in range(2))


def inside_xy(point, o):
    return all(o["bbox_min"][i] <= point[i] <= o["bbox_max"][i] for i in range(2))


def content_pairs(data):
    return [tuple(pair) for pair in data["constants"]["CONTENT"]]


def luminance(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# --- broad: what the build creates --------------------------------------------


@pytest.mark.blender
def test_builds_the_station_content_with_roles(station):
    pairs = content_pairs(station)
    names = [name for name, _ in pairs]
    assert len(names) == len(set(names)), f"CONTENT repeats a name: {names}"
    for name, role in STATION:
        assert (name, role) in pairs, f"{(name, role)} missing from CONTENT"
        o = obj(station, name)
        assert o["type"] == "MESH", (name, o["type"])
        assert o["props"].get("artlab_content") is True, (name, o["props"])
        assert o["props"].get("artlab_role") == role, (name, o["props"])
    # Every CONTENT entry, the station's and any appended later, is a tagged mesh.
    for name, role in pairs:
        o = obj(station, name)
        assert o["type"] == "MESH", (name, o["type"])
        assert o["props"].get("artlab_role") == role, (name, o["props"])
    tagged = {
        n for n, o in station["objects"].items() if o["props"].get("artlab_content")
    }
    assert tagged == set(names)


@pytest.mark.blender
def test_cutaway_tags_match(station):
    cutaway = station["constants"]["CUTAWAY"]
    assert cutaway == ["Canopy.Roof", "Platform.Lamps"]
    tagged = {
        name
        for name, o in station["objects"].items()
        if o["props"].get("artlab_cutaway")
    }
    assert tagged == set(cutaway)
    for name in cutaway:
        assert obj(station, name)["props"]["artlab_cutaway"] is True, name


@pytest.mark.blender
def test_content_objects_excludes_lights(station):
    returned = station["content_objects"]
    assert returned["is_list"] and returned["all_objects"], returned
    expected = sorted(name for name, _ in content_pairs(station))
    assert returned["names"] == expected
    lights = {n for n, o in station["objects"].items() if o["type"] == "LIGHT"}
    assert lights, "the scene has no lights"
    assert not lights & set(returned["names"])


@pytest.mark.blender
def test_roles_palette_and_base_materials(station):
    constants = station["constants"]
    assert constants["types"] == {
        "CONTENT": "tuple",
        "CUTAWAY": "tuple",
        "EMISSIVE_ROLES": "tuple",
        "ROLES": "dict",
    }
    roles = constants["ROLES"]
    assert set(roles) == ALL_ROLES
    for role, rgba in roles.items():
        assert len(rgba) == 4, (role, rgba)
        assert all(isinstance(c, int | float) and 0.0 <= c <= 1.0 for c in rgba), (
            role,
            rgba,
        )
    assert constants["EMISSIVE_ROLES"] == list(EMISSIVE)
    for name, role in content_pairs(station):
        assert role in roles, (name, role)
        assert obj(station, name)["materials"][:1] == [f"base.{role}"], name


# --- layout -------------------------------------------------------------------


@pytest.mark.blender
def test_platform_is_elevated(station):
    deck = obj(station, "Platform.Deck")
    ground = obj(station, "Ground")
    assert top(deck) - top(ground) >= 3.0, (top(deck), top(ground))


@pytest.mark.blender
def test_tactile_strip_is_on_the_track_side(station):
    deck = obj(station, "Platform.Deck")
    tactile = obj(station, "Platform.Tactile")
    bed = obj(station, "Track.Bed")
    assert abs(bottom(tactile) - top(deck)) <= TOUCH, (bottom(tactile), top(deck))
    assert inside_xy(xy_center(tactile), deck), "the strip is not on the deck"
    to_bed = math.dist(xy_center(tactile), xy_center(bed))
    deck_to_bed = math.dist(xy_center(deck), xy_center(bed))
    assert to_bed < deck_to_bed, (to_bed, deck_to_bed)


@pytest.mark.blender
def test_rails_sit_on_the_track_bed(station):
    rails = obj(station, "Track.Rails")
    bed = obj(station, "Track.Bed")
    assert abs(bottom(rails) - top(bed)) <= TOUCH, (bottom(rails), top(bed))
    assert inside_xy(xy_center(rails), bed), "the rails are not over the bed"


@pytest.mark.blender
def test_props_stand_on_the_deck(station):
    deck = obj(station, "Platform.Deck")
    problems = []
    for name in ("Bench", "Sign", "Vending.Body", "Canopy.Posts"):
        o = obj(station, name)
        gap = bottom(o) - top(deck)
        if abs(gap) > TOUCH:
            problems.append(f"{name}: bottom is {gap:+.3f} from the deck top")
        if not inside_xy(xy_center(o), deck):
            problems.append(f"{name}: XY center {xy_center(o)} is off the deck")
    assert not problems, problems


# --- night --------------------------------------------------------------------


@pytest.mark.blender
def test_world_is_night(station):
    world = station["world"]
    assert world is not None, "the scene has no world"
    assert world["name"] == "World"
    assert len(world["backgrounds"]) == 1, world
    # The world shader is that one Background node and nothing else.
    assert world["surface_upstream"] == ["ShaderNodeBackground"], world
    bg = world["backgrounds"][0]
    assert not bg["color_linked"] and not bg["strength_linked"], bg
    assert all(c >= 0.0 for c in bg["color"][:3]) and bg["strength"] >= 0.0, bg
    assert luminance(bg["color"]) * bg["strength"] <= 0.05, bg


@pytest.mark.blender
def test_night_lights(station):
    lights = {n: o for n, o in station["objects"].items() if o["type"] == "LIGHT"}
    groups = {}
    for name, o in lights.items():
        tag = o["props"].get("artlab_light")
        assert isinstance(tag, str) and tag, f"{name} has no artlab_light tag"
        assert not o["props"].get("artlab_content"), f"{name} is tagged as content"
        groups.setdefault(tag, []).append(name)

    assert groups.get("moon") == ["Moon"], groups
    assert lights["Moon"]["light"]["type"] == "SUN"
    assert len(groups.get("lamp", [])) >= 2, groups
    assert len(groups.get("vending", [])) >= 1, groups
    for name in groups["lamp"]:
        assert re.fullmatch(r"Light\.Lamp\.\d+", name), name
    for name in groups["vending"]:
        assert re.fullmatch(r"Light\.Vending(\.\d+)?", name), name
    for name in groups["moon"] + groups["lamp"] + groups["vending"]:
        assert lights[name]["light"]["energy"] > 0, (name, lights[name]["light"])


@pytest.mark.blender
def test_emissive_roles_glow(station):
    emissive = set(station["constants"]["EMISSIVE_ROLES"])
    glowing = [(n, r) for n, r in content_pairs(station) if r in emissive]
    assert {"Platform.Lamps", "Vending.Front"} <= {n for n, _ in glowing}, glowing
    for name, role in glowing:
        material = obj(station, name)["first_material"]
        assert material is not None, f"{name} ({role}) has no material"
        lit = [
            node
            for node in material["emission"]
            if not node["strength_linked"]
            and node["strength"] > 0
            and node["feeds_output"]
            and (node["color_linked"] or max(node["color"][:3]) > 0)
        ]
        assert lit, (name, material)


# --- scene settings -----------------------------------------------------------


@pytest.mark.blender
def test_no_text_objects(station):
    types = {n: o["type"] for n, o in station["objects"].items()}
    assert {name for name, _ in content_pairs(station)} <= set(types)
    assert [n for n, t in types.items() if t == "FONT"] == []


@pytest.mark.blender
def test_render_settings(station):
    render = station["render"]
    assert render["engine"] == "BLENDER_EEVEE"
    assert (render["resolution_x"], render["resolution_y"]) == (1024, 1024)
    assert render["resolution_percentage"] == 100


@pytest.mark.blender
def test_build_is_deterministic(station, station_again):
    first = station["fingerprint"]
    rows = {row[0]: row for row in first["objects"]}
    # The fingerprint covers every content object and the lights, with geometry.
    for name, _ in content_pairs(station):
        assert name in rows, name
        assert rows[name][4], f"{name} has no evaluated vertices"
    assert len(first["lights"]) >= 4, first["lights"]
    assert station_again["fingerprint"] == first
