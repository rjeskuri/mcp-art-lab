"""A deterministic JSON manifest of a scene: the same scene gives the same bytes."""

import json
import math
from pathlib import Path

import bpy

DECIMALS = 4
RAMP_IDNAME = "ShaderNodeValToRGB"


def _num(value: float) -> float:
    """Round to DECIMALS, writing -0.0 as 0.0."""
    return round(float(value), DECIMALS) + 0.0


def _triple(values) -> list[float]:
    return [_num(v) for v in values]


def _nodes(node_tree) -> list[str]:
    if node_tree is None:
        return []
    return sorted({node.bl_idname for node in node_tree.nodes})


def _color_ramps(node_tree) -> list[str]:
    if node_tree is None:
        return []
    ramps = [n for n in node_tree.nodes if n.bl_idname == RAMP_IDNAME]
    return [n.color_ramp.interpolation for n in sorted(ramps, key=lambda n: n.name)]


def _mesh_counts(obj, depsgraph) -> dict:
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return {
            "vertices": len(mesh.vertices),
            "faces": len(mesh.polygons),
            "smooth_faces": sum(1 for poly in mesh.polygons if poly.use_smooth),
        }
    finally:
        evaluated.to_mesh_clear()


def _object(obj, depsgraph) -> dict:
    role = obj.get("artlab_role")
    entry = {
        "type": obj.type,
        "content": bool(obj.get("artlab_content")),
        "role": None if role is None else str(role),
        "location": _triple(obj.location),
        "rotation_deg": _triple(math.degrees(a) for a in obj.rotation_euler),
        "scale": _triple(obj.scale),
        "hide_render": bool(obj.hide_render),
        "modifiers": [mod.type for mod in obj.modifiers],
        "materials": [slot.name for slot in obj.material_slots],
    }
    if obj.type == "MESH":
        entry.update(_mesh_counts(obj, depsgraph))
    elif obj.type == "CAMERA":
        cam = obj.data
        entry["camera"] = {
            "type": cam.type,
            "lens": _num(cam.lens),
            "ortho_scale": _num(cam.ortho_scale),
        }
    elif obj.type == "LIGHT":
        light = obj.data
        entry["light"] = {
            "type": light.type,
            "energy": _num(light.energy),
            "color": _triple(light.color),
        }
    return entry


def scene_manifest(scene, *, style: str) -> dict:
    """Describe `scene` as plain JSON-ready data; floats rounded, angles in degrees."""
    depsgraph = scene.view_layers[0].depsgraph
    depsgraph.update()
    render = scene.render
    objects = {obj.name: _object(obj, depsgraph) for obj in scene.objects}
    materials = {
        slot.material.name: {
            "nodes": _nodes(slot.material.node_tree),
            "color_ramps": _color_ramps(slot.material.node_tree),
        }
        for obj in scene.objects
        for slot in obj.material_slots
        if slot.material is not None
    }
    world = scene.world
    return {
        "blender": bpy.app.version_string,
        "style": style,
        "render": {
            "engine": render.engine,
            "resolution": [int(render.resolution_x), int(render.resolution_y)],
            "film_transparent": bool(render.film_transparent),
            "view_transform": scene.view_settings.view_transform,
            "use_freestyle": bool(render.use_freestyle),
        },
        "world": None
        if world is None
        else {"name": world.name, "nodes": _nodes(world.node_tree)},
        "objects": objects,
        "materials": materials,
    }


def write_manifest(scene, path: str | Path, *, style: str) -> None:
    """Write scene_manifest(scene) as sorted, 2-space-indented JSON with a newline."""
    manifest = scene_manifest(scene, style=style)
    text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8")
