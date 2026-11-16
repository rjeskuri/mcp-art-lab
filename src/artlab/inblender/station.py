"""The station: viaduct, platform, track, canopy, sign, bench and vending machine.

Axes: the track runs along X on the +Y side of the platform, so the platform's
open back edge (-Y) faces the iso camera; z = 0 is the top of the ground. Every
mesh is axis-aligned boxes in world coordinates, so every object sits at the
origin. Also adds the night lights `Moon`, `Light.Lamp.<n>` and `Light.Vending`.
"""

import math

import bpy

# Layout in metres, for the train, people and cameras (#12) to build against.
TRACK_X = 18.0  # the viaduct and the track run from -TRACK_X to TRACK_X
TRACK_Y = 1.7  # track centerline
GAUGE = 1.067  # rail spacing, Japanese narrow gauge
RAIL_PROFILE = ((0.065, 0.0, 0.02), (0.009, 0.02, 0.12), (0.034, 0.12, 0.17))
PLATFORM_X = 10.0  # the deck runs from -PLATFORM_X to PLATFORM_X
PLATFORM_BACK_Y = -5.0  # open back edge; the track-side edge is at y = 0
VIADUCT_TOP = 4.0
BED_TOP = 4.25
RAIL_TOP = BED_TOP + RAIL_PROFILE[-1][2]
DECK_TOP = 5.5
ROOF_Z = 8.6  # underside of the canopy slab
POST_XS = (-6.0, -2.0, 2.0, 6.0)
POST_Y = -3.9
LAMP_XS = (-4.0, 0.0, 4.0)
LAMP_Y = -1.9
BEAM_Z = ROOF_Z - 0.25  # underside of the canopy beams, top of the posts

MOON_COLOR = (0.62, 0.72, 1.0)
LAMP_COLOR = (0.92, 0.96, 1.0)
VENDING_COLOR = (0.85, 0.93, 1.0)

# Box faces as corner indices, wound so normals point out.
BOX_FACES = (
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (1, 2, 6, 5),
    (2, 3, 7, 6),
    (3, 0, 4, 7),
)


def boxes(name, *parts):
    """A mesh of boxes; each part is `(lo, hi)` or `(lo, hi, material_slot)`."""
    verts, faces, slots = [], [], []
    for lo, hi, *slot in parts:
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        first = len(verts)
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        verts += [(x, y, z) for z in (z0, z1) for x, y in corners]
        faces += [[first + i for i in face] for face in BOX_FACES]
        slots += [slot[0] if slot else 0] * len(BOX_FACES)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.polygons.foreach_set("material_index", slots)
    mesh.update()
    return mesh


def build(scene, add):
    """Add the station through `add(name, mesh, *extra_roles)`, then its lights."""
    add("Ground", boxes("Ground", ((-20, -7.5, -0.2), (20, 6, 0))))
    add("Viaduct", viaduct())
    add(
        "Platform.Deck",
        boxes(
            "Platform.Deck",
            ((-PLATFORM_X, PLATFORM_BACK_Y, VIADUCT_TOP), (PLATFORM_X, 0, DECK_TOP)),
            ((-PLATFORM_X, 0, DECK_TOP - 0.2), (PLATFORM_X, 0.12, DECK_TOP)),  # coping
        ),
    )
    strip = (
        (0.3 - PLATFORM_X, -1.1, DECK_TOP),
        (PLATFORM_X - 0.3, -0.8, DECK_TOP + 0.01),
    )
    add("Platform.Tactile", boxes("Platform.Tactile", strip))
    bed = ((-TRACK_X, TRACK_Y - 1.25, VIADUCT_TOP), (TRACK_X, TRACK_Y + 1.25, BED_TOP))
    add("Track.Bed", boxes("Track.Bed", bed))
    add("Track.Rails", rails())
    posts = [
        ((x - 0.125, POST_Y - 0.125, DECK_TOP), (x + 0.125, POST_Y + 0.125, BEAM_Z))
        for x in POST_XS
    ]
    add("Canopy.Posts", boxes("Canopy.Posts", *posts))
    add("Canopy.Roof", roof())
    lamps = [
        ((x - 0.6, LAMP_Y - 0.08, ROOF_Z - 0.1), (x + 0.6, LAMP_Y + 0.08, ROOF_Z))
        for x in LAMP_XS
    ]
    add("Platform.Lamps", boxes("Platform.Lamps", *lamps))
    add("Sign", sign(), "steel")
    add("Bench", bench(), "steel")
    body, front = vending_machine()
    add("Vending.Body", body, "steel")
    add("Vending.Front", front)
    add_lights(scene)


def viaduct():
    """Deck slab with a parapet behind the track, on frames of two pillars."""
    parts = [
        ((-TRACK_X, -5.3, 3.3), (TRACK_X, 4, VIADUCT_TOP)),
        ((-TRACK_X, 3.8, VIADUCT_TOP), (TRACK_X, 4, 5.2)),
    ]
    for x in (-15, -5, 5, 15):
        parts.append(((x - 0.45, -5.3, 2.8), (x + 0.45, 4, 3.3)))
        for y in (-4.3, 3.0):
            parts.append(((x - 0.45, y - 0.45, 0), (x + 0.45, y + 0.45, 2.8)))
    return boxes("Viaduct", *parts)


def rails():
    """Two rails on the track bed, each a foot, web and head (`RAIL_PROFILE`)."""
    parts = [
        ((-TRACK_X, y - half, BED_TOP + z0), (TRACK_X, y + half, BED_TOP + z1))
        for y in (TRACK_Y - GAUGE / 2, TRACK_Y + GAUGE / 2)
        for half, z0, z1 in RAIL_PROFILE
    ]
    return boxes("Track.Rails", *parts)


def roof():
    """Canopy slab on cross beams over the posts, with fascias on both long edges."""
    x = PLATFORM_X - 1.5
    parts = [((-x, -5.3, ROOF_Z), (x, 0.3, ROOF_Z + 0.15))]
    parts += [((-x, y0, ROOF_Z - 0.15), (x, y0 + 0.1, ROOF_Z)) for y0 in (-5.3, 0.2)]
    parts += [((px - 0.1, -5.2, BEAM_Z), (px + 0.1, 0.2, ROOF_Z)) for px in POST_XS]
    return boxes("Canopy.Roof", *parts)


def sign():
    """A name board between two posts; dark bars on both faces suggest lettering."""
    y, z = POST_Y, 7.15  # the board's center, between the middle canopy posts
    parts = [((-1.2, y - 0.03, z - 0.35), (1.2, y + 0.03, z + 0.35))]
    parts += [
        ((x - 0.04, y - 0.04, DECK_TOP), (x + 0.04, y + 0.04, z + 0.35), 1)
        for x in (-1.24, 1.24)
    ]
    bars = [(x - 0.15, x + 0.15, 0.06, 0.3) for x in (-0.42, 0.0, 0.42)]  # the name
    bars += [
        (x - 0.06, x + 0.06, -0.08, -0.02)
        for x in (-0.48, -0.32, -0.16, 0, 0.16, 0.32, 0.48)
    ]
    bars.append((-1.1, 1.1, -0.27, -0.23))  # a line band
    for face in (y - 0.04, y + 0.03):
        parts += [
            ((x0, face, z + z0), (x1, face + 0.01, z + z1), 1)
            for x0, x1, z0, z1 in bars
        ]
    return boxes("Sign", *parts)


def bench():
    """Four seats with backs on a steel frame, facing the track."""
    parts = []
    for i in range(4):
        x0 = -4.93 + i * 0.48
        parts.append(((x0, -4.5, 5.92), (x0 + 0.42, -4.05, 5.97)))
        parts.append(((x0, -4.56, 6.02), (x0 + 0.42, -4.51, 6.42)))
    parts.append(((-4.95, -4.4, 5.82), (-3.05, -4.3, 5.92), 1))
    for x in (-4.75, -3.25):
        parts.append(((x - 0.03, -4.6, DECK_TOP), (x + 0.03, -4.2, 5.82), 1))
        parts.append(((x - 0.03, -4.6, 5.82), (x + 0.03, -4.56, 6.4), 1))
    return boxes("Bench", *parts)


def vending_machine():
    """The body (with a dark dispenser flap) and a glowing 5x3 grid of product slots.

    The machine stands at the back of the deck facing +X, along the platform, so
    both the iso camera and a camera down the platform see its front.
    """
    x0, x1, y0, y1 = 6.6, 7.35, -4.85, -3.85
    body = boxes(
        "Vending.Body",
        ((x0, y0, DECK_TOP), (x1, y1, DECK_TOP + 1.83)),
        ((x1, y0 + 0.15, DECK_TOP + 0.12), (x1 + 0.02, y1 - 0.15, DECK_TOP + 0.32), 1),
    )
    width, height, gap_y, gap_z = 0.144, 0.273, 0.03, 0.04
    slots = []
    for row in range(3):
        for col in range(5):
            sy = y0 + 0.08 + col * (width + gap_y)
            sz = DECK_TOP + 0.8 + row * (height + gap_z)
            slots.append(((x1, sy, sz), (x1 + 0.02, sy + width, sz + height)))
    return body, boxes("Vending.Front", *slots)


def add_lights(scene):
    """A dim moon, an area light under each lamp fitting, and the vending glow."""
    tilt = (math.radians(55), 0, math.radians(-35))
    light(scene, "Moon", "moon", "SUN", 0.4, MOON_COLOR, (0, 0, 20), tilt)
    for n, x in enumerate(LAMP_XS, start=1):
        at = (x, LAMP_Y, ROOF_Z - 0.12)
        lamp = light(scene, f"Light.Lamp.{n}", "lamp", "AREA", 120, LAMP_COLOR, at)
        lamp.shape = "RECTANGLE"
        lamp.size, lamp.size_y = 1.2, 0.16
    # An area light shines down its -Z; turned -90 degrees about Y it shines +X.
    at, turn = (7.45, -4.35, 6.75), (0, math.radians(-90), 0)
    glow = light(scene, "Light.Vending", "vending", "AREA", 30, VENDING_COLOR, at, turn)
    glow.size = 0.9


def light(scene, name, tag, kind, energy, color, location, rotation=(0, 0, 0)):
    """Link a `kind` light `name` tagged `artlab_light = tag`; returns its data."""
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    obj.rotation_euler = rotation
    obj["artlab_light"] = tag
    scene.collection.objects.link(obj)
    return data
