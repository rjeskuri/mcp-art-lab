"""Probe for tests/test_manifest.py: build a small fixed scene, write its manifest.

Run through `artlab.blender.run_blender(this_file, [out_path, variant])`.
`variant` is "base" (the scene the ticket describes, with a world) or "noworld"
(the same objects with other values, tags and render settings, and no world).

Writes `out_path` with `write_manifest` and `out_path + ".dict.json"` with
`json.dumps(scene_manifest(...))`, so the tests can check both public functions,
and `out_path + ".facts.json"` with what the probe itself reads from Blender.
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy


def new_material(name, idnames, ramps=()):
    """A material whose node tree holds exactly `idnames` plus the named `ramps`."""
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    for idname in idnames:
        nodes.new(idname)
    for node_name, interpolation in ramps:
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.name = node_name
        ramp.color_ramp.interpolation = interpolation
    return mat


def mesh_object(name, build):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build_scene(variant):
    base = variant == "base"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    render = scene.render
    render.resolution_percentage = 100
    if base:
        render.engine = "BLENDER_WORKBENCH"
        render.resolution_x, render.resolution_y = 640, 360
        render.film_transparent = True
        render.use_freestyle = True
        scene.view_settings.view_transform = "Standard"
    else:
        render.engine = "CYCLES"
        render.resolution_x, render.resolution_y = 320, 240
        render.film_transparent = False
        render.use_freestyle = False
        scene.view_settings.view_transform = "AgX"

    principled = ["ShaderNodeOutputMaterial", "ShaderNodeBsdfPrincipled"]
    box_mat = new_material(
        "Box.Mat", principled, ramps=[("Ramp", "CONSTANT")] if base else []
    )
    # Two ramps created B-first: ordered by node name the result is LINEAR, CONSTANT.
    ball_mat = new_material(
        "Ball.Mat",
        ["ShaderNodeEmission", "ShaderNodeOutputMaterial"],
        ramps=[("Ramp.B", "CONSTANT"), ("Ramp.A", "LINEAR")],
    )
    accent_mat = new_material("Accent.Mat", ["ShaderNodeOutputMaterial"])
    new_material("Orphan.Mat", principled, ramps=[("Ramp", "EASE")])
    stray_mat = new_material("Stray.Mat", principled)

    box = mesh_object("Box", lambda bm: bmesh.ops.create_cube(bm, size=2.0))
    box.data.materials.append(box_mat)
    if base:
        box.location = (-0.0, 1.23456789, 2.0)
        box.rotation_euler = (math.radians(30), 0.0, math.radians(-45))
        box.scale = (1.0, 2.0, 0.5)
        box["artlab_content"] = True
        box["artlab_role"] = "wall"
    else:
        box.location = (0.5, -0.0, -2.25)
        box.rotation_euler = (0.0, math.radians(90), 0.0)
        box.scale = (3.0, 3.0, 3.0)

    ball = mesh_object(
        "Ball",
        lambda bm: bmesh.ops.create_uvsphere(
            bm, u_segments=32, v_segments=16, radius=1.0
        ),
    )
    # Smooth only the 64 pole triangles: each becomes 3 quads under SUBSURF.
    for poly in ball.data.polygons:
        poly.use_smooth = len(poly.vertices) == 3
    ball.data.materials.append(ball_mat)
    ball.data.materials.append(accent_mat)
    subsurf = ball.modifiers.new("Subdivision", "SUBSURF")
    subsurf.levels = 1
    subsurf.render_levels = 1
    ball.location = (3.0, 0.0, 0.0)
    ball.rotation_euler = (0.0, 0.0, -0.0)
    ball.hide_render = True
    if not base:
        ball["artlab_content"] = 1
        ball["artlab_role"] = "prop"

    cam_data = bpy.data.cameras.new("Cam")
    if base:
        cam_data.type = "ORTHO"
        cam_data.lens = 35.0
        cam_data.ortho_scale = 12.5
    else:
        cam_data.type = "PERSP"
        cam_data.lens = 85.0
        cam_data.ortho_scale = 4.25
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (10.0, -10.0, 8.0)
    cam.rotation_euler = (math.radians(60), 0.0, math.radians(45))
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    if base:
        sun_data.energy = 3.5
        sun_data.color = (1.0, 0.9, 0.8)
    else:
        sun_data.energy = 0.25
        sun_data.color = (0.6, 0.7, 1.0)
    sun = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 20.0)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(30))

    # An object outside the scene: neither it nor its material is in the manifest.
    stray = bpy.data.objects.new("Stray", bpy.data.meshes.new("Stray"))
    stray.data.materials.append(stray_mat)

    if base:
        world = bpy.data.worlds.new("Probe.World")
        if world.node_tree is None:
            world.use_nodes = True
        world.node_tree.nodes.clear()
        for idname in [
            "ShaderNodeTexGradient",
            "ShaderNodeOutputWorld",
            "ShaderNodeBackground",
        ]:
            world.node_tree.nodes.new(idname)
        scene.world = world
    else:
        scene.world = None
        for world in list(bpy.data.worlds):
            bpy.data.worlds.remove(world)
    return scene


def main():
    after = sys.argv[sys.argv.index("--") + 1 :]
    out, variant = after[0], after[1]
    scene = build_scene(variant)
    facts = {"blender": bpy.app.version_string}
    Path(out + ".facts.json").write_text(json.dumps(facts))

    from artlab.inblender.manifest import scene_manifest, write_manifest

    if variant == "base":
        write_manifest(scene, out, style="plain")
        manifest = scene_manifest(scene, style="plain")
    else:
        write_manifest(scene, Path(out), style="toon-test")
        manifest = scene_manifest(scene, style="toon-test")
    Path(out + ".dict.json").write_text(json.dumps(manifest))


if __name__ == "__main__":
    main()
