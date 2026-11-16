"""The shared test scene: role palette, base materials, night world, render settings.

`build_test_scene` fills an empty scene. Each builder module (`station`, `train`,
`people`) makes its meshes and hands them to `add_content`, which links them as
content objects tagged `artlab_content` and `artlab_role` (looked up in
`CONTENT`) with the `base.<role>` materials, then `cameras` adds the two views.
Styles find the content with `content_objects`.
"""

import functools

import bpy

from . import cameras, people, station, train

# Default base color (linear RGBA) for every role in the scene.
ROLES = {
    "ground": (0.05, 0.05, 0.055, 1.0),
    "concrete": (0.32, 0.32, 0.31, 1.0),
    "platform": (0.42, 0.41, 0.39, 1.0),
    "tactile": (0.85, 0.62, 0.02, 1.0),
    "rail": (0.36, 0.34, 0.32, 1.0),
    "steel": (0.12, 0.13, 0.15, 1.0),
    "roof": (0.5, 0.52, 0.55, 1.0),
    "lamp": (0.92, 0.96, 1.0, 1.0),
    "sign": (0.85, 0.86, 0.84, 1.0),
    "bench": (0.1, 0.28, 0.5, 1.0),
    "vending": (0.72, 0.73, 0.75, 1.0),
    "vending_glow": (0.85, 0.93, 1.0, 1.0),
    "train_body": (0.7, 0.72, 0.75, 1.0),
    "train_window": (1.0, 0.92, 0.75, 1.0),
    "train_light": (1.0, 0.96, 0.85, 1.0),
    "person_skin": (0.78, 0.58, 0.45, 1.0),
    "person_cloth": (0.1, 0.11, 0.16, 1.0),
}
EMISSIVE_ROLES = ("lamp", "vending_glow", "train_window", "train_light")
EMISSION_STRENGTH = 5.0

# Content objects as (name, role), in build order: the station, the train, the people.
CONTENT = (
    ("Ground", "ground"),
    ("Viaduct", "concrete"),
    ("Platform.Deck", "platform"),
    ("Platform.Tactile", "tactile"),
    ("Track.Bed", "concrete"),
    ("Track.Rails", "rail"),
    ("Canopy.Posts", "steel"),
    ("Canopy.Roof", "roof"),
    ("Platform.Lamps", "lamp"),
    ("Sign", "sign"),
    ("Bench", "bench"),
    ("Vending.Body", "vending"),
    ("Vending.Front", "vending_glow"),
    ("Train.Body", "train_body"),
    ("Train.Nose", "train_body"),
    ("Train.Windows", "train_window"),
    ("Train.Headlights", "train_light"),
    ("Person.1.Head", "person_skin"),
    ("Person.1.Body", "person_cloth"),
    ("Person.2.Head", "person_skin"),
    ("Person.2.Body", "person_cloth"),
    ("Person.3.Head", "person_skin"),
    ("Person.3.Body", "person_cloth"),
)
# Content the iso camera cuts away to show the inside.
CUTAWAY = ("Canopy.Roof", "Platform.Lamps")

NIGHT_SKY = (0.008, 0.012, 0.03, 1.0)


def build_test_scene(scene):
    """Build the station at night into `scene`, which starts empty.

    Both cameras are added and `Cam.Iso` is active, with nothing hidden: the
    cutaway is applied per camera by `cameras.use_camera`.
    """
    for role in ROLES:
        base_material(role)
    add = functools.partial(add_content, scene)
    station.build(scene, add)
    train.build(scene, add)
    people.build(add)
    scene.camera = cameras.add_iso_camera(scene)
    cameras.add_hero_camera(scene)
    night_world(scene)
    render_settings(scene)


def content_objects(scene):
    """The scene's objects tagged `artlab_content`, sorted by name."""
    return sorted(
        (obj for obj in scene.objects if obj.get("artlab_content")),
        key=lambda obj: obj.name,
    )


def add_content(scene, name, mesh, *extra_roles):
    """Link `mesh` into `scene` as content object `name`, tagged with its role.

    Material slot 0 is `base.<role>`; `extra_roles` fill slots 1, 2, ... for the
    polygons whose `material_index` points at them.
    """
    role = dict(CONTENT)[name]
    for slot_role in (role, *extra_roles):
        mesh.materials.append(bpy.data.materials[f"base.{slot_role}"])
    obj = bpy.data.objects.new(name, mesh)
    obj["artlab_content"] = True
    obj["artlab_role"] = role
    if name in CUTAWAY:
        obj["artlab_cutaway"] = True
    scene.collection.objects.link(obj)
    return obj


def socket(sockets, identifier):
    """The socket with `identifier`; names are localized, identifiers are not."""
    return next(s for s in sockets if s.identifier == identifier)


def base_material(role):
    """`base.<role>`: an Emission for emissive roles, else a Principled BSDF."""
    name = f"base.{role}"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    color = ROLES[role]
    material.diffuse_color = color
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    if role in EMISSIVE_ROLES:
        shader = tree.nodes.new("ShaderNodeEmission")
        socket(shader.inputs, "Color").default_value = color
        socket(shader.inputs, "Strength").default_value = EMISSION_STRENGTH
    else:
        shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
        socket(shader.inputs, "Base Color").default_value = color
    shader.location = (-300, 0)
    tree.links.new(shader.outputs[0], socket(output.inputs, "Surface"))
    return material


def night_world(scene):
    """World `World`: one constant, near-black blue Background."""
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    world.color = NIGHT_SKY[:3]
    tree = world.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputWorld")
    background = tree.nodes.new("ShaderNodeBackground")
    background.location = (-300, 0)
    socket(background.inputs, "Color").default_value = NIGHT_SKY
    socket(background.inputs, "Strength").default_value = 1.0
    tree.links.new(background.outputs[0], socket(output.inputs, "Surface"))
    scene.world = world


def render_settings(scene):
    render = scene.render
    render.engine = "BLENDER_EEVEE"
    render.resolution_x = 1024
    render.resolution_y = 1024
    render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "None"
