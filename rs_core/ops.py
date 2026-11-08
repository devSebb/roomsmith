"""Operations: pure functions scene -> scene.

``apply_operations(scene, ops)`` deep-copies the scene, applies every
operation in order, runs the hard validation once at the end, and returns the
new scene plus a per-operation receipt. Any ``SceneError`` aborts the whole
batch (atomicity is the caller's promise; this function simply raises).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from rs_core import geometry as g
from rs_core import model as m
from rs_core import placement
from rs_core.catalog import normalize_category, spec_for
from rs_core.model import SceneError

OPENING_DEFAULT_WIDTH_M = {"door": 0.9, "window": 1.2, "opening": 1.2}

# ---------------------------------------------------------------- receipts


@dataclass
class OpResult:
    op: str
    summary: str
    changed_ids: list[str] = field(default_factory=list)
    created_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"op": self.op, "summary": self.summary, "changed_ids": list(self.changed_ids)}
        if self.created_id:
            d["created_id"] = self.created_id
        if self.details:
            d["details"] = dict(self.details)
        return d


@dataclass
class BatchResult:
    scene: dict
    results: list[OpResult]

    @property
    def changed_ids(self) -> list[str]:
        seen: list[str] = []
        for r in self.results:
            for i in r.changed_ids:
                if i not in seen:
                    seen.append(i)
        return seen

    @property
    def summary(self) -> str:
        parts = [r.summary for r in self.results if r.summary]
        if not parts:
            return "No change"
        if len(parts) == 1:
            return parts[0]
        return "; ".join(parts[:3]) + (f" (+{len(parts) - 3} more)" if len(parts) > 3 else "")


# ---------------------------------------------------------------- helpers


def _num(v: Any, field_name: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SceneError("invalid_value", f"{field_name} must be a number", field=field_name)
    f = float(v)
    if not math.isfinite(f):
        raise SceneError("invalid_value", f"{field_name} must be finite", field=field_name)
    if lo is not None and f < lo:
        raise SceneError("out_of_range", f"{field_name} must be at least {lo}", field=field_name, value=f)
    if hi is not None and f > hi:
        raise SceneError("out_of_range", f"{field_name} must be at most {hi}", field=field_name, value=f)
    return f


def _dims(v: Any, field_name: str = "dimensions_m") -> list[float]:
    if isinstance(v, dict):
        try:
            v = [v["width_m"], v["height_m"], v["depth_m"]]
        except KeyError as e:
            raise SceneError("invalid_value", f"{field_name} needs width_m, height_m, depth_m", field=field_name) from e
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise SceneError("invalid_value", f"{field_name} must be [width, height, depth] in metres", field=field_name)
    return [_num(x, field_name, m.OBJECT_DIM_MIN, m.OBJECT_DIM_MAX) for x in v]


def _color(v: Any, field_name: str = "color") -> str:
    if not isinstance(v, str):
        raise SceneError("invalid_value", f"{field_name} must be a hex colour like #a1b2c3", field=field_name)
    s = v.strip()
    if not s.startswith("#"):
        s = "#" + s
    if len(s) not in (4, 7) or any(c not in "0123456789abcdefABCDEF" for c in s[1:]):
        raise SceneError("invalid_value", f"{field_name} must be a hex colour like #a1b2c3", field=field_name)
    if len(s) == 4:
        s = "#" + "".join(c * 2 for c in s[1:])
    return s.lower()


def _str(v: Any, field_name: str, choices: tuple[str, ...] | None = None) -> str:
    if not isinstance(v, str) or not v.strip():
        raise SceneError("invalid_value", f"{field_name} must be a non-empty string", field=field_name)
    s = v.strip()
    if choices is not None:
        s = s.lower()
        if s not in choices:
            raise SceneError("invalid_value", f"{field_name} must be one of {', '.join(choices)}", field=field_name)
    return s


def _require(op: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in op]
    if missing:
        raise SceneError("missing_field", f"{op.get('op')} needs {', '.join(missing)}", fields=missing)


def _unlocked(obj: dict, op: dict) -> None:
    if obj.get("locked") and not op.get("force"):
        raise SceneError(
            "locked",
            f"{obj['name']} ({obj['id']}) is locked; unlock it first (update_object locked=false) or pass force=true",
            id=obj["id"],
        )


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _dims_str(d: list[float]) -> str:
    return f"{_fmt(d[0])} x {_fmt(d[1])} x {_fmt(d[2])} m"


# ---------------------------------------------------------------- room


def op_set_room_rectangle(scene: dict, op: dict) -> OpResult:
    _require(op, "width_m", "depth_m")
    w = _num(op["width_m"], "width_m", m.ROOM_SIDE_MIN, m.ROOM_SIDE_MAX)
    d = _num(op["depth_m"], "depth_m", m.ROOM_SIDE_MIN, m.ROOM_SIDE_MAX)
    room = scene["room"]
    if len(room["vertices"]) != 4:
        # replacing a polygon room with a rectangle: drop openings that no longer
        # have a wall, keep objects where they are
        room["openings"] = []
        room["vertices"] = []
        room["walls"] = []
    m.set_rectangle(scene, w, d)
    _clamp_openings_to_walls(scene)
    if "height_m" in op:
        room["height_m"] = _num(op["height_m"], "height_m", m.ROOM_HEIGHT_MIN, m.ROOM_HEIGHT_MAX)
    ids = [v["id"] for v in room["vertices"]] + [wl["id"] for wl in room["walls"]]
    return OpResult("set_room_rectangle", f"Set room to {_fmt(w)} x {_fmt(d)} m", ids)


def op_set_room_height(scene: dict, op: dict) -> OpResult:
    _require(op, "height_m")
    h = _num(op["height_m"], "height_m", m.ROOM_HEIGHT_MIN, m.ROOM_HEIGHT_MAX)
    scene["room"]["height_m"] = h
    return OpResult("set_room_height", f"Set ceiling height to {_fmt(h)} m", ["room"])


def op_set_wall_length(scene: dict, op: dict) -> OpResult:
    _require(op, "id", "length_m")
    wall = m.find_wall(scene, str(op["id"]))
    L = _num(op["length_m"], "length_m", m.ROOM_SIDE_MIN, m.ROOM_SIDE_MAX)
    if not m.is_rectangle(scene):
        raise SceneError("not_rectangle", "set_wall_length only works on rectangular rooms; use move_vertex", id=wall["id"])
    i = m.wall_index(scene, wall["id"])
    verts = scene["room"]["vertices"]
    n = len(verts)
    a, b = m.wall_segment(scene, wall)
    dirv = g.normalize(g.sub(b, a))
    delta = g.scale(dirv, L - g.distance(a, b))
    for j in ((i + 1) % n, (i + 2) % n):
        verts[j]["x"] = float(verts[j]["x"]) + delta[0]
        verts[j]["z"] = float(verts[j]["z"]) + delta[1]
    _clamp_openings_to_walls(scene)
    return OpResult("set_wall_length", f"Set wall {wall['id']} ({wall.get('label') or 'wall'}) to {_fmt(L)} m", [wall["id"]])


def op_move_vertex(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    v = m.find_vertex(scene, str(op["id"]))
    if "x" in op:
        v["x"] = _num(op["x"], "x", -m.ROOM_SIDE_MAX, m.ROOM_SIDE_MAX)
    if "z" in op:
        v["z"] = _num(op["z"], "z", -m.ROOM_SIDE_MAX, m.ROOM_SIDE_MAX)
    if "by" in op:
        d = op["by"]
        if not isinstance(d, (list, tuple)) or len(d) != 2:
            raise SceneError("invalid_value", "by needs [dx, dz]", field="by")
        v["x"] = float(v["x"]) + _num(d[0], "by")
        v["z"] = float(v["z"]) + _num(d[1], "by")
    _canonicalize_outline(scene)
    _clamp_openings_to_walls(scene)
    return OpResult("move_vertex", f"Moved corner {v['id']} to ({_fmt(v['x'])}, {_fmt(v['z'])})", [v["id"]])


def op_set_surface_color(scene: dict, op: dict) -> OpResult:
    _require(op, "surface", "color")
    color = _color(op["color"])
    surface = _str(op["surface"], "surface")
    key = surface.lower()
    room = scene["room"]
    if key == "floor":
        room["floor"]["color"] = color
        return OpResult("set_surface_color", f"Floor colour set to {color}", ["floor"])
    if key == "ceiling":
        room["ceiling"]["color"] = color
        return OpResult("set_surface_color", f"Ceiling colour set to {color}", ["ceiling"])
    if key in ("walls", "all_walls"):
        for w in room["walls"]:
            w["color"] = color
        return OpResult("set_surface_color", f"All walls set to {color}", [w["id"] for w in room["walls"]])
    wall = m.find_wall(scene, surface)
    wall["color"] = color
    return OpResult("set_surface_color", f"Wall {wall['id']} set to {color}", [wall["id"]])


# ---------------------------------------------------------------- openings


def op_add_opening(scene: dict, op: dict) -> OpResult:
    if "wall_id" not in op and "wall" in op:
        op = {**op, "wall_id": op["wall"]}  # `wall` accepts an id or a label such as "front"
    _require(op, "wall_id", "kind")
    wall = m.find_wall(scene, str(op["wall_id"]))
    kind = _str(op["kind"], "kind", m.OPENING_KINDS)
    # Typical widths when the model does not state one (door leaf, standard window).
    width = _num(op.get("width_m", OPENING_DEFAULT_WIDTH_M[kind]), "width_m", 0.3, 10.0)
    L = m.wall_length(scene, wall)
    if "offset_m" in op:
        offset = _num(op["offset_m"], "offset_m", 0.0, m.ROOM_SIDE_MAX)  # explicit: validated, never clamped
    elif "position_fraction" in op:
        f = _num(op["position_fraction"], "position_fraction", 0.0, 1.0)
        offset = f * L - width / 2.0
        offset = max(0.0, min(L - width, offset)) if L >= width else 0.0
    else:
        offset = max(0.0, (L - width) / 2.0)
    opening = m.make_opening(
        scene,
        wall["id"],
        kind,
        offset,
        width,
        _num(op["height_m"], "height_m", 0.2, m.ROOM_HEIGHT_MAX) if "height_m" in op else None,
        _num(op["sill_m"], "sill_m", 0.0, m.ROOM_HEIGHT_MAX) if "sill_m" in op else None,
        _str(op["swing"], "swing", m.SWINGS) if "swing" in op else None,
        _str(op["hinge"], "hinge", m.HINGES) if "hinge" in op else None,
        _str(op["dims_source"], "dims_source", m.DIMS_SOURCES) if "dims_source" in op else "stated",
    )
    scene["room"]["openings"].append(opening)
    return OpResult(
        "add_opening",
        f"Added {kind} {opening['id']} on wall {wall['id']} ({wall.get('label') or 'wall'}), {_fmt(width)} m wide",
        [opening["id"], wall["id"]],
        created_id=opening["id"],
    )


def op_update_opening(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    o = m.find_opening(scene, str(op["id"]))
    changed = []
    if "wall_id" in op:
        o["wall_id"] = m.find_wall(scene, str(op["wall_id"]))["id"]
        changed.append("wall")
    if "kind" in op:
        o["kind"] = _str(op["kind"], "kind", m.OPENING_KINDS)
        changed.append("kind")
    if "offset_m" in op:
        o["offset_m"] = _num(op["offset_m"], "offset_m", 0.0, m.ROOM_SIDE_MAX)
        changed.append("position")
    if "position_fraction" in op:
        L = m.wall_length(scene, o["wall_id"])
        f = _num(op["position_fraction"], "position_fraction", 0.0, 1.0)
        o["offset_m"] = max(0.0, f * L - float(o["width_m"]) / 2.0)
        changed.append("position")
    if "width_m" in op:
        o["width_m"] = _num(op["width_m"], "width_m", 0.3, 10.0)
        changed.append("width")
    if "height_m" in op:
        o["height_m"] = _num(op["height_m"], "height_m", 0.2, m.ROOM_HEIGHT_MAX)
        changed.append("height")
    if "sill_m" in op:
        o["sill_m"] = _num(op["sill_m"], "sill_m", 0.0, m.ROOM_HEIGHT_MAX)
        changed.append("sill")
    if "swing" in op:
        o["swing"] = _str(op["swing"], "swing", m.SWINGS)
        changed.append("swing")
    if "hinge" in op:
        o["hinge"] = _str(op["hinge"], "hinge", m.HINGES)
        changed.append("hinge")
    if "dims_source" in op:
        o["dims_source"] = _str(op["dims_source"], "dims_source", m.DIMS_SOURCES)
    what = ", ".join(changed) if changed else "nothing"
    return OpResult("update_opening", f"Updated {o['kind']} {o['id']}: {what}", [o["id"]])


def op_remove_opening(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    o = m.find_opening(scene, str(op["id"]))
    scene["room"]["openings"] = [x for x in scene["room"]["openings"] if x["id"] != o["id"]]
    return OpResult("remove_opening", f"Removed {o['kind']} {o['id']}", [o["id"]])


# ---------------------------------------------------------------- objects


def op_add_object(scene: dict, op: dict) -> OpResult:
    name = _str(op.get("name") or op.get("category") or "", "name")
    category = normalize_category(op.get("category") or name)
    dims = _dims(op["dimensions_m"]) if "dimensions_m" in op else None
    provenance = op.get("provenance") if isinstance(op.get("provenance"), dict) else None
    if dims is None:
        provenance = dict(provenance or {})
        provenance.setdefault("class", "generated_approximation")
        provenance.setdefault("dims_source", "estimated")
        provenance.setdefault("confidence", 0.5)
    obj = m.make_object(
        scene,
        name,
        category,
        tuple(dims) if dims else None,
        color=_color(op["color"]) if op.get("color") else None,
        shape=_str(op["shape"], "shape", m.SHAPES) if "shape" in op else None,
        mount=_str(op["mount"], "mount", m.MOUNTS) if "mount" in op else None,
        provenance=provenance,
        product=op.get("product") if isinstance(op.get("product"), dict) else None,
        locked=bool(op.get("locked", False)),
    )
    if "yaw_rad" in op:
        obj["yaw_rad"] = g.normalize_yaw(_num(op["yaw_rad"], "yaw_rad"))
    place = dict(op["place"]) if isinstance(op.get("place"), dict) else {}
    if "position_m" in op:
        place["position_m"] = op["position_m"]
        place.setdefault("yaw_rad", obj["yaw_rad"])
    if place:
        obj["position_m"], obj["yaw_rad"], desc = placement.resolve(scene, obj, place)
    else:
        obj["position_m"], obj["yaw_rad"], desc = _auto_place(scene, obj)
    scene["objects"].append(obj)
    return OpResult(
        "add_object",
        f"Added {obj['name']} ({obj['id']}), {_dims_str(obj['dimensions_m'])}, {desc}",
        [obj["id"]],
        created_id=obj["id"],
        details={"position_m": list(obj["position_m"]), "yaw_rad": obj["yaw_rad"]},
    )


def _auto_place(scene: dict, obj: dict) -> tuple[list[float], float, str]:
    """Default spot for a new object: along the first wall with room, else centre."""
    spec = spec_for(obj["category"])
    w = float(obj["dimensions_m"][0])
    if spec.against_wall_typical or True:
        for wall in scene["room"]["walls"]:
            if m.wall_length(scene, wall) < w + 0.1:
                continue
            try:
                pos, yaw, _ = placement.resolve(scene, obj, {"against_wall": wall["id"], "align": "left", "offset_m": 0.1})
            except SceneError:
                continue
            trial = dict(obj, position_m=pos, yaw_rad=yaw)
            fp = m.footprint(trial)
            if any(g.convex_overlap_depth(fp, m.footprint(o)) > 0.01 for o in scene["objects"] if o.get("mount", "floor") == "floor"):
                # slide along the wall in 20 cm steps until free
                L = m.wall_length(scene, wall)
                t = 0.1
                placed = False
                while t + w <= L - 0.1:
                    pos, yaw, _ = placement.resolve(scene, obj, {"against_wall": wall["id"], "align": "left", "offset_m": t})
                    trial = dict(obj, position_m=pos, yaw_rad=yaw)
                    fp = m.footprint(trial)
                    if not any(g.convex_overlap_depth(fp, m.footprint(o)) > 0.01 for o in scene["objects"] if o.get("mount", "floor") == "floor"):
                        placed = True
                        break
                    t += 0.2
                if not placed:
                    continue
            return pos, yaw, f"against wall {wall['id']} (auto)"
    x, z = g.centroid(m.outline(scene))
    return [x, 0.0, z], 0.0, "centred (auto)"


def op_update_object(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    obj = m.find_object(scene, str(op["id"]))
    changed = []
    if "locked" in op:
        obj["locked"] = bool(op["locked"])
        changed.append("locked" if obj["locked"] else "unlocked")
    fields = {k: v for k, v in op.items() if k not in ("op", "id", "locked", "force")}
    if fields:
        _unlocked(obj, op)
    if "name" in fields:
        obj["name"] = _str(fields["name"], "name")
        changed.append("name")
    if "category" in fields:
        obj["category"] = normalize_category(fields["category"])
        changed.append("category")
    if "color" in fields:
        obj["color"] = _color(fields["color"])
        changed.append("colour")
    if "shape" in fields:
        obj["shape"] = _str(fields["shape"], "shape", m.SHAPES)
        changed.append("shape")
    if "mount" in fields:
        obj["mount"] = _str(fields["mount"], "mount", m.MOUNTS)
        changed.append("mount")
    if "product" in fields:
        obj["product"] = fields["product"] if isinstance(fields["product"], dict) else None
        changed.append("product")
    if "provenance" in fields and isinstance(fields["provenance"], dict):
        obj["provenance"] = {**obj.get("provenance", {}), **fields["provenance"]}
        changed.append("provenance")
    if "dimensions_m" in fields:
        obj["dimensions_m"] = _dims(fields["dimensions_m"])
        obj.setdefault("provenance", {})["dims_source"] = str(fields.get("dims_source", "stated"))
        changed.append("size")
    what = ", ".join(changed) if changed else "nothing"
    return OpResult("update_object", f"Updated {obj['name']} ({obj['id']}): {what}", [obj["id"]])


def op_set_dimensions(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    obj = m.find_object(scene, str(op["id"]))
    _unlocked(obj, op)
    if "dimensions_m" in op:
        dims = _dims(op["dimensions_m"])
    else:
        dims = list(obj["dimensions_m"])
        for i, key in enumerate(("width_m", "height_m", "depth_m")):
            if key in op:
                dims[i] = _num(op[key], key, m.OBJECT_DIM_MIN, m.OBJECT_DIM_MAX)
        if dims == list(obj["dimensions_m"]):
            raise SceneError("missing_field", "set_dimensions needs dimensions_m or width_m/height_m/depth_m")
    obj["dimensions_m"] = dims
    obj.setdefault("provenance", {})["dims_source"] = _str(op.get("dims_source", "stated"), "dims_source", m.DIMS_SOURCES)
    return OpResult("set_dimensions", f"Resized {obj['name']} ({obj['id']}) to {_dims_str(dims)}", [obj["id"]])


def op_move_object(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    obj = m.find_object(scene, str(op["id"]))
    _unlocked(obj, op)
    place = dict(op.get("place") or {})
    for k in ("position_m", "yaw_rad", "yaw_deg", "facing", "by", "against_wall", "next_to", "in_corner", "centered_in_room", "on", "align", "offset_m", "gap_m", "side"):
        if k in op and k not in place:
            place[k] = op[k]
    if not place:
        raise SceneError("missing_field", "move_object needs a place instruction or position_m")
    pos, yaw, desc = placement.resolve(scene, obj, place)
    obj["position_m"] = pos
    obj["yaw_rad"] = yaw
    return OpResult(
        "move_object",
        f"Moved {obj['name']} ({obj['id']}) {desc}",
        [obj["id"]],
        details={"position_m": list(pos), "yaw_rad": yaw},
    )


def op_rotate_object(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    obj = m.find_object(scene, str(op["id"]))
    _unlocked(obj, op)
    if "yaw_rad" in op:
        yaw = _num(op["yaw_rad"], "yaw_rad")
    elif "yaw_deg" in op:
        yaw = math.radians(_num(op["yaw_deg"], "yaw_deg"))
    elif "by_deg" in op:
        yaw = float(obj.get("yaw_rad", 0.0)) + math.radians(_num(op["by_deg"], "by_deg"))
    elif "by_rad" in op:
        yaw = float(obj.get("yaw_rad", 0.0)) + _num(op["by_rad"], "by_rad")
    elif "facing" in op:
        yaw = placement.facing_yaw(scene, str(op["facing"]))
    else:
        raise SceneError("missing_field", "rotate_object needs yaw_rad, yaw_deg, by_deg, by_rad or facing")
    obj["yaw_rad"] = g.normalize_yaw(yaw)
    return OpResult("rotate_object", f"Rotated {obj['name']} ({obj['id']}) to {math.degrees(obj['yaw_rad']):.0f}°", [obj["id"]])


def op_duplicate_object(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    src = m.find_object(scene, str(op["id"]))
    dup = m.clone(src)
    dup["id"] = m.alloc_id(scene, "ob")
    dup["locked"] = False
    if op.get("name"):
        dup["name"] = _str(op["name"], "name")
    if isinstance(op.get("place"), dict):
        dup["position_m"], dup["yaw_rad"], desc = placement.resolve(scene, dup, op["place"])
    else:
        dup["position_m"], dup["yaw_rad"], desc = placement.resolve(scene, dup, {"next_to": src["id"], "side": "right", "gap_m": 0.1})
    scene["objects"].append(dup)
    return OpResult("duplicate_object", f"Duplicated {src['name']} as {dup['id']}, {desc}", [dup["id"]], created_id=dup["id"])


def op_remove_object(scene: dict, op: dict) -> OpResult:
    _require(op, "id")
    obj = m.find_object(scene, str(op["id"]))
    _unlocked(obj, op)
    scene["objects"] = [o for o in scene["objects"] if o["id"] != obj["id"]]
    return OpResult("remove_object", f"Removed {obj['name']} ({obj['id']})", [obj["id"]])


def op_swap_objects(scene: dict, op: dict) -> OpResult:
    _require(op, "a", "b")
    a = m.find_object(scene, str(op["a"]))
    b = m.find_object(scene, str(op["b"]))
    _unlocked(a, op)
    _unlocked(b, op)
    a["position_m"], b["position_m"] = list(b["position_m"]), list(a["position_m"])
    a["yaw_rad"], b["yaw_rad"] = b.get("yaw_rad", 0.0), a.get("yaw_rad", 0.0)
    return OpResult("swap_objects", f"Swapped {a['name']} ({a['id']}) and {b['name']} ({b['id']})", [a["id"], b["id"]])


# ---------------------------------------------------------------- scale


def op_calibrate(scene: dict, op: dict) -> OpResult:
    """Rescale the whole scene so that one known length becomes real.

    reference: {"kind": "wall_length"|"room_height"|"opening_width"|"object_width"|
                "object_height"|"object_depth", "id": "...", "real_m": 4.2}
    Objects whose dimensions are stated or measured keep their size; only their
    positions scale. Everything estimated scales.
    """
    ref = op.get("reference") if isinstance(op.get("reference"), dict) else op
    kind = _str(ref.get("kind", ""), "kind", ("wall_length", "room_height", "opening_width", "object_width", "object_height", "object_depth"))
    real = _num(ref.get("real_m"), "real_m", 0.05, 60.0)
    current = _reference_value(scene, kind, ref.get("id"))
    if current <= 1e-6:
        raise SceneError("invalid_value", "Reference length is zero; cannot calibrate")
    k = real / current
    _scale_scene(scene, k)
    scene["calibration"] = {
        "status": "calibrated",
        "reference": {"kind": kind, "id": ref.get("id"), "real_m": real},
        "scale_applied": k,
    }
    ids = [v["id"] for v in scene["room"]["vertices"]] + [o["id"] for o in scene["objects"]] + [o["id"] for o in scene["room"]["openings"]]
    return OpResult(
        "calibrate",
        f"Calibrated: {kind.replace('_', ' ')} {ref.get('id') or ''} = {_fmt(real)} m (scene scaled x{k:.3f})".replace("  ", " "),
        ids,
        details={"scale": k},
    )


def _reference_value(scene: dict, kind: str, ident: str | None) -> float:
    if kind == "room_height":
        return float(scene["room"]["height_m"])
    if ident is None:
        raise SceneError("missing_field", f"{kind} needs an id")
    if kind == "wall_length":
        return m.wall_length(scene, m.find_wall(scene, str(ident)))
    if kind == "opening_width":
        return float(m.find_opening(scene, str(ident))["width_m"])
    obj = m.find_object(scene, str(ident))
    idx = {"object_width": 0, "object_height": 1, "object_depth": 2}[kind]
    return float(obj["dimensions_m"][idx])


def _scale_scene(scene: dict, k: float) -> None:
    room = scene["room"]
    for v in room["vertices"]:
        v["x"] = float(v["x"]) * k
        v["z"] = float(v["z"]) * k
    room["height_m"] = float(room["height_m"]) * k
    for o in room["openings"]:
        for key in ("offset_m", "width_m", "height_m", "sill_m"):
            o[key] = float(o[key]) * k
    for obj in scene["objects"]:
        obj["position_m"] = [float(v) * k for v in obj["position_m"]]
        src = (obj.get("provenance") or {}).get("dims_source", "estimated")
        if src == "estimated":
            obj["dimensions_m"] = [float(v) * k for v in obj["dimensions_m"]]
    cal = scene.get("calibration") or {}
    if cal.get("reference") and cal.get("status") == "calibrated":
        pass


# ---------------------------------------------------------------- outline upkeep


def _canonicalize_outline(scene: dict) -> None:
    """Keep the outline's shoelace sum positive so inward normals stay inward."""
    pts = m.outline(scene)
    if len(pts) >= 3 and g.shoelace(pts) < 0:
        room = scene["room"]
        room["vertices"].reverse()
        # walls join vertex i to i+1; rebuild endpoints keeping ids and attributes
        n = len(room["vertices"])
        old_walls = room["walls"]
        by_pair = {(w["a"], w["b"]): w for w in old_walls}
        new_walls = []
        for i in range(n):
            a, b = room["vertices"][i]["id"], room["vertices"][(i + 1) % n]["id"]
            w = by_pair.get((a, b)) or by_pair.get((b, a))
            if w is None:
                w = {"id": m.alloc_id(scene, "w"), "color": m.DEFAULT_WALL_COLOR, "label": ""}
            w = dict(w, a=a, b=b)
            new_walls.append(w)
        room["walls"] = new_walls


def _clamp_openings_to_walls(scene: dict) -> None:
    """After a wall changes length, keep openings on it and inside it."""
    walls = m.wall_map(scene)
    kept = []
    for o in scene["room"]["openings"]:
        w = walls.get(o["wall_id"])
        if w is None:
            continue
        L = m.wall_length(scene, w)
        width = float(o["width_m"])
        if width > L:
            o["width_m"] = max(0.3, L)
            width = o["width_m"]
        o["offset_m"] = max(0.0, min(L - width, float(o["offset_m"])))
        kept.append(o)
    scene["room"]["openings"] = kept


# ---------------------------------------------------------------- dispatcher

OPS: dict[str, Callable[[dict, dict], OpResult]] = {
    "set_room_rectangle": op_set_room_rectangle,
    "set_room_height": op_set_room_height,
    "set_wall_length": op_set_wall_length,
    "move_vertex": op_move_vertex,
    "set_surface_color": op_set_surface_color,
    "add_opening": op_add_opening,
    "update_opening": op_update_opening,
    "remove_opening": op_remove_opening,
    "add_object": op_add_object,
    "update_object": op_update_object,
    "set_dimensions": op_set_dimensions,
    "move_object": op_move_object,
    "rotate_object": op_rotate_object,
    "duplicate_object": op_duplicate_object,
    "remove_object": op_remove_object,
    "swap_objects": op_swap_objects,
    "calibrate": op_calibrate,
}

# Friendly aliases the model may produce
ALIASES = {
    "add": "add_object",
    "move": "move_object",
    "rotate": "rotate_object",
    "resize": "set_dimensions",
    "resize_object": "set_dimensions",
    "remove": "remove_object",
    "delete": "remove_object",
    "delete_object": "remove_object",
    "duplicate": "duplicate_object",
    "update": "update_object",
    "rename": "update_object",
    "lock": "update_object",
    "unlock": "update_object",
    "swap": "swap_objects",
    "set_room_size": "set_room_rectangle",
    "set_room": "set_room_rectangle",
    "set_height": "set_room_height",
    "add_door": "add_opening",
    "add_window": "add_opening",
    "set_color": "set_surface_color",
    "set_colour": "set_surface_color",
    "set_surface_colour": "set_surface_color",
    "scale": "calibrate",
}


def apply_operations(scene: dict, operations: list[dict]) -> BatchResult:
    """Apply a batch to a copy of `scene`. Raises SceneError on any failure."""
    from rs_core.validate import validate_hard  # local import: validate imports model, not ops

    if not isinstance(operations, list) or not operations:
        raise SceneError("invalid_value", "operations must be a non-empty list")
    work = m.clone(scene)
    results: list[OpResult] = []
    for i, op in enumerate(operations):
        if not isinstance(op, dict) or "op" not in op:
            raise SceneError("invalid_value", f"operation {i} must be an object with an 'op' field", index=i)
        name = str(op["op"]).strip().lower()
        if name in ALIASES:
            op = dict(op)
            if name == "lock":
                op["locked"] = True
            elif name == "unlock":
                op["locked"] = False
            elif name == "add_door":
                op.setdefault("kind", "door")
            elif name == "add_window":
                op.setdefault("kind", "window")
            name = ALIASES[name]
            op["op"] = name
        fn = OPS.get(name)
        if fn is None:
            raise SceneError("unknown_op", f"Unknown operation {name!r}", index=i, known=sorted(OPS))
        try:
            results.append(fn(work, op))
        except SceneError as e:
            e.extra.setdefault("index", i)
            e.extra.setdefault("op", name)
            raise
    validate_hard(work)
    return BatchResult(work, results)
