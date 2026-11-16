"""The script `artlab render` runs in Blender: one style, built, checked and rendered.

Run through `artlab.blender.run_blender(this_file, args)`, where args are
`STYLE BUILD_PY OUT_DIR [--size N] [--camera KEY ...] [--save-blend]`. It resets
to an empty factory scene, builds the test scene, calls the style's
`build(scene)` and refuses (exit 1, naming the objects) if the style deleted,
renamed, moved, rotated, scaled or hid content. Then it sets the square
resolution and PNG RGBA 8-bit output, writes `OUT_DIR/manifest.json` (and
`scene.blend`) with the scene uncut, and renders each `--camera`, in
`CAMERA_ORDER`, through `use_camera` to `OUT_DIR/<key>.png`.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import bpy

from artlab.inblender.cameras import CAMERA_ORDER, use_camera
from artlab.inblender.manifest import write_manifest
from artlab.inblender.testscene import build_test_scene, content_objects

TOLERANCE = 1e-4


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="artlab.inblender.runner")
    parser.add_argument("style")
    parser.add_argument("build_py", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--camera", action="append", choices=CAMERA_ORDER, default=[])
    parser.add_argument("--save-blend", action="store_true")
    return parser.parse_args(argv)


def refuse(message):
    print(f"artlab render: {message}", file=sys.stderr, flush=True)
    sys.exit(1)


def snapshot(scene):
    """Each content object's name -> (world matrix, hide_render)."""
    scene.view_layers[0].update()  # world matrices follow parents and constraints
    return {
        obj.name: (obj.matrix_world.copy(), obj.hide_render)
        for obj in content_objects(scene)
    }


def differs(a, b):
    """Whether two equal-length float sequences differ by more than TOLERANCE."""
    return any(abs(x - y) > TOLERANCE for x, y in zip(a, b, strict=True))


def flat(matrix):
    return [x for row in matrix for x in row]


def content_changes(before, scene):
    """Content object name -> what the style did to it, for each one it changed."""
    after = snapshot(scene)
    changes = {}
    for name, (matrix, hidden) in before.items():
        if name not in after:
            changes[name] = ["deleted or renamed"]
            continue
        now_matrix, now_hidden = after[name]
        loc, rot, scale = matrix.decompose()
        now_loc, now_rot, now_scale = now_matrix.decompose()
        kinds = []
        if differs(loc, now_loc):
            kinds.append("moved")
        if differs(flat(rot.to_matrix()), flat(now_rot.to_matrix())):
            kinds.append("rotated")
        if differs(scale, now_scale):
            kinds.append("scaled")
        if now_hidden != hidden:
            kinds.append("hidden" if now_hidden else "unhidden")
        if kinds:
            changes[name] = kinds
    return changes


def load_build(style, path):
    """The `build` function of the style file at `path`."""
    module_name = f"artlab_style_{style}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    build = getattr(module, "build", None)
    if not callable(build):
        refuse(f"style {style!r} defines no build(scene) function in {path}")
    return build


def set_output(scene, size):
    render = scene.render
    render.resolution_x = size
    render.resolution_y = size
    render.resolution_percentage = 100
    image = render.image_settings
    image.media_type = "IMAGE"
    image.file_format = "PNG"
    image.color_mode = "RGBA"
    image.color_depth = "8"


def main():
    args = parse_args(sys.argv[sys.argv.index("--") + 1 :])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    build_test_scene(scene)
    before = snapshot(scene)

    load_build(args.style, args.build_py)(scene)
    changes = content_changes(before, scene)
    if changes:
        lines = [f"  {name}: {', '.join(kinds)}" for name, kinds in changes.items()]
        refuse(
            f"style {args.style!r} changed content objects, which styles may not "
            "delete, rename, move, rotate, scale or hide:\n" + "\n".join(lines)
        )

    set_output(scene, args.size)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    write_manifest(scene, out / "manifest.json", style=args.style)
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"), copy=True)

    for key in CAMERA_ORDER:
        if key in args.camera:
            use_camera(scene, key)
            scene.render.filepath = str(out / f"{key}.png")
            if bpy.ops.render.render(write_still=True) != {"FINISHED"}:
                raise RuntimeError(f"rendering camera {key!r} did not finish")


if __name__ == "__main__":
    main()
