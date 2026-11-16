"""The train: one commuter EMU car pulling in along the platform, frozen mid-arrival.

The car runs +X on the track (station.py's axes), its cab front partway along the
platform and its tail out past the deck's -X end. Like the station, every mesh
is built in world coordinates and every object sits at the origin. The body is a
plain silver shell with a dark underframe and bogies; there is no livery or
logo. Also adds the lights `Light.Headlight` and `Light.Windows`.
"""

import functools
import math

from . import station
from .shapes import Shape
from .station import GAUGE, RAIL_TOP, TRACK_Y

# Layout in metres, on station.py's axes.
FRONT_X = 3.0  # the cab front, partway along the deck
JOIN_X = FRONT_X - 1.2  # where the nose meets the body
TAIL_X = FRONT_X - 17.5  # the car is 17.5 m long; the tail is past the deck end
HALF_WIDTH = 1.4  # the car is 2.8 m wide, centered on the track
SIDE_Y = TRACK_Y - HALF_WIDTH  # the side facing the platform
BODY_BOTTOM = RAIL_TOP + 0.8
BODY_TOP = RAIL_TOP + 3.6
LOW_RADIUS, HIGH_RADIUS = 0.1, 0.35  # rounding of the skirt and the roof edges
DOOR_XS = (-12.1, -6.35, -0.6)  # door centers; each door has two tall windows
# Side windows along the car, as (x0, x1), between and beyond the doors.
WINDOW_XS = (
    (-14.0, -13.2),
    (-11.1, -9.35),
    (-9.1, -7.35),
    (-5.35, -3.6),
    (-3.35, -1.6),
    (0.4, 1.4),
)
BOGIE_XS = (TAIL_X + 2.5, JOIN_X - 2.0)
HEADLIGHT_Z = 5.725  # the middle of the lenses on the cab front

HEADLIGHT_COLOR = (1.0, 0.95, 0.85)
WINDOW_COLOR = (1.0, 0.9, 0.72)


def section(x, half_width, bottom, top, low_radius, high_radius):
    """The car's cross-section at `x`: a rounded rectangle, counterclockwise from +X."""
    y0, y1 = TRACK_Y - half_width, TRACK_Y + half_width
    corners = (  # (center y, center z, radius, start angle) from the bottom right
        (y1 - low_radius, bottom + low_radius, low_radius, -90),
        (y1 - high_radius, top - high_radius, high_radius, 0),
        (y0 + high_radius, top - high_radius, high_radius, 90),
        (y0 + low_radius, bottom + low_radius, low_radius, 180),
    )
    ring = []
    for cy, cz, radius, start in corners:
        for step in (0, 45, 90):
            angle = math.radians(start + step)
            ring.append(
                (x, cy + radius * math.cos(angle), cz + radius * math.sin(angle))
            )
    return ring


def car_section(x):
    return section(x, HALF_WIDTH, BODY_BOTTOM, BODY_TOP, LOW_RADIUS, HIGH_RADIUS)


def build(scene, add):
    """Add the car through `add(name, mesh, *extra_roles)`, then its lights."""
    add("Train.Body", body(), "steel")
    subsurf = add("Train.Nose", nose()).modifiers.new("Subdivision", "SUBSURF")
    subsurf.levels = subsurf.render_levels = 1
    add("Train.Windows", windows())
    add("Train.Headlights", headlights())
    add_lights(scene)


def body():
    """The shell and roof units; in steel, the underframe and bogies on the rails."""
    shape = Shape()
    shape.loft([car_section(TAIL_X), car_section(JOIN_X)])
    y0, y1 = TRACK_Y - 0.7, TRACK_Y + 0.7
    for x in (TAIL_X + 4.0, JOIN_X - 5.0):
        shape.box((x - 1.2, y0, BODY_TOP - 0.05), (x + 1.2, y1, BODY_TOP + 0.3))
    y0, y1 = TRACK_Y - 1.1, TRACK_Y + 1.1
    shape.box((TAIL_X + 1, y0, RAIL_TOP + 0.45), (JOIN_X - 0.6, y1, BODY_BOTTOM), 1)
    for x in BOGIE_XS:
        for y in (TRACK_Y - GAUGE / 2, TRACK_Y + GAUGE / 2):
            shape.box(
                (x - 1.25, y - 0.1, RAIL_TOP), (x + 1.25, y + 0.1, RAIL_TOP + 0.6), 1
            )
    return shape.mesh("Train.Body")


def nose():
    """The cab front: rings that narrow toward a flat face, rounded by its SUBSURF.

    The first ring sits inside the body, so the subdivision's shrinking back
    edge stays hidden. Smooth-shaded.
    """
    # The last two rings as (x, half width, bottom, top, low radius, high radius).
    edge = (FRONT_X - 0.15, HALF_WIDTH - 0.05, BODY_BOTTOM + 0.04, BODY_TOP - 0.08)
    face = (FRONT_X, HALF_WIDTH - 0.18, BODY_BOTTOM + 0.12, BODY_TOP - 0.22)
    shape = Shape()
    shape.loft(
        [
            car_section(JOIN_X - 0.3),
            car_section(JOIN_X),
            car_section(JOIN_X + 0.6),
            section(*edge, 0.15, 0.45),
            section(*face, 0.2, 0.55),
        ]
    )
    mesh = shape.mesh("Train.Nose")
    mesh.shade_smooth()
    return mesh


def windows():
    """Glowing panes proud of both sides (side and door windows), and the windscreen."""
    shape = Shape()
    panes = [(x0, x1, 6.45, 7.3) for x0, x1 in WINDOW_XS]
    panes += [
        (door + dx0, door + dx1, 6.2, 7.35)
        for door in DOOR_XS
        for dx0, dx1 in ((-0.55, -0.1), (0.1, 0.55))
    ]
    far_y = TRACK_Y + HALF_WIDTH
    for x0, x1, z0, z1 in panes:
        for y0, y1 in ((SIDE_Y - 0.02, SIDE_Y + 0.01), (far_y - 0.01, far_y + 0.02)):
            shape.box((x0, y0, z0), (x1, y1, z1))
    shape.box(
        (FRONT_X - 0.01, TRACK_Y - 1.0, 6.5), (FRONT_X + 0.02, TRACK_Y + 1.0, 7.55)
    )
    return shape.mesh("Train.Windows")


def headlights():
    """Two lenses low on the cab front."""
    shape = Shape()
    z0, z1 = HEADLIGHT_Z - 0.075, HEADLIGHT_Z + 0.075
    for y in (TRACK_Y - 0.95, TRACK_Y + 0.95):
        shape.box((FRONT_X - 0.01, y - 0.17, z0), (FRONT_X + 0.03, y + 0.17, z1))
    return shape.mesh("Train.Headlights")


def add_lights(scene):
    """A spot down the track ahead of the train, and the windows' spill on the deck."""
    light = functools.partial(station.light, scene)
    # A spot shines down its -Z; turned -85 degrees about Y it shines +X, dipping.
    at, turn = (FRONT_X + 0.1, TRACK_Y, HEADLIGHT_Z), (0, math.radians(-85), 0)
    beam = light("Light.Headlight", "headlight", "SPOT", 600, HEADLIGHT_COLOR, at, turn)
    beam.spot_size, beam.spot_blend = math.radians(40), 0.3
    # An area light turned -90 degrees about X shines -Y, onto the platform.
    at, turn = ((TAIL_X + JOIN_X) / 2, SIDE_Y - 0.05, 6.85), (math.radians(-90), 0, 0)
    spill = light("Light.Windows", "windows", "AREA", 300, WINDOW_COLOR, at, turn)
    spill.shape = "RECTANGLE"
    spill.size, spill.size_y = JOIN_X - TAIL_X - 0.8, 1.0
