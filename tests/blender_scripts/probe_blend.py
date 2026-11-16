"""Probe for tests/test_render.py: open a saved scene.blend and report what it holds.

Runs inside Blender through `artlab.blender.run_blender(this_file, [blend, out_json])`.
It opens `blend` with `bpy.ops.wm.open_mainfile` and writes JSON with the active
scene's camera and render resolution and, for every object in that scene, its
type, its `artlab_content` and `artlab_cutaway` tags and `hide_render`.
"""

import json
import sys

import bpy


def main():
    blend, out = sys.argv[sys.argv.index("--") + 1 :][:2]
    bpy.ops.wm.open_mainfile(filepath=blend)
    scene = bpy.context.scene
    report = {
        "file": bpy.data.filepath,
        "camera": scene.camera.name if scene.camera else None,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "objects": {
            obj.name: {
                "type": obj.type,
                "content": bool(obj.get("artlab_content")),
                "cutaway": bool(obj.get("artlab_cutaway")),
                "hide_render": bool(obj.hide_render),
            }
            for obj in scene.objects
        },
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)


main()
