"""Turn a model-produced *draft* (fractions and estimates) into a scene.

The draft format is what a vision model estimates well:

{
  "room": {"width_m": 4.2, "depth_m": 5.0, "height_m": 2.6, "shape": "rectangle"},
  "walls_visible": ["back", "left"],
  "colors": {"walls": "#f2efe9", "floor": "#b08d62"},
  "openings": [
    {"wall": "left", "kind": "door", "position_fraction": 0.3, "width_m": 0.85,
     "height_m": 2.03, "sill_m": 0.0, "confidence": 0.7}
  ],
  "objects": [
    {"label": "Grey sofa", "category": "sofa", "width_m": 2.1, "height_m": 0.85, "depth_m": 0.9,
     "against_wall": "back" | "left" | "right" | "front" | "none",
     "across_fraction": 0.5, "into_fraction": 0.1, "facing": "front",
     "color": "#6b7a8f", "confidence": 0.8}
  ],
  "scale_anchors": ["door ~2.03 m tall"],
  "notes": "..."
}

Wall names are relative to the camera: "back" is the wall the camera faces
(z = 0), "front" is behind the camera (z = depth), "left" is x = 0 and "right"
is x = width. across_fraction runs 0..1 along x, into_fraction 0..1 along z
(0 = at the back wall, 1 = at the front wall).

Everything the builder produces is marked estimated. The builder never fails
on a bad draft: it clamps, snaps, nudges, and reports what it changed.
"""

from __future__ import annotations

import math
from typing import Any

from rs_core import geometry as g
from rs_core import model as m
from rs_core import placement
from rs_core.catalog import clamp_dimensions, normalize_category, spec_for

WALL_NAME_TO_INDEX = {"back": 0, "right": 1, "front": 2, "left": 3}
FACING_TO_YAW = {"back": 0.0, "right": -math.pi / 2, "front": math.pi, "left": math.pi / 2}


def _num(v: Any, default: float, lo: float, hi: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return min(max(f, lo), hi)


def _frac(v: Any, default: float = 0.5) -> float:
    return _num(v, default, 0.0, 1.0)


def _wall_name(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    k = v.strip().lower()
    aliases = {"rear": "back", "far": "back", "camera": "front", "near": "front", "behind": "front", "w1": "back", "w2": "right", "w3": "front", "w4": "left"}
    k = aliases.get(k, k)
    return k if k in WALL_NAME_TO_INDEX else None


def _color(v: Any, default: str) -> str:
    if isinstance(v, str):
        s = v.strip()
        if not s.startswith("#"):
            s = "#" + s
        if len(s) == 7 and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
            return s.lower()
        if len(s) == 4 and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
            return "#" + "".join(c * 2 for c in s[1:]).lower()
    return default


def build_scene(project_id: str, name: str, draft: dict | None, notes: list[str] | None = None) -> tuple[dict, list[str]]:
    """Build a scene from a draft. Returns (scene, notes about adjustments)."""
    notes = list(notes or [])
    draft = draft if isinstance(draft, dict) else {}
    room = draft.get("room") if isinstance(draft.get("room"), dict) else {}
    width = _num(room.get("width_m"), m.DEFAULT_ROOM["width_m"], 1.5, 30.0)
    depth = _num(room.get("depth_m"), m.DEFAULT_ROOM["depth_m"], 1.5, 30.0)
    height = _num(room.get("height_m"), m.DEFAULT_ROOM["height_m"], m.ROOM_HEIGHT_MIN, m.ROOM_HEIGHT_MAX)
    if "width_m" not in room or "depth_m" not in room:
        notes.append("Room size not given; used a default 4 x 5 m footprint.")
    scene = m.new_scene(project_id, name, width, depth, height)
    scene["calibration"] = {"status": "uncalibrated", "reference": None}

    colors = draft.get("colors") if isinstance(draft.get("colors"), dict) else {}
    wall_color = _color(colors.get("walls"), m.DEFAULT_WALL_COLOR)
    for w in scene["room"]["walls"]:
        w["color"] = wall_color
    scene["room"]["floor"]["color"] = _color(colors.get("floor"), m.DEFAULT_FLOOR_COLOR)

    walls = scene["room"]["walls"]

    # openings
    for i, o in enumerate(draft.get("openings") or []):
        if not isinstance(o, dict):
            continue
        wname = _wall_name(o.get("wall")) or "left"
        wall = walls[WALL_NAME_TO_INDEX[wname]]
        kind = str(o.get("kind", "door")).lower()
        if kind not in m.OPENING_KINDS:
            kind = "door"
        L = m.wall_length(scene, wall)
        default_w = {"door": 0.85, "window": 1.2, "opening": 1.0}[kind]
        w = _num(o.get("width_m"), default_w, 0.3, max(0.3, L))
        frac = _frac(o.get("position_fraction"))
        offset = max(0.0, min(L - w, frac * L - w / 2.0))
        h = _num(o.get("height_m"), {"door": 2.03, "window": 1.2, "opening": 2.1}[kind], 0.2, height)
        sill = _num(o.get("sill_m"), {"door": 0.0, "window": 0.9, "opening": 0.0}[kind], 0.0, height - 0.2)
        if sill + h > height:
            h = height - sill
        # avoid overlapping an earlier opening on the same wall: shift along
        spans = [(float(x["offset_m"]), float(x["offset_m"]) + float(x["width_m"])) for x in scene["room"]["openings"] if x["wall_id"] == wall["id"]]
        offset = _free_offset(offset, w, L, spans)
        if offset is None:
            notes.append(f"Dropped {kind} {i + 1} on the {wname} wall: no room left on that wall.")
            continue
        opening = m.make_opening(scene, wall["id"], kind, offset, w, h, sill, dims_source="estimated")
        scene["room"]["openings"].append(opening)

    # objects
    placed: list[dict] = []
    for i, d in enumerate(draft.get("objects") or []):
        if not isinstance(d, dict):
            continue
        label = str(d.get("label") or d.get("name") or d.get("category") or f"Object {i + 1}").strip()[:60]
        category = normalize_category(d.get("category") or label)
        if category == "other":
            category = _category_from_label(label)
        spec = spec_for(category)
        dims = (
            _num(d.get("width_m"), spec.default[0], 0.01, 20.0),
            _num(d.get("height_m"), spec.default[1], 0.01, 20.0),
            _num(d.get("depth_m"), spec.default[2], 0.01, 20.0),
        )
        dims, clamped = clamp_dimensions(category, dims)
        if clamped:
            notes.append(f"{label}: size clamped to the typical range for {category}.")
        conf = _num(d.get("confidence"), 0.5, 0.0, 1.0)
        obj = m.make_object(
            scene,
            label,
            category,
            dims,
            color=_color(d.get("color"), spec.color),
            provenance={"class": "generated_approximation", "dims_source": "estimated", "confidence": conf},
        )
        across = _frac(d.get("across_fraction"))
        into = _frac(d.get("into_fraction"))
        x = across * width
        z = into * depth
        facing = _wall_name(d.get("facing"))
        yaw = FACING_TO_YAW.get(facing, None) if facing else None
        against = _wall_name(d.get("against_wall"))
        obj["position_m"] = [x, 0.0, z]
        if yaw is not None:
            obj["yaw_rad"] = yaw
        if against:
            wall = walls[WALL_NAME_TO_INDEX[against]]
            L = m.wall_length(scene, wall)
            # offset along the wall from its start, derived from the fraction
            t = {"back": across, "right": into, "front": 1 - across, "left": 1 - into}[against] * L
            offset = max(0.0, min(L - dims[0], t - dims[0] / 2.0))
            pos, wyaw, _ = placement.resolve(scene, obj, {"against_wall": wall["id"], "align": "left", "offset_m": offset, "gap_m": 0.02})
            obj["position_m"] = pos
            obj["yaw_rad"] = wyaw if yaw is None else yaw
        elif yaw is None:
            obj["yaw_rad"] = math.pi  # free-standing default: face the camera
        mount = _mount_name(d.get("mount")) or spec.mount
        elevation = d.get("elevation_m")
        elevation = _num(elevation, -1.0, 0.0, height) if isinstance(elevation, (int, float)) else None
        if mount == "ceiling":
            # hangs from the ceiling: its underside at elevation_m, else flush to the ceiling
            obj["mount"] = "ceiling"
            y = elevation if elevation is not None else height - dims[1]
            obj["position_m"][1] = max(0.0, min(y, height - dims[1]))
        elif mount == "wall":
            obj["mount"] = "wall"
            y = elevation if elevation is not None else 1.2
            obj["position_m"][1] = max(0.0, min(y, height - dims[1]))
        elif mount == "surface" or _looks_tabletop(category, dims):
            host = _host_under(placed, obj)
            if host is not None and (mount == "surface" or host.get("category") in SURFACE_HOSTS):
                obj["position_m"][1] = m.object_top(host)
                obj["mount"] = "surface"
                if spec.mount != "surface":
                    notes.append(f"{label}: placed on top of {host['name']}.")
            elif mount == "surface" and elevation is not None:
                obj["position_m"][1] = elevation
                obj["mount"] = "surface"
        elif elevation is not None and elevation >= 0.3:
            obj["position_m"][1] = min(elevation, height - dims[1])  # e.g. a shelf fixed high on a wall
        _keep_inside(scene, obj)
        placed.append(obj)
        scene["objects"].append(obj)

    moved = nudge_apart(scene)
    if moved:
        notes.append("Nudged apart: " + ", ".join(moved) + ".")
    for o in scene["objects"]:
        _keep_inside(scene, o)
    scene["photos"] = []
    if draft.get("notes"):
        notes.append(_clip(str(draft["notes"]), 500))
    return scene, notes


CEILING_WORDS = ("ceiling light", "ceiling lamp", "pendant", "chandelier", "hanging light", "light fixture", "ceiling fan")


def _category_from_label(label: str) -> str:
    """When the model says 'other', a few label words still tell us how the thing mounts."""
    low = label.lower()
    if any(w in low for w in CEILING_WORDS):
        return "lamp_ceiling"
    return "other"


def _mount_name(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    return s if s in m.MOUNTS else None


def _clip(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    cut = text[:n]
    if " " in cut[n // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:") + "…"


def _free_offset(offset: float, w: float, L: float, spans: list[tuple[float, float]]) -> float | None:
    def clash(o: float) -> bool:
        return any(o < s1 and o + w > s0 for s0, s1 in spans)

    if not clash(offset):
        return offset
    # try sliding in 10 cm steps both ways
    for k in range(1, int(L / 0.1) + 1):
        for cand in (offset + 0.1 * k, offset - 0.1 * k):
            if 0.0 <= cand <= L - w and not clash(cand):
                return cand
    return None


# Floor categories that carry things: a small plant/lamp/box whose centre lands on one sits on it.
SURFACE_HOSTS = frozenset({"table_side", "table_coffee", "table_dining", "table", "desk", "nightstand", "dresser", "sideboard", "cabinet", "tv_stand", "counter", "shelf", "bookshelf", "ottoman"})
TABLETOP_MAX_HEIGHT_M = 0.6
TABLETOP_MAX_FOOTPRINT_M = 0.6


def _looks_tabletop(category: str, dims: tuple[float, float, float]) -> bool:
    """A small floor-category object (plant, box, 'other') that is more likely sitting on furniture."""
    return category in ("plant", "box", "other", "lamp_floor") and dims[1] <= TABLETOP_MAX_HEIGHT_M and max(dims[0], dims[2]) <= TABLETOP_MAX_FOOTPRINT_M


def _host_under(placed: list[dict], obj: dict) -> dict | None:
    """The floor object this one sits on: its centre is inside the host's footprint,
    or (estimated positions being what they are — the host may have been snapped
    to a wall after the model placed both at the same spot) its footprint touches
    the host's. The object is then pulled onto the host."""
    cx, _cy, cz = obj["position_m"]
    half = min(float(obj["dimensions_m"][0]), float(obj["dimensions_m"][2])) / 2.0
    for p in reversed(placed):
        if p.get("mount", "floor") != "floor" or p is obj:
            continue
        fp = m.footprint(p)
        if g.point_in_polygon((cx, cz), fp) or g.convex_overlap_depth(m.footprint(obj), fp) > 0.01:
            bx0, bz0, bx1, bz1 = g.bounds(fp)
            obj["position_m"][0] = min(max(cx, bx0 + half), bx1 - half) if bx1 - bx0 > 2 * half else (bx0 + bx1) / 2
            obj["position_m"][2] = min(max(cz, bz0 + half), bz1 - half) if bz1 - bz0 > 2 * half else (bz0 + bz1) / 2
            return p
    return None


def _keep_inside(scene: dict, obj: dict) -> None:
    """Translate the object so its footprint is inside the room (rectangles)."""
    x0, z0, x1, z1 = m.room_bounds(scene)
    for _ in range(3):
        fp = m.footprint(obj)
        bx0, bz0, bx1, bz1 = g.bounds(fp)
        dx = dz = 0.0
        if bx0 < x0:
            dx = x0 - bx0
        elif bx1 > x1:
            dx = x1 - bx1
        if bz0 < z0:
            dz = z0 - bz0
        elif bz1 > z1:
            dz = z1 - bz1
        if abs(dx) < 1e-9 and abs(dz) < 1e-9:
            return
        obj["position_m"][0] += dx
        obj["position_m"][2] += dz


def nudge_apart(scene: dict, rounds: int = 12) -> list[str]:
    """Push overlapping floor objects apart along their own right axis (along the
    wall they sit against). The smaller one moves first; if a wall stops it, the
    larger one gives way. Things sitting on a moved object ride along. Small,
    deterministic, never perfect."""
    floor = [o for o in scene["objects"] if o.get("mount", "floor") == "floor" and o.get("category") != "rug" and float(o["position_m"][1]) < 1.9]
    riders = [o for o in scene["objects"] if o.get("mount") == "surface"]
    moved: set[str] = set()

    def slide(obj: dict, away_from: dict, amount: float) -> bool:
        before = (obj["position_m"][0], obj["position_m"][2])
        r = g.right_vector(float(obj.get("yaw_rad", 0.0)))
        toward = g.sub(before, (away_from["position_m"][0], away_from["position_m"][2]))
        sign = 1.0 if g.dot(r, toward) >= 0 else -1.0
        step = g.scale(r, sign * amount)
        host_fp = m.footprint(obj)
        obj["position_m"][0] += step[0]
        obj["position_m"][2] += step[1]
        _keep_inside(scene, obj)
        dx, dz = obj["position_m"][0] - before[0], obj["position_m"][2] - before[1]
        if abs(dx) < 1e-9 and abs(dz) < 1e-9:
            return False
        top = m.object_top(obj)
        for rd in riders:  # carry what sits on it: centre over the footprint, resting at its top
            if abs(float(rd["position_m"][1]) - top) < 0.02 and g.point_in_polygon((rd["position_m"][0], rd["position_m"][2]), host_fp):
                rd["position_m"][0] += dx
                rd["position_m"][2] += dz
        moved.add(f"{obj['name']} ({obj['id']})")
        return True

    for _ in range(rounds):
        any_move = False
        for i in range(len(floor)):
            for j in range(i + 1, len(floor)):
                a, b = floor[i], floor[j]
                depth = g.convex_overlap_depth(m.footprint(a), m.footprint(b))
                if depth <= 0.01:
                    continue
                mover, anchor = (a, b) if _area(a) <= _area(b) else (b, a)
                if slide(mover, anchor, depth + 0.03):
                    any_move = True
                remaining = g.convex_overlap_depth(m.footprint(a), m.footprint(b))
                if remaining > 0.01 and slide(anchor, mover, remaining + 0.03):  # the wall stopped the small one
                    any_move = True
        if not any_move:
            break
    return sorted(moved)


def _area(o: dict) -> float:
    return float(o["dimensions_m"][0]) * float(o["dimensions_m"][2])


DRAFT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "room": {
            "type": "object",
            "properties": {
                "width_m": {"type": "number", "description": "Estimated distance between the left and right walls, metres"},
                "depth_m": {"type": "number", "description": "Estimated distance from the back wall to the camera wall, metres"},
                "height_m": {"type": "number", "description": "Estimated ceiling height, metres"},
                "shape": {"type": "string", "enum": ["rectangle"]},
            },
            "required": ["width_m", "depth_m", "height_m"],
        },
        "walls_visible": {"type": "array", "items": {"type": "string", "enum": ["back", "left", "right", "front"]}},
        "colors": {
            "type": "object",
            "properties": {"walls": {"type": "string"}, "floor": {"type": "string"}},
        },
        "openings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "wall": {"type": "string", "enum": ["back", "left", "right", "front"]},
                    "kind": {"type": "string", "enum": ["door", "window", "opening"]},
                    "position_fraction": {"type": "number", "description": "Centre of the opening along its wall, 0 at the wall's left end as seen from inside, 1 at its right end"},
                    "width_m": {"type": "number"},
                    "height_m": {"type": "number"},
                    "sill_m": {"type": "number", "description": "Height of the bottom edge above the floor; 0 for doors"},
                    "confidence": {"type": "number"},
                },
                "required": ["wall", "kind", "position_fraction", "width_m"],
            },
        },
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Short name, e.g. 'Grey sofa'"},
                    "category": {"type": "string", "description": "One of: sofa, armchair, chair, bed_double, bed_single, nightstand, desk, table_dining, table_coffee, table_side, bookshelf, shelf, wardrobe, dresser, cabinet, tv_stand, tv, rug, plant, lamp_floor, lamp_table, fridge, counter, other"},
                    "width_m": {"type": "number", "description": "Across the front"},
                    "height_m": {"type": "number"},
                    "depth_m": {"type": "number", "description": "Front to back"},
                    "against_wall": {"type": "string", "enum": ["back", "left", "right", "front", "none"]},
                    "across_fraction": {"type": "number", "description": "Centre position left (0) to right (1) across the room"},
                    "into_fraction": {"type": "number", "description": "Centre position from the back wall (0) to the camera (1)"},
                    "facing": {"type": "string", "enum": ["back", "left", "right", "front"], "description": "Which wall the object's front faces"},
                    "mount": {"type": "string", "enum": ["floor", "surface", "wall", "ceiling"], "description": "floor: stands on the floor; surface: sits on another piece of furniture; wall: fixed to a wall (picture, mirror, wall TV, shelf); ceiling: hangs from the ceiling (pendant light)"},
                    "elevation_m": {"type": "number", "description": "Height of the object's lowest point above the floor; 0 for floor objects, the table top for surface objects, the bottom edge for wall and ceiling objects"},
                    "color": {"type": "string", "description": "Hex colour like #6b7a8f"},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "category", "width_m", "height_m", "depth_m", "against_wall", "across_fraction", "into_fraction"],
            },
        },
        "scale_anchors": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["room", "objects"],
}

DRAFT_JSON_SCHEMA_SMALL: dict = {
    "type": "object",
    "properties": {
        "room": {
            "type": "object",
            "properties": {"width_m": {"type": "number"}, "depth_m": {"type": "number"}, "height_m": {"type": "number"}},
            "required": ["width_m", "depth_m", "height_m"],
        },
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "category": {"type": "string"},
                    "against_wall": {"type": "string", "enum": ["back", "left", "right", "front", "none"]},
                    "across_fraction": {"type": "number"},
                    "into_fraction": {"type": "number"},
                },
                "required": ["label", "category"],
            },
        },
    },
    "required": ["room", "objects"],
}

DRAFT_INSTRUCTIONS = """You are measuring a room from one or more photos for a 3D planner.
Return only the JSON described by the schema. Think in metres.
Use known sizes as anchors: an interior door is about 0.8 m wide and 2.03 m tall; a kitchen counter is about 0.9 m high; a sofa seat is about 0.45 m high; a standard ceiling is 2.4 to 2.7 m.
Phone photos are wide-angle and make rooms look much deeper than they are: estimate the room's depth from the furniture along the side walls (how many sofa-lengths or door-widths the wall holds), not from how far away the back wall looks. Prefer underestimating depth.
Walls are named from the camera's point of view: 'back' is the wall the camera faces, 'left' and 'right' are the side walls, 'front' is behind the camera. Give every piece of furniture you can see with a short label, a category from the list, estimated width (across its front), height and depth, which wall it stands against ('none' if free-standing), its centre as fractions across the room (0 = left wall, 1 = right wall) and into the room (0 = back wall, 1 = camera), and which wall its front faces.
Say how each thing is mounted: 'floor' for furniture standing on the floor, 'surface' for things sitting on other furniture (a plant on a table), 'wall' for things fixed to a wall (pictures, mirrors, wall-mounted TVs, shelves) and 'ceiling' for things hanging from the ceiling (pendant lights, fans); give elevation_m, the height of its lowest point above the floor. Pictures leaning on the floor are 'floor'.
List doors and windows with the wall they are on and their centre as a fraction along that wall (0 at the wall's left end as seen from inside, 1 at its right end).
Give a confidence from 0 to 1 per item and name the scale anchors you used. Do not invent things you cannot see; the far side of the room may be unknown."""
