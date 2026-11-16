"""Probe for tests/test_train_people_cameras.py: build the test scene, report it.

Runs inside Blender through `artlab.blender.run_blender(this_file, [out_json])`.
It starts from an empty factory scene, calls `build_test_scene`, and writes JSON
with the facts the tests assert on, all read from Blender itself, in this order
so that nothing a later step changes reaches an earlier one:

1. the built scene: every object's world-space bound box (of the evaluated
   object), `artlab_*` tags, `hide_render`, transform, modifiers, evaluated
   polygon smoothing, camera and light data, and `scene.camera`;
2. framing: at a square resolution, every content object's 8 bound-box corners
   and center projected through `Cam.Iso` and `Cam.Hero` with
   `bpy_extras.object_utils.world_to_camera_view`;
3. the fingerprint of #4's determinism test, plus the cameras;
4. the `cameras` constants, then `use_camera` called with `USE_SEQUENCE`
   (recording `scene.camera` and the objects with `hide_render` after each
   call), then with each of `BAD_KEYS`, recording what it raised.

A step that raises is recorded under "errors" and the probe carries on, so each
test fails on the behavior it checks and names the error (a missing module, a
missing object) instead of every test erroring on the first one.
"""

import importlib
import json
import math
import sys
import traceback

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

CAMERA_NAMES = ("Cam.Iso", "Cam.Hero")
# Starts with "hero" so a toggle cannot pass, and repeats keys for idempotence.
USE_SEQUENCE = ("hero", "iso", "iso", "hero", "hero", "iso")
BAD_KEYS = ("top", "ISO", "Iso", "Cam.Iso", "Cam.Hero", "")
SQUARE = 1024

errors = {}


def attempt(step, fn):
    """`fn()`, or None with the error and where it was raised in `errors[step]`."""
    try:
        return fn()
    except Exception as exc:
        where = traceback.extract_tb(exc.__traceback__)[-1]
        message = "".join(traceback.format_exception_only(exc)).strip()
        errors[step] = f"{message} (at {where.filename}:{where.lineno})"
        return None


def plain(value):
    """A custom property value as JSON: scalars as they are, anything else as repr."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return repr(value)


def world_corners(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    return [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]


def object_report(obj, depsgraph):
    corners = world_corners(obj, depsgraph)
    rotation = obj.matrix_world.decompose()[1].to_euler("XYZ")
    report = {
        "type": obj.type,
        "props": {k: plain(obj[k]) for k in obj.keys() if k.startswith("artlab_")},
        "bbox_min": [min(c[i] for c in corners) for i in range(3)],
        "bbox_max": [max(c[i] for c in corners) for i in range(3)],
        "hide_render": bool(obj.hide_render),
        "location": list(obj.matrix_world.translation),
        "rotation_mode": obj.rotation_mode,
        "rotation_euler_deg": [math.degrees(a) for a in obj.rotation_euler],
        "world_rotation_deg": [math.degrees(a) for a in rotation],
        "modifiers": [
            {
                "type": mod.type,
                "show_render": bool(mod.show_render),
                "render_levels": getattr(mod, "render_levels", None),
            }
            for mod in obj.modifiers
        ],
        "materials": [
            slot.material.name if slot.material else None for slot in obj.material_slots
        ],
        "vertices": None,
        "polygons": None,
        "smooth_polygons": None,
    }
    if obj.type == "MESH":
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        report["vertices"] = len(mesh.vertices)
        report["polygons"] = len(mesh.polygons)
        report["smooth_polygons"] = sum(1 for p in mesh.polygons if p.use_smooth)
        evaluated.to_mesh_clear()
    elif obj.type == "LIGHT":
        report["light"] = {
            "type": obj.data.type,
            "energy": obj.data.energy,
            "color": list(obj.data.color),
        }
    elif obj.type == "CAMERA":
        cam = obj.data
        report["camera"] = {
            "type": cam.type,
            "lens": cam.lens,
            "ortho_scale": cam.ortho_scale,
            "clip_start": cam.clip_start,
            "clip_end": cam.clip_end,
        }
    return report


def framing(scene, depsgraph):
    """Content corners and centers projected through each camera, square frame."""
    scene.render.resolution_x = SQUARE
    scene.render.resolution_y = SQUARE
    bpy.context.view_layer.update()
    content = [obj for obj in scene.objects if obj.get("artlab_content")]
    result = {}
    for cam_name in CAMERA_NAMES:
        cam = scene.objects.get(cam_name)
        if cam is None or cam.type != "CAMERA":
            errors[f"framing {cam_name}"] = f"no camera object {cam_name!r}"
            continue
        projected = {}
        for obj in content:
            corners = world_corners(obj, depsgraph)
            center = sum(corners, Vector()) / len(corners)
            projected[obj.name] = {
                "corners": [list(world_to_camera_view(scene, cam, c)) for c in corners],
                "center": list(world_to_camera_view(scene, cam, center)),
            }
        result[cam_name] = {
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "objects": projected,
        }
    return result


def r4(values):
    return [round(v, 4) for v in values]


def fingerprint(objects):
    """#4's fingerprint (objects and lights), plus each camera's lens and pose."""
    rows, lights, cameras = [], [], []
    for name in sorted(objects):
        o = objects[name]
        rows.append(
            [
                name,
                o["type"],
                o["props"].get("artlab_role"),
                o["props"].get("artlab_cutaway"),
                o["vertices"],
                r4(o["bbox_min"]),
                r4(o["bbox_max"]),
                o["materials"],
            ]
        )
        if "light" in o:
            light = o["light"]
            lights.append(
                [name, light["type"], round(light["energy"], 4), r4(light["color"])]
            )
        if "camera" in o:
            cam = o["camera"]
            cameras.append(
                [
                    name,
                    cam["type"],
                    round(cam["lens"], 4),
                    round(cam["ortho_scale"], 4),
                    r4(o["location"]),
                    r4(o["world_rotation_deg"]),
                ]
            )
    return {"objects": rows, "lights": lights, "cameras": cameras}


def camera_constants(cameras):
    return {
        "CAMERAS": dict(cameras.CAMERAS),
        "CAMERA_ORDER": list(cameras.CAMERA_ORDER),
        "CUTAWAY_CAMERAS": sorted(cameras.CUTAWAY_CAMERAS),
        "types": {
            name: type(getattr(cameras, name)).__name__
            for name in ("CAMERAS", "CAMERA_ORDER", "CUTAWAY_CAMERAS")
        },
    }


def scene_camera(scene):
    return scene.camera.name if scene.camera else None


def use_camera_report(scene, cameras):
    steps = []
    for key in USE_SEQUENCE:
        cameras.use_camera(scene, key)
        steps.append(
            {
                "key": key,
                "camera": scene_camera(scene),
                "hidden": sorted(o.name for o in scene.objects if o.hide_render),
            }
        )
    refused = {}
    for key in BAD_KEYS:
        try:
            cameras.use_camera(scene, key)
        except KeyError:
            refused[key] = "KeyError"
        except Exception as exc:
            refused[key] = type(exc).__name__
        else:
            refused[key] = None
    return {"steps": steps, "refused": refused}


def main():
    out_path = sys.argv[sys.argv.index("--") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    data = {"errors": errors}

    testscene = attempt(
        "import testscene",
        lambda: importlib.import_module("artlab.inblender.testscene"),
    )
    cameras = attempt(
        "import cameras", lambda: importlib.import_module("artlab.inblender.cameras")
    )
    if testscene is not None:
        data["constants"] = {
            "CONTENT": [list(pair) for pair in testscene.CONTENT],
            "CUTAWAY": list(testscene.CUTAWAY),
        }
        attempt("build_test_scene", lambda: testscene.build_test_scene(scene))

    # 1. The scene as built, before anything else touches it.
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = {obj.name: object_report(obj, depsgraph) for obj in scene.objects}
    data["objects"] = objects
    data["scene_camera"] = scene_camera(scene)

    # 2. Framing, read-only: projection does not depend on scene.camera.
    data["framing"] = attempt("framing", lambda: framing(scene, depsgraph))

    # 3. The determinism fingerprint.
    data["fingerprint"] = fingerprint(objects)

    # 4. The camera API, last, since use_camera changes hide_render.
    if cameras is not None:
        data["camera_constants"] = attempt(
            "camera constants", lambda: camera_constants(cameras)
        )
        data["use_camera"] = attempt(
            "use_camera", lambda: use_camera_report(scene, cameras)
        )

    with open(out_path, "w") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)


main()
