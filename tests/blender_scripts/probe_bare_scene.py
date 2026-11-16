"""Probe for tests/test_render.py: the manifest of the test scene with no style applied.

Runs inside Blender through `artlab.blender.run_blender(this_file, [out_json])`.
It resets to an empty factory scene, calls `build_test_scene` and nothing else,
and writes the scene's manifest with `style="plain"`: what `artlab render plain
--no-render` must write when `plain` changes nothing.
"""

import sys

import bpy

from artlab.inblender.manifest import write_manifest
from artlab.inblender.testscene import build_test_scene


def main():
    out = sys.argv[sys.argv.index("--") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    build_test_scene(scene)
    write_manifest(scene, out, style="plain")


main()
