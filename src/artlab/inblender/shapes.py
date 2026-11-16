"""`Shape`, the mesh builder for the train and the people: boxes, lofts, spheres.

A `Shape` collects vertices and faces, each face with a material slot, and makes
them into one mesh. Faces are wound so normals point out.
"""

import math

import bpy
from mathutils import Vector

from .station import BOX_FACES


class Shape:
    def __init__(self):
        self.verts, self.faces, self.slots = [], [], []

    def add(self, verts, faces, slot=0):
        first = len(self.verts)
        self.verts += [tuple(v) for v in verts]
        self.faces += [[first + i for i in face] for face in faces]
        self.slots += [slot] * len(faces)

    def box(self, lo, hi, slot=0):
        """An axis-aligned box from corner `lo` to corner `hi`."""
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        self.add([(x, y, z) for z in (z0, z1) for x, y in corners], BOX_FACES, slot)

    def loft(self, rings, slot=0):
        """Join rings of equal length side to side, and cap the first and last.

        Each ring runs counterclockwise seen from beyond the last ring.
        """
        n = len(rings[0])
        last = (len(rings) - 1) * n
        faces = [list(range(n - 1, -1, -1)), [last + i for i in range(n)]]
        for a in range(0, last, n):
            b = a + n
            faces += [
                [a + i, a + (i + 1) % n, b + (i + 1) % n, b + i] for i in range(n)
            ]
        self.add([v for ring in rings for v in ring], faces, slot)

    def tube(self, start, end, radii, segments, flatten=1.0, slot=0):
        """A capped cylinder from `start` to `end`, tapering between `radii`.

        `flatten` scales its section across, along the local Y that `start` to
        `end` tracks with (the world Y for an upright tube).
        """
        start, end = Vector(start), Vector(end)
        turn = (end - start).to_track_quat("Z", "Y").to_matrix()
        angles = [2 * math.pi * i / segments for i in range(segments)]
        rings = [
            [
                center + turn @ Vector((r * math.cos(a), flatten * r * math.sin(a), 0))
                for a in angles
            ]
            for center, r in zip((start, end), radii, strict=True)
        ]
        self.loft(rings, slot)

    def sphere(self, matrix, segments, rings, slot=0):
        """A UV sphere of radius 1 placed by `matrix`: `segments` by `rings`."""
        verts = [Vector((0, 0, 1))]
        for k in range(1, rings):
            polar = math.pi * k / rings
            across, up = math.sin(polar), math.cos(polar)
            verts += [
                Vector((across * math.cos(a), across * math.sin(a), up))
                for a in (2 * math.pi * j / segments for j in range(segments))
            ]
        verts.append(Vector((0, 0, -1)))
        bottom = len(verts) - 1

        def at(k, j):  # vertex j of ring k, for k in 1 .. rings - 1
            return 1 + (k - 1) * segments + j % segments

        faces = [(0, at(1, j), at(1, j + 1)) for j in range(segments)]
        faces += [
            (at(k, j), at(k + 1, j), at(k + 1, j + 1), at(k, j + 1))
            for k in range(1, rings - 1)
            for j in range(segments)
        ]
        faces += [
            (bottom, at(rings - 1, j + 1), at(rings - 1, j)) for j in range(segments)
        ]
        self.add([matrix @ v for v in verts], faces, slot)

    def mesh(self, name):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.verts, [], self.faces)
        mesh.polygons.foreach_set("material_index", self.slots)
        mesh.update()
        return mesh
