"""Probe for tests/test_station.py: build the test scene and report what it holds.

Runs inside Blender through `artlab.blender.run_blender(this_file, [out_json])`.
It starts from an empty factory scene, calls `build_test_scene`, and writes JSON
with the facts the tests assert on, all worked out here from Blender itself:
world-space bound boxes of the evaluated objects, `artlab_*` custom properties,
material and world node inputs (nodes found by `bl_idname`, sockets by
`identifier`, never by localized name), lights, render settings, the
`testscene` constants, and a fingerprint for the determinism test.
"""

import json
import sys

import bpy
from mathutils import Vector

from artlab.inblender import testscene


def plain(value):
    """A custom property value as JSON: scalars as they are, anything else as repr."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return repr(value)


def input_socket(node, identifier):
    for socket in node.inputs:
        if socket.identifier == identifier:
            return socket
    raise KeyError(f"{node.bl_idname} has no input {identifier!r}")


def upstream(socket):
    """Every node that feeds `socket`, directly or through other nodes."""
    found = {}
    stack = [socket]
    while stack:
        for link in stack.pop().links:
            if link.is_muted or not link.is_valid:
                continue
            node = link.from_node
            if node.name not in found:
                found[node.name] = node
                stack.extend(node.inputs)
    return list(found.values())


def active_output(tree, bl_idname):
    outputs = [node for node in tree.nodes if node.bl_idname == bl_idname]
    active = [node for node in outputs if node.is_active_output]
    return (active or outputs or [None])[0]


def material_report(material):
    if material is None:
        return None
    tree = material.node_tree
    emission = []
    if tree is not None:
        output = active_output(tree, "ShaderNodeOutputMaterial")
        feeding = set()
        if output is not None:
            feeding = {node.name for node in upstream(input_socket(output, "Surface"))}
        for node in sorted(tree.nodes, key=lambda n: n.name):
            if node.bl_idname != "ShaderNodeEmission":
                continue
            color = input_socket(node, "Color")
            strength = input_socket(node, "Strength")
            emission.append(
                {
                    "color": list(color.default_value),
                    "color_linked": color.is_linked,
                    "strength": strength.default_value,
                    "strength_linked": strength.is_linked,
                    "feeds_output": node.name in feeding,
                }
            )
    return {"name": material.name, "emission": emission}


def world_report(world):
    if world is None:
        return None
    tree = world.node_tree
    if tree is None:
        return {"name": world.name, "surface_upstream": [], "backgrounds": []}
    output = active_output(tree, "ShaderNodeOutputWorld")
    surface = []
    if output is not None:
        surface = sorted(n.bl_idname for n in upstream(input_socket(output, "Surface")))
    backgrounds = []
    for node in tree.nodes:
        if node.bl_idname != "ShaderNodeBackground":
            continue
        color = input_socket(node, "Color")
        strength = input_socket(node, "Strength")
        backgrounds.append(
            {
                "color": list(color.default_value),
                "color_linked": color.is_linked,
                "strength": strength.default_value,
                "strength_linked": strength.is_linked,
            }
        )
    return {"name": world.name, "surface_upstream": surface, "backgrounds": backgrounds}


def object_report(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    corners = [
        evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box
    ]
    vertices = None
    if obj.type == "MESH":
        mesh = evaluated.to_mesh()
        vertices = len(mesh.vertices)
        evaluated.to_mesh_clear()
    slots = obj.material_slots
    report = {
        "type": obj.type,
        "props": {k: plain(obj[k]) for k in obj.keys() if k.startswith("artlab_")},
        "bbox_min": [min(c[i] for c in corners) for i in range(3)],
        "bbox_max": [max(c[i] for c in corners) for i in range(3)],
        "vertices": vertices,
        "materials": [slot.material.name if slot.material else None for slot in slots],
        "first_material": material_report(slots[0].material) if slots else None,
    }
    if obj.type == "LIGHT":
        report["light"] = {
            "type": obj.data.type,
            "energy": obj.data.energy,
            "color": list(obj.data.color),
        }
    return report


def r4(values):
    return [round(v, 4) for v in values]


def fingerprint(objects):
    rows = []
    lights = []
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
    return {"objects": rows, "lights": lights}


def main():
    out_path = sys.argv[sys.argv.index("--") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    testscene.build_test_scene(scene)

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = {obj.name: object_report(obj, depsgraph) for obj in scene.objects}
    returned = testscene.content_objects(scene)
    render = scene.render
    data = {
        "constants": {
            "CONTENT": [list(pair) for pair in testscene.CONTENT],
            "CUTAWAY": list(testscene.CUTAWAY),
            "EMISSIVE_ROLES": list(testscene.EMISSIVE_ROLES),
            "ROLES": {role: list(rgba) for role, rgba in testscene.ROLES.items()},
            "types": {
                "CONTENT": type(testscene.CONTENT).__name__,
                "CUTAWAY": type(testscene.CUTAWAY).__name__,
                "EMISSIVE_ROLES": type(testscene.EMISSIVE_ROLES).__name__,
                "ROLES": type(testscene.ROLES).__name__,
            },
        },
        "content_objects": {
            "is_list": isinstance(returned, list),
            "all_objects": all(isinstance(o, bpy.types.Object) for o in returned),
            "names": [o.name for o in returned],
        },
        "objects": objects,
        "world": world_report(scene.world),
        "render": {
            "engine": render.engine,
            "resolution_x": render.resolution_x,
            "resolution_y": render.resolution_y,
            "resolution_percentage": render.resolution_percentage,
        },
        "fingerprint": fingerprint(objects),
    }
    with open(out_path, "w") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)


main()
