"""Write a scene as a binary glTF (.glb) using only the standard library.

Geometry: floor slab, walls as thin boxes split around openings (so doors and
windows are real gaps), objects as boxes or 24-sided prisms. One node per
object, named, so the file is readable in Blender, Quick Look and three.js.
Colours are flat PBR base colours.
"""

from __future__ import annotations

import json
import math
import struct
from typing import Iterable

from rs_core import geometry as g
from rs_core import model as m

WALL_THICKNESS = 0.1
FLOOR_THICKNESS = 0.05


class _Builder:
    def __init__(self) -> None:
        self.bin = bytearray()
        self.buffer_views: list[dict] = []
        self.accessors: list[dict] = []
        self.meshes: list[dict] = []
        self.nodes: list[dict] = []
        self.materials: list[dict] = []
        self._material_index: dict[str, int] = {}

    def material(self, color: str) -> int:
        key = color.lower()
        if key in self._material_index:
            return self._material_index[key]
        r, gg, b = _hex_to_rgb(key)
        self.materials.append(
            {
                "name": key,
                "pbrMetallicRoughness": {"baseColorFactor": [r, gg, b, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.85},
                "doubleSided": True,
            }
        )
        self._material_index[key] = len(self.materials) - 1
        return self._material_index[key]

    def _view(self, data: bytes, target: int | None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        offset = len(self.bin)
        self.bin.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    def add_mesh(self, name: str, positions: list[tuple[float, float, float]], normals: list[tuple[float, float, float]], indices: list[int], material: int) -> int:
        pos_bytes = b"".join(struct.pack("<fff", *p) for p in positions)
        nrm_bytes = b"".join(struct.pack("<fff", *n) for n in normals)
        idx_bytes = b"".join(struct.pack("<I", i) for i in indices)
        pv = self._view(pos_bytes, 34962)
        nv = self._view(nrm_bytes, 34962)
        iv = self._view(idx_bytes, 34963)
        xs, ys, zs = zip(*positions)
        self.accessors.append({"bufferView": pv, "componentType": 5126, "count": len(positions), "type": "VEC3", "min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]})
        pa = len(self.accessors) - 1
        self.accessors.append({"bufferView": nv, "componentType": 5126, "count": len(normals), "type": "VEC3"})
        na = len(self.accessors) - 1
        self.accessors.append({"bufferView": iv, "componentType": 5125, "count": len(indices), "type": "SCALAR"})
        ia = len(self.accessors) - 1
        self.meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": pa, "NORMAL": na}, "indices": ia, "material": material}]})
        return len(self.meshes) - 1

    def add_node(self, name: str, mesh: int, translation: tuple[float, float, float] = (0, 0, 0), yaw: float = 0.0, extras: dict | None = None) -> int:
        node: dict = {"name": name, "mesh": mesh}
        if any(abs(t) > 1e-9 for t in translation):
            node["translation"] = list(translation)
        if abs(yaw) > 1e-9:
            node["rotation"] = [0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)]
        if extras:
            node["extras"] = extras
        self.nodes.append(node)
        return len(self.nodes) - 1

    def finish(self, scene_name: str) -> bytes:
        while len(self.bin) % 4:
            self.bin.append(0)
        gltf = {
            "asset": {"version": "2.0", "generator": "Roomsmith for Hermes Agent"},
            "scene": 0,
            "scenes": [{"name": scene_name, "nodes": list(range(len(self.nodes)))}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.bin)}],
        }
        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        while len(json_bytes) % 4:
            json_bytes += b" "
        total = 12 + 8 + len(json_bytes) + 8 + len(self.bin)
        out = bytearray()
        out += struct.pack("<III", 0x46546C67, 2, total)
        out += struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
        out += struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin)
        return bytes(out)


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        r, gg, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        r, gg, b = 154, 160, 166
    # sRGB -> linear for glTF base colour
    return tuple(((v / 255.0) / 12.92) if v / 255.0 <= 0.04045 else (((v / 255.0) + 0.055) / 1.055) ** 2.4 for v in (r, gg, b))  # type: ignore[return-value]


def box_geometry(w: float, h: float, d: float, origin_at_base: bool = True) -> tuple[list, list, list]:
    """Axis-aligned box centred on x/z, base at y=0 (or centred)."""
    hw, hd = w / 2, d / 2
    y0, y1 = (0.0, h) if origin_at_base else (-h / 2, h / 2)
    faces = [
        # (normal, 4 corners)
        ((0, 0, 1), [(-hw, y0, hd), (hw, y0, hd), (hw, y1, hd), (-hw, y1, hd)]),
        ((0, 0, -1), [(hw, y0, -hd), (-hw, y0, -hd), (-hw, y1, -hd), (hw, y1, -hd)]),
        ((1, 0, 0), [(hw, y0, hd), (hw, y0, -hd), (hw, y1, -hd), (hw, y1, hd)]),
        ((-1, 0, 0), [(-hw, y0, -hd), (-hw, y0, hd), (-hw, y1, hd), (-hw, y1, -hd)]),
        ((0, 1, 0), [(-hw, y1, hd), (hw, y1, hd), (hw, y1, -hd), (-hw, y1, -hd)]),
        ((0, -1, 0), [(-hw, y0, -hd), (hw, y0, -hd), (hw, y0, hd), (-hw, y0, hd)]),
    ]
    positions, normals, indices = [], [], []
    for normal, corners in faces:
        base = len(positions)
        positions.extend(corners)
        normals.extend([normal] * 4)
        indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return positions, normals, indices


def cylinder_geometry(radius: float, h: float, segments: int = 24) -> tuple[list, list, list]:
    positions, normals, indices = [], [], []
    ring_b, ring_t = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        x, z = radius * math.cos(a), radius * math.sin(a)
        n = (math.cos(a), 0.0, math.sin(a))
        ring_b.append(len(positions))
        positions.append((x, 0.0, z))
        normals.append(n)
        ring_t.append(len(positions))
        positions.append((x, h, z))
        normals.append(n)
    for i in range(segments):
        j = (i + 1) % segments
        indices += [ring_b[i], ring_t[i], ring_t[j], ring_b[i], ring_t[j], ring_b[j]]
    # caps
    ct = len(positions)
    positions.append((0.0, h, 0.0))
    normals.append((0, 1, 0))
    cb = len(positions)
    positions.append((0.0, 0.0, 0.0))
    normals.append((0, -1, 0))
    top_ring, bot_ring = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        x, z = radius * math.cos(a), radius * math.sin(a)
        top_ring.append(len(positions))
        positions.append((x, h, z))
        normals.append((0, 1, 0))
        bot_ring.append(len(positions))
        positions.append((x, 0.0, z))
        normals.append((0, -1, 0))
    for i in range(segments):
        j = (i + 1) % segments
        indices += [ct, top_ring[j], top_ring[i]]
        indices += [cb, bot_ring[i], bot_ring[j]]
    return positions, normals, indices


def _wall_pieces(scene: dict, wall: dict) -> Iterable[tuple[float, float, float, float]]:
    """(start_t, end_t, y0, y1) rectangles of solid wall along the wall's length."""
    L = m.wall_length(scene, wall)
    H = float(scene["room"]["height_m"])
    openings = sorted((o for o in scene["room"]["openings"] if o["wall_id"] == wall["id"]), key=lambda o: float(o["offset_m"]))
    t = 0.0
    for o in openings:
        s, e = float(o["offset_m"]), float(o["offset_m"]) + float(o["width_m"])
        sill, top = float(o["sill_m"]), float(o["sill_m"]) + float(o["height_m"])
        if s > t:
            yield (t, s, 0.0, H)
        if sill > 0:
            yield (s, e, 0.0, sill)
        if top < H:
            yield (s, e, top, H)
        t = max(t, e)
    if t < L:
        yield (t, L, 0.0, H)


def scene_to_glb(scene: dict) -> bytes:
    b = _Builder()
    poly = m.outline(scene)
    x0, z0, x1, z1 = g.bounds(poly)
    # floor: a slab under the bounding box for polygons, exact for rectangles
    floor_mat = b.material(scene["room"]["floor"]["color"])
    if m.is_rectangle(scene):
        pos, nrm, idx = box_geometry(x1 - x0, FLOOR_THICKNESS, z1 - z0, origin_at_base=False)
        mesh = b.add_mesh("Floor", pos, nrm, idx, floor_mat)
        b.add_node("Floor", mesh, ((x0 + x1) / 2, -FLOOR_THICKNESS / 2, (z0 + z1) / 2))
    else:
        pos, nrm, idx = _polygon_slab(poly, FLOOR_THICKNESS)
        mesh = b.add_mesh("Floor", pos, nrm, idx, floor_mat)
        b.add_node("Floor", mesh, (0.0, -FLOOR_THICKNESS, 0.0))

    for wall in scene["room"]["walls"]:
        a, bb = m.wall_segment(scene, wall)
        n = g.inward_normal(a, bb)
        d = g.normalize(g.sub(bb, a))
        yaw = -math.atan2(d[1], d[0])  # rotates the box's local +x onto the wall direction d
        mat = b.material(wall.get("color", m.DEFAULT_WALL_COLOR))
        for k, (s, e, y0, y1) in enumerate(_wall_pieces(scene, wall)):
            length = e - s
            if length <= 1e-6 or y1 - y0 <= 1e-6:
                continue
            pos, nrm, idx = box_geometry(length, y1 - y0, WALL_THICKNESS, origin_at_base=True)
            mesh = b.add_mesh(f"{wall['id']}_{k}", pos, nrm, idx, mat)
            centre_along = g.add(a, g.scale(d, s + length / 2))
            centre = g.add(centre_along, g.scale(n, -WALL_THICKNESS / 2))
            b.add_node(f"Wall {wall['id']} {wall.get('label', '')}".strip(), mesh, (centre[0], y0, centre[1]), yaw, {"wall_id": wall["id"]})

    for obj in scene["objects"]:
        w, h, dd = (float(v) for v in obj["dimensions_m"])
        x, y, z = (float(v) for v in obj["position_m"])
        mat = b.material(obj.get("color", "#9aa0a6"))
        if obj.get("shape") == "cylinder":
            pos, nrm, idx = cylinder_geometry(min(w, dd) / 2, h)
        else:
            pos, nrm, idx = box_geometry(w, h, dd)
        mesh = b.add_mesh(obj["id"], pos, nrm, idx, mat)
        extras = {"id": obj["id"], "category": obj.get("category"), "dimensions_m": obj["dimensions_m"]}
        if obj.get("product"):
            extras["product"] = {k: v for k, v in obj["product"].items() if k in ("title", "url", "price")}
        b.add_node(obj["name"], mesh, (x, y, z), float(obj.get("yaw_rad", 0.0)), extras)
    return b.finish(scene["project"]["name"])


def _polygon_slab(poly: list[g.Point], thickness: float) -> tuple[list, list, list]:
    """Triangulated slab for a simple polygon (ear clipping, top face only plus sides)."""
    pts = list(poly)
    if g.shoelace(pts) < 0:
        pts.reverse()
    tris = _ear_clip(pts)
    positions, normals, indices = [], [], []
    for tri in tris:
        base = len(positions)
        for i in tri:
            positions.append((pts[i][0], thickness, pts[i][1]))
            normals.append((0.0, 1.0, 0.0))
        # top face winding: viewed from +Y, shoelace-positive in (x,z) is clockwise
        # in a right-handed view from above, so flip to face up
        indices += [base, base + 2, base + 1]
    n = len(pts)
    for i in range(n):
        a, bb = pts[i], pts[(i + 1) % n]
        nx, nz = g.inward_normal(a, bb)
        normal = (-nx, 0.0, -nz)
        base = len(positions)
        positions += [(a[0], 0.0, a[1]), (bb[0], 0.0, bb[1]), (bb[0], thickness, bb[1]), (a[0], thickness, a[1])]
        normals += [normal] * 4
        indices += [base, base + 1, base + 2, base, base + 2, base + 3]
    return positions, normals, indices


def _ear_clip(pts: list[g.Point]) -> list[tuple[int, int, int]]:
    idx = list(range(len(pts)))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 1000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, bb, c = pts[i0], pts[i1], pts[i2]
            if g.cross(g.sub(bb, a), g.sub(c, bb)) <= 0:
                continue
            if any(_point_in_tri(pts[j], a, bb, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _point_in_tri(p: g.Point, a: g.Point, b: g.Point, c: g.Point) -> bool:
    d1 = g.cross(g.sub(b, a), g.sub(p, a))
    d2 = g.cross(g.sub(c, b), g.sub(p, b))
    d3 = g.cross(g.sub(a, c), g.sub(p, c))
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)
