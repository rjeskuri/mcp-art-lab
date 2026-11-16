"""The test scene's cameras, and `use_camera`, which applies the iso cutaway.

`Cam.Iso` is the main view: a 2:1 dimetric orthographic camera on the platform's
open (-Y) side, looking across it at the track. Rendered through it, the
`artlab_cutaway` objects (the canopy roof and its lamps) are hidden, like
lifting a hatch to see inside. `Cam.Hero` is a perspective at eye level just
past the platform's +X end, looking back along it at the arriving train. Styles
never hide content: whatever renders the scene calls `use_camera` per camera.
"""

import math

import bpy
from mathutils import Euler, Vector

from .station import DECK_TOP

CAMERAS = {"iso": "Cam.Iso", "hero": "Cam.Hero"}
CAMERA_ORDER = ("iso", "hero")  # the primary view first
CUTAWAY_CAMERAS = frozenset({"iso"})

ISO_ROTATION = (math.radians(60), 0.0, math.radians(45))  # 2:1 dimetric
# The ground point at the center of the iso frame, which centers the station's
# projected bounds; the camera backs away from it along its view.
ISO_TARGET = (-2.7, 1.9, 0.0)
ISO_DISTANCE = 60.0
ISO_SCALE = 40.0  # fits the 40 m ground plane with a margin

# Eye level just past the deck's +X end: far enough back that the vending
# machine, the people and the cab front all fit without a fisheye lens.
HERO_LOCATION = (12.5, -1.4, DECK_TOP + 1.9)
HERO_TARGET = (2.0, -2.2, DECK_TOP + 1.55)
HERO_LENS = 26.0


def add_iso_camera(scene):
    """Link `Cam.Iso` into `scene`; returns the object."""
    rotation = Euler(ISO_ROTATION, "XYZ")
    forward = rotation.to_matrix() @ Vector((0.0, 0.0, -1.0))
    location = Vector(ISO_TARGET) - ISO_DISTANCE * forward
    cam = camera(scene, CAMERAS["iso"], "ORTHO", location, rotation)
    cam.data.ortho_scale = ISO_SCALE
    return cam


def add_hero_camera(scene):
    """Link `Cam.Hero` into `scene`; returns the object."""
    location = Vector(HERO_LOCATION)
    view = Vector(HERO_TARGET) - location
    rotation = view.to_track_quat("-Z", "Y").to_euler("XYZ")
    cam = camera(scene, CAMERAS["hero"], "PERSP", location, rotation)
    cam.data.lens = HERO_LENS
    return cam


def use_camera(scene, key):
    """Render through camera `key`: set `scene.camera` and apply its cutaway.

    The `artlab_cutaway` objects are hidden from render for the cameras in
    `CUTAWAY_CAMERAS` and shown for the rest. A key not in `CAMERAS` raises
    KeyError before anything changes.
    """
    cam = scene.objects[CAMERAS[key]]
    hide = key in CUTAWAY_CAMERAS
    scene.camera = cam
    for obj in scene.objects:
        if obj.get("artlab_cutaway"):
            obj.hide_render = hide


def camera(scene, name, kind, location, rotation):
    data = bpy.data.cameras.new(name)
    data.type = kind
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    obj.rotation_euler = rotation
    scene.collection.objects.link(obj)
    return obj
