"""Scene data shapes, defaults, ID allocation and accessors.

A scene is a plain dict (JSON-serialisable). Functions here never mutate the
scene they are given unless their name says so (``alloc_id`` is the one
exception: it updates the scene's ID counters in place, by design, so IDs are
never reused within a project).
"""

from __future__ import annotations

import copy
import math
import uuid
from typing import Any

from rs_core import geometry as g
from rs_core.catalog import normalize_category, spec_for

SCHEMA_VERSION = 1

DEFAULT_ROOM = {"width_m": 4.0, "depth_m": 5.0, "height_m": 2.5}
DEFAULT_WALL_COLOR = "#f2efe9"
DEFAULT_FLOOR_COLOR = "#b08d62"
DEFAULT_CEILING_COLOR = "#ffffff"

# Hard limits (section 8 of the plan)
OBJECT_DIM_MIN = 0.01
OBJECT_DIM_MAX = 20.0
ROOM_HEIGHT_MIN = 1.8
ROOM_HEIGHT_MAX = 6.0
ROOM_SIDE_MIN = 0.5
ROOM_SIDE_MAX = 50.0

RECT_WALL_LABELS = ("back", "right", "front", "left")

OPENING_KINDS = ("door", "window", "opening")
SWINGS = ("in", "out", "none")
HINGES = ("left", "right")
MOUNTS = ("floor", "wall", "surface")
SHAPES = ("box", "cylinder")
DIMS_SOURCES = ("estimated", "stated", "measured")
PROVENANCE_CLASSES = ("generated_approximation", "dimensioned_placeholder", "user_supplied")


class SceneError(ValueError):
    """A hard validation failure. ``code`` is machine-readable."""

    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        d.update(self.extra)
        return d


def new_project_id() -> str:
    return str(uuid.uuid4())


def alloc_id(scene: dict, prefix: str) -> str:
    counters = scene.setdefault("id_counters", {})
    n = int(counters.get(prefix, 0)) + 1
    counters[prefix] = n
    return f"{prefix}{n}"


def new_scene(
    project_id: str,
    name: str,
    width_m: float = DEFAULT_ROOM["width_m"],
    depth_m: float = DEFAULT_ROOM["depth_m"],
    height_m: float = DEFAULT_ROOM["height_m"],
) -> dict:
    """A rectangular, empty, uncalibrated room."""
    scene: dict = {
        "schema_version": SCHEMA_VERSION,
        "project": {"id": project_id, "name": name, "units": "m"},
        "calibration": {"status": "uncalibrated", "reference": None},
        "room": {
            "height_m": float(height_m),
            "vertices": [],
            "walls": [],
            "floor": {"color": DEFAULT_FLOOR_COLOR},
            "ceiling": {"color": DEFAULT_CEILING_COLOR},
            "openings": [],
        },
        "objects": [],
        "photos": [],
        "id_counters": {},
    }
    set_rectangle(scene, float(width_m), float(depth_m))
    return scene


def set_rectangle(scene: dict, width_m: float, depth_m: float) -> None:
    """Replace the outline with a rectangle (back wall along z = 0). Mutates."""
    room = scene["room"]
    pts = [(0.0, 0.0), (width_m, 0.0), (width_m, depth_m), (0.0, depth_m)]
    if len(room["vertices"]) == 4 and len(room["walls"]) == 4:
        for v, (x, z) in zip(room["vertices"], pts):
            v["x"], v["z"] = x, z
        return
    room["vertices"] = []
    room["walls"] = []
    vids = [alloc_id(scene, "v") for _ in pts]
    for vid, (x, z) in zip(vids, pts):
        room["vertices"].append({"id": vid, "x": x, "z": z})
    for i in range(4):
        room["walls"].append(
            {
                "id": alloc_id(scene, "w"),
                "a": vids[i],
                "b": vids[(i + 1) % 4],
                "color": DEFAULT_WALL_COLOR,
                "label": RECT_WALL_LABELS[i],
            }
        )


# ---------------------------------------------------------------- accessors


def vertex_map(scene: dict) -> dict[str, dict]:
    return {v["id"]: v for v in scene["room"]["vertices"]}


def wall_map(scene: dict) -> dict[str, dict]:
    return {w["id"]: w for w in scene["room"]["walls"]}


def opening_map(scene: dict) -> dict[str, dict]:
    return {o["id"]: o for o in scene["room"]["openings"]}


def object_map(scene: dict) -> dict[str, dict]:
    return {o["id"]: o for o in scene["objects"]}


def outline(scene: dict) -> list[g.Point]:
    return [(float(v["x"]), float(v["z"])) for v in scene["room"]["vertices"]]


def wall_segment(scene: dict, wall: dict | str) -> tuple[g.Point, g.Point]:
    if isinstance(wall, str):
        wall = find_wall(scene, wall)
    vm = vertex_map(scene)
    a, b = vm[wall["a"]], vm[wall["b"]]
    return ((float(a["x"]), float(a["z"])), (float(b["x"]), float(b["z"])))


def wall_length(scene: dict, wall: dict | str) -> float:
    a, b = wall_segment(scene, wall)
    return g.distance(a, b)


def wall_inward_normal(scene: dict, wall: dict | str) -> g.Point:
    a, b = wall_segment(scene, wall)
    return g.inward_normal(a, b)


def wall_direction(scene: dict, wall: dict | str) -> g.Point:
    a, b = wall_segment(scene, wall)
    return g.normalize(g.sub(b, a))


def find_wall(scene: dict, wall_id: str) -> dict:
    w = wall_map(scene).get(wall_id)
    if w is None:
        w = _find_wall_by_label(scene, wall_id)
    if w is None:
        raise SceneError("unknown_id", f"No wall with id {wall_id!r}", id=wall_id)
    return w


def _find_wall_by_label(scene: dict, label: str) -> dict | None:
    key = str(label).strip().lower()
    for w in scene["room"]["walls"]:
        if str(w.get("label", "")).lower() == key:
            return w
    return None


def find_object(scene: dict, object_id: str) -> dict:
    o = object_map(scene).get(object_id)
    if o is None:
        raise SceneError("unknown_id", f"No object with id {object_id!r}", id=object_id)
    return o


def find_opening(scene: dict, opening_id: str) -> dict:
    o = opening_map(scene).get(opening_id)
    if o is None:
        raise SceneError("unknown_id", f"No opening with id {opening_id!r}", id=opening_id)
    return o


def find_vertex(scene: dict, vertex_id: str) -> dict:
    v = vertex_map(scene).get(vertex_id)
    if v is None:
        raise SceneError("unknown_id", f"No vertex with id {vertex_id!r}", id=vertex_id)
    return v


def wall_index(scene: dict, wall_id: str) -> int:
    for i, w in enumerate(scene["room"]["walls"]):
        if w["id"] == wall_id:
            return i
    raise SceneError("unknown_id", f"No wall with id {wall_id!r}", id=wall_id)


def is_rectangle(scene: dict, tol: float = 1e-6) -> bool:
    pts = outline(scene)
    if len(pts) != 4:
        return False
    for i in range(4):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % 4]
        if abs(g.dot(g.sub(a, b), g.sub(c, b))) > tol * max(1.0, g.distance(a, b) * g.distance(c, b)):
            return False
    return True


def room_bounds(scene: dict) -> tuple[float, float, float, float]:
    return g.bounds(outline(scene))


def room_size(scene: dict) -> tuple[float, float]:
    """(width along x, depth along z) of the outline's bounding box."""
    x0, z0, x1, z1 = room_bounds(scene)
    return (x1 - x0, z1 - z0)


def footprint(obj: dict) -> list[g.Point]:
    w, _h, d = obj["dimensions_m"]
    x, _y, z = obj["position_m"]
    return g.rect_corners((float(x), float(z)), float(w), float(d), float(obj.get("yaw_rad", 0.0)))


def object_top(obj: dict) -> float:
    return float(obj["position_m"][1]) + float(obj["dimensions_m"][1])


def opening_span(scene: dict, opening: dict) -> tuple[g.Point, g.Point]:
    """Endpoints of the opening along its wall."""
    a, b = wall_segment(scene, opening["wall_id"])
    d = g.normalize(g.sub(b, a))
    start = g.add(a, g.scale(d, float(opening["offset_m"])))
    end = g.add(start, g.scale(d, float(opening["width_m"])))
    return (start, end)


# ---------------------------------------------------------------- builders


def make_object(
    scene: dict,
    name: str,
    category: str | None = None,
    dimensions_m: tuple[float, float, float] | None = None,
    position_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    yaw_rad: float = 0.0,
    color: str | None = None,
    shape: str | None = None,
    mount: str | None = None,
    provenance: dict | None = None,
    product: dict | None = None,
    locked: bool = False,
) -> dict:
    """Build an object dict with an allocated id and category defaults."""
    cat = normalize_category(category or name)
    spec = spec_for(cat)
    dims = tuple(float(v) for v in (dimensions_m or spec.default))
    prov = {
        "class": "user_supplied",
        "dims_source": "stated",
        "confidence": 1.0,
    }
    if provenance:
        prov.update(provenance)
    return {
        "id": alloc_id(scene, "ob"),
        "name": str(name),
        "category": cat,
        "shape": shape or spec.shape,
        "dimensions_m": [dims[0], dims[1], dims[2]],
        "position_m": [float(position_m[0]), float(position_m[1]), float(position_m[2])],
        "yaw_rad": g.normalize_yaw(float(yaw_rad)),
        "mount": mount or spec.mount,
        "color": color or spec.color,
        "locked": bool(locked),
        "provenance": prov,
        "product": product,
    }


def make_opening(
    scene: dict,
    wall_id: str,
    kind: str,
    offset_m: float,
    width_m: float,
    height_m: float | None = None,
    sill_m: float | None = None,
    swing: str | None = None,
    hinge: str | None = None,
    dims_source: str = "stated",
) -> dict:
    kind = str(kind).lower()
    if kind not in OPENING_KINDS:
        raise SceneError("invalid_value", f"Opening kind must be one of {OPENING_KINDS}", field="kind")
    if height_m is None:
        height_m = {"door": 2.03, "window": 1.2, "opening": 2.1}[kind]
    if sill_m is None:
        sill_m = {"door": 0.0, "window": 0.9, "opening": 0.0}[kind]
    if swing is None:
        swing = "in" if kind == "door" else "none"
    if hinge is None:
        hinge = "left"
    return {
        "id": alloc_id(scene, "o"),
        "wall_id": wall_id,
        "kind": kind,
        "offset_m": float(offset_m),
        "width_m": float(width_m),
        "height_m": float(height_m),
        "sill_m": float(sill_m),
        "swing": swing,
        "hinge": hinge,
        "dims_source": dims_source,
    }


def clone(scene: dict) -> dict:
    return copy.deepcopy(scene)


def round_scene(scene: dict, ndigits: int = 4) -> dict:
    """Round floats for stable storage and readable output. Returns a copy."""

    def rnd(v: Any) -> Any:
        if isinstance(v, bool):
            return v
        if isinstance(v, float):
            if not math.isfinite(v):
                return v
            r = round(v, ndigits)
            return 0.0 if r == 0 else r
        if isinstance(v, list):
            return [rnd(x) for x in v]
        if isinstance(v, dict):
            return {k: rnd(x) for k, x in v.items()}
        return v

    return rnd(scene)
