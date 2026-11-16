"""Three faceless mannequins waiting on the platform: two together, one apart.

Each person is two meshes, built standing at the origin facing +Y and then
moved into place, so like the station's every object sits at the origin:
`Person.<n>.Head`, a smooth 32x16 UV sphere drawn out into an egg, and
`Person.<n>.Body`, a mannequin of tapered tubes with ball joints and box feet.
A `Pose` places, turns, scales and arms each one, so the three stand slightly
differently. No faces and no likenesses.
"""

import math
from typing import NamedTuple

from mathutils import Matrix, Vector

from .shapes import Shape
from .station import DECK_TOP


class Pose(NamedTuple):
    x: float
    y: float
    facing: float  # degrees about Z from facing the track (+Y); positive turns to -X
    scale: float  # size relative to the base mannequin, 1.765 m tall
    stance: float  # how far each ankle sits from the middle
    arms: tuple  # right then left arm as (out, forward, elbow) angles in degrees


POSES = (
    # A pair near the platform's +X end, half turned toward the arriving train,
    # one a step behind the other so both show through either camera.
    Pose(8.2, -2.0, 30.0, 1.0, 0.11, ((6, 4, 10), (8, 12, 45))),
    Pose(7.9, -2.7, 10.0, 0.94, 0.09, ((5, -3, 12), (7, 6, 20))),
    # One apart, nearer the train, behind the tactile strip, looking at a phone.
    Pose(5.0, -1.45, 20.0, 1.03, 0.13, ((8, 10, 100), (4, 2, 5))),
)

# The base mannequin, standing at the origin facing +Y, in metres.
HIP = (0.09, 0.88)  # (x, z) of each hip joint
KNEE_Z, ANKLE_Z = 0.49, 0.08
SHOULDER = (0.2, 1.38)
UPPER_ARM, FOREARM = 0.29, 0.25
HEAD_Z, HEAD_RADII = 1.645, (0.095, 0.105, 0.12)
SEGMENTS = 12


def build(add):
    """Add each person's head and body through `add(name, mesh)`."""
    for n, pose in enumerate(POSES, start=1):
        place = (
            Matrix.Translation((pose.x, pose.y, DECK_TOP))
            @ Matrix.Rotation(math.radians(pose.facing), 4, "Z")
            @ Matrix.Scale(pose.scale, 4)
        )
        for part, shape in (("Head", head()), ("Body", body(pose))):
            mesh = shape.mesh(f"Person.{n}.{part}")
            mesh.transform(place)
            mesh.shade_smooth()
            if part == "Body":
                mesh.set_sharp_from_angle(angle=math.radians(40))
            add(f"Person.{n}.{part}", mesh)


def head():
    """A faceless egg: a 32x16 UV sphere."""
    shape = Shape()
    egg = Matrix.Translation((0, 0, HEAD_Z)) @ Matrix.Diagonal((*HEAD_RADII, 1.0))
    shape.sphere(egg, 32, 16)
    return shape


def body(pose):
    """Pelvis, torso, neck, legs, arms, hands and feet, with ball joints."""
    shape = Shape()
    shape.tube((0, 0, 0.84), (0, 0, 1.0), (0.15, 0.15), 16, flatten=0.72)  # pelvis
    shape.tube((0, 0, 0.97), (0, 0, 1.42), (0.14, 0.19), 16, flatten=0.6)  # torso
    shape.tube((0, 0, 1.4), (0, 0, 1.55), (0.05, 0.045), SEGMENTS)  # neck
    for side, arm in zip((1, -1), pose.arms, strict=True):
        hip = Vector((side * HIP[0], 0, HIP[1]))
        ankle = Vector((side * pose.stance, 0, ANKLE_Z))
        knee = Vector(((hip.x + ankle.x) / 2, 0.01, KNEE_Z))
        shape.tube(hip, knee, (0.075, 0.055), SEGMENTS)
        shape.tube(knee, ankle, (0.05, 0.038), SEGMENTS)
        ball(shape, knee, 0.055)
        shape.box((ankle.x - 0.045, -0.06, 0), (ankle.x + 0.045, 0.18, 0.08))  # foot

        out, forward, bend = (math.radians(angle) for angle in arm)
        shoulder = Vector((side * SHOULDER[0], 0, SHOULDER[1]))
        elbow = shoulder + UPPER_ARM * hanging(side, out, forward)
        wrist = elbow + FOREARM * hanging(side, out, forward + bend)
        shape.tube(shoulder, elbow, (0.05, 0.04), SEGMENTS)
        shape.tube(elbow, wrist, (0.038, 0.03), SEGMENTS)
        ball(shape, shoulder, 0.06)
        ball(shape, elbow, 0.042)
        ball(shape, wrist + 0.04 * (wrist - elbow).normalized(), 0.045)  # the hand
    return shape


def hanging(side, out, forward):
    """The direction of an arm part swung `forward`, then raised `out` sideways."""
    down = Matrix.Rotation(forward, 3, "X") @ Vector((0, 0, -1))
    return Matrix.Rotation(-side * out, 3, "Y") @ down


def ball(shape, center, radius):
    shape.sphere(Matrix.Translation(center) @ Matrix.Scale(radius, 4), SEGMENTS, 6)
