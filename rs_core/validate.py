"""Hard rules (reject the command) and soft issues (apply, then report).

Hard: ``validate_hard(scene)`` raises SceneError.
Soft: ``issues(scene)`` returns a list of dicts
      {"code", "severity", "ids", "message", ...numbers}.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Iterable

from rs_core import geometry as g
from rs_core import model as m
from rs_core import money
from rs_core.model import SceneError

OVERLAP_MIN_DEPTH = 0.01      # m of penetration before two objects "overlap"
DOOR_CLEAR_DEPTH = 0.8        # m of clear floor in front of a doorway
WINDOW_CLEARANCE = 0.10       # m
WALKWAY_MIN = 0.60            # m
WALKWAY_GRID = 0.10           # m
OUTSIDE_TOL = 0.005           # m


# ---------------------------------------------------------------- hard


def validate_hard(scene: dict) -> None:
    room = scene.get("room") or {}
    verts = room.get("vertices") or []
    walls = room.get("walls") or []
    if len(verts) < 3:
        raise SceneError("invalid_room", "A room needs at least three corners")
    pts = []
    for v in verts:
        x, z = v.get("x"), v.get("z")
        if not g.is_finite(x, z):
            raise SceneError("invalid_value", f"Corner {v.get('id')} has a non-finite coordinate", id=v.get("id"))
        pts.append((float(x), float(z)))
    _validate_budget(scene.get("budget"))
    if not g.polygon_is_simple(pts):
        raise SceneError("invalid_room", "The room outline crosses itself or has a zero-length wall")
    if g.polygon_area(pts) < 0.1:
        raise SceneError("invalid_room", "The room is too small (under 0.1 m²)")
    if len(walls) != len(verts):
        raise SceneError("invalid_room", "Wall count must match corner count")
    vids = {v["id"] for v in verts}
    for i, w in enumerate(walls):
        if w.get("a") not in vids or w.get("b") not in vids:
            raise SceneError("invalid_room", f"Wall {w.get('id')} refers to a missing corner", id=w.get("id"))
        if w["a"] != verts[i]["id"] or w["b"] != verts[(i + 1) % len(verts)]["id"]:
            raise SceneError("invalid_room", "Walls must join consecutive corners")
    h = room.get("height_m")
    if not g.is_finite(h) or not (m.ROOM_HEIGHT_MIN <= float(h) <= m.ROOM_HEIGHT_MAX):
        raise SceneError("out_of_range", f"Room height must be between {m.ROOM_HEIGHT_MIN} and {m.ROOM_HEIGHT_MAX} m", field="height_m")

    wall_ids = {w["id"] for w in walls}
    seen_openings: dict[str, list[tuple[float, float]]] = {}
    for o in room.get("openings") or []:
        if o.get("wall_id") not in wall_ids:
            raise SceneError("unknown_id", f"Opening {o.get('id')} is on a missing wall", id=o.get("id"))
        off, wid, hei, sill = (o.get(k) for k in ("offset_m", "width_m", "height_m", "sill_m"))
        if not g.is_finite(off, wid, hei, sill):
            raise SceneError("invalid_value", f"Opening {o.get('id')} has a non-finite size", id=o.get("id"))
        off, wid, hei, sill = float(off), float(wid), float(hei), float(sill)
        if wid <= 0 or hei <= 0 or off < -1e-9 or sill < -1e-9:
            raise SceneError("invalid_value", f"Opening {o.get('id')} has a non-positive size", id=o.get("id"))
        L = m.wall_length(scene, o["wall_id"])
        if off + wid > L + 1e-6:
            raise SceneError("opening_outside_wall", f"Opening {o['id']} extends past wall {o['wall_id']} ({L:.2f} m long)", id=o["id"])
        if sill + hei > float(h) + 1e-6:
            raise SceneError("opening_too_tall", f"Opening {o['id']} is taller than the room", id=o["id"])
        spans = seen_openings.setdefault(o["wall_id"], [])
        for s0, s1 in spans:
            if off < s1 - 1e-6 and off + wid > s0 + 1e-6:
                raise SceneError("openings_overlap", f"Opening {o['id']} overlaps another opening on wall {o['wall_id']}", id=o["id"])
        spans.append((off, off + wid))

    ids: set[str] = set()
    for obj in scene.get("objects") or []:
        oid = obj.get("id")
        if not oid or oid in ids:
            raise SceneError("invalid_value", f"Duplicate or missing object id {oid!r}", id=oid)
        ids.add(oid)
        dims = obj.get("dimensions_m")
        pos = obj.get("position_m")
        if not isinstance(dims, list) or len(dims) != 3 or not g.is_finite(*dims):
            raise SceneError("invalid_value", f"{oid} has invalid dimensions", id=oid)
        if not isinstance(pos, list) or len(pos) != 3 or not g.is_finite(*pos):
            raise SceneError("invalid_value", f"{oid} has an invalid position", id=oid)
        if not g.is_finite(obj.get("yaw_rad", 0.0)):
            raise SceneError("invalid_value", f"{oid} has an invalid rotation", id=oid)
        for d in dims:
            if not (m.OBJECT_DIM_MIN <= float(d) <= m.OBJECT_DIM_MAX):
                raise SceneError("out_of_range", f"{obj.get('name', oid)} has a dimension outside {m.OBJECT_DIM_MIN}-{m.OBJECT_DIM_MAX} m", id=oid)
        if abs(float(pos[0])) > 1000 or abs(float(pos[2])) > 1000 or float(pos[1]) < -1 or float(pos[1]) > m.ROOM_HEIGHT_MAX:
            raise SceneError("out_of_range", f"{obj.get('name', oid)} is placed absurdly far away", id=oid)


# ---------------------------------------------------------------- soft


OVERHEAD_MIN_M = 1.9  # an object whose underside is this high is walked under, whatever its mount says


def _is_overhead(o: dict) -> bool:
    return float(o["position_m"][1]) >= OVERHEAD_MIN_M or o.get("mount") == "ceiling"


def _floor_objects(scene: dict) -> list[dict]:
    """Objects that occupy floor space for overlap, door, walkway and outside checks:
    floor-mounted, not a rug, and not hanging overhead (pendant lights, a shelf at 2 m)."""
    return [o for o in scene["objects"] if o.get("mount", "floor") == "floor" and o.get("category") != "rug" and not _is_overhead(o)]


def issues(scene: dict, only_ids: Iterable[str] | None = None) -> list[dict]:
    """All soft issues. With `only_ids`, keep issues touching any of those ids."""
    out: list[dict] = []
    out += _overlaps(scene)
    out += _outside(scene)
    out += _door_blocks(scene)
    out += _window_blocks(scene)
    out += _too_tall(scene)
    out += _walkway(scene)
    if scene.get("calibration", {}).get("status") != "calibrated":
        out.append(
            {
                "code": "uncalibrated",
                "severity": "info",
                "ids": [],
                "message": "Sizes are estimates until you give one real measurement (a wall, a door or an object).",
            }
        )
    out += _over_budget(scene)
    if only_ids is not None:
        keep = set(only_ids)
        out = [i for i in out if not i["ids"] or keep.intersection(i["ids"])]
    return out


def _validate_budget(budget: object) -> None:
    if budget is None:
        return
    ok = isinstance(budget, dict) and isinstance(budget.get("limit"), (int, float)) and not isinstance(budget.get("limit"), bool)
    if ok:
        limit, reserve, cur = float(budget["limit"]), budget.get("reserve", 0.0), budget.get("currency")
        ok = (
            math.isfinite(limit) and 0 < limit <= money.MAX_AMOUNT
            and isinstance(reserve, (int, float)) and not isinstance(reserve, bool) and math.isfinite(reserve) and 0 <= reserve < limit
            and (cur is None or (isinstance(cur, str) and money.currency_code(cur) == cur))
        )
    if not ok:
        raise SceneError("invalid_value", "budget must be {limit > 0, currency: 'USD' or null, reserve: 0 <= amount < limit}", field="budget")


def _over_budget(scene: dict) -> list[dict]:
    """The one money issue: the room costs more than the budget the user gave.
    Reported, never enforced."""
    status = money.budget_status(scene)
    if not status or not status["over_limit"]:
        return []
    cur = status["currency"]
    return [
        {
            "code": "over_budget",
            "severity": "warning",
            "ids": [i["id"] for i in status["items"]],
            "message": f"{money.format_money(status['spent'], cur)} spent of {money.format_money(status['limit'], cur)}: {money.format_money(-status['remaining'], cur)} over",
            "over": -status["remaining"],
        }
    ]


def _overlaps(scene: dict) -> list[dict]:
    out = []
    objs = _floor_objects(scene)
    fps = {o["id"]: m.footprint(o) for o in objs}
    for i in range(len(objs)):
        for j in range(i + 1, len(objs)):
            a, b = objs[i], objs[j]
            # stacked objects (surface-mounted) are excluded above; a tall and a
            # short object can still overlap on the floor
            depth = g.convex_overlap_depth(fps[a["id"]], fps[b["id"]])
            if depth > OVERLAP_MIN_DEPTH:
                out.append(
                    {
                        "code": "overlap",
                        "severity": "warning",
                        "ids": [a["id"], b["id"]],
                        "overlap_m": round(depth, 3),
                        "message": f"{a['name']} ({a['id']}) and {b['name']} ({b['id']}) overlap by {depth * 100:.0f} cm",
                    }
                )
    return out


def _outside(scene: dict) -> list[dict]:
    out = []
    poly = m.outline(scene)
    for o in scene["objects"]:
        if o.get("mount") in ("wall", "ceiling"):
            continue
        corners = m.footprint(o)
        if any(not g.point_in_polygon(c, poly, OUTSIDE_TOL) for c in corners):
            worst = max(_distance_outside(c, poly) for c in corners)
            out.append(
                {
                    "code": "outside_room",
                    "severity": "warning",
                    "ids": [o["id"]],
                    "outside_m": round(worst, 3),
                    "message": f"{o['name']} ({o['id']}) sticks out of the room by {worst * 100:.0f} cm",
                }
            )
    return out


def _distance_outside(p: g.Point, poly: list[g.Point]) -> float:
    if g.point_in_polygon(p, poly, OUTSIDE_TOL):
        return 0.0
    n = len(poly)
    return min(g.point_segment_distance(p, poly[i], poly[(i + 1) % n]) for i in range(n))


def door_zones(scene: dict) -> list[tuple[dict, list[g.Point]]]:
    """Convex zones that must stay clear for each door: the clear strip in front
    of the doorway plus (for in-swinging doors) the swing square."""
    zones = []
    for o in scene["room"]["openings"]:
        if o["kind"] not in ("door", "opening"):
            continue
        start, end = m.opening_span(scene, o)
        n = m.wall_inward_normal(scene, o["wall_id"])
        depth = DOOR_CLEAR_DEPTH
        if o["kind"] == "door" and o.get("swing", "in") == "in":
            depth = max(depth, float(o["width_m"]))
        strip = [start, end, g.add(end, g.scale(n, depth)), g.add(start, g.scale(n, depth))]
        zones.append((o, strip))
    return zones


def _door_blocks(scene: dict) -> list[dict]:
    out = []
    objs = _floor_objects(scene)
    for o, zone in door_zones(scene):
        for obj in objs:
            depth = g.convex_overlap_depth(m.footprint(obj), zone)
            if depth > OVERLAP_MIN_DEPTH:
                out.append(
                    {
                        "code": "blocks_door",
                        "severity": "warning",
                        "ids": [obj["id"], o["id"]],
                        "message": f"{obj['name']} ({obj['id']}) blocks {o['kind']} {o['id']} (needs {DOOR_CLEAR_DEPTH:.1f} m clear in front)",
                    }
                )
    return out


def _window_blocks(scene: dict) -> list[dict]:
    out = []
    for o in scene["room"]["openings"]:
        if o["kind"] != "window":
            continue
        start, end = m.opening_span(scene, o)
        sill = float(o["sill_m"])
        for obj in scene["objects"]:
            if obj.get("mount") in ("wall", "ceiling") or _is_overhead(obj):
                continue
            if m.object_top(obj) <= sill + 1e-6:
                continue
            dist = g.polygon_segment_distance(m.footprint(obj), start, end)
            if dist < WINDOW_CLEARANCE:
                out.append(
                    {
                        "code": "blocks_window",
                        "severity": "info",
                        "ids": [obj["id"], o["id"]],
                        "message": f"{obj['name']} ({obj['id']}) stands in front of window {o['id']} and rises above its sill",
                    }
                )
    return out


def _too_tall(scene: dict) -> list[dict]:
    out = []
    h = float(scene["room"]["height_m"])
    for obj in scene["objects"]:
        top = m.object_top(obj)
        if top > h + 1e-6:
            out.append(
                {
                    "code": "too_tall",
                    "severity": "warning",
                    "ids": [obj["id"]],
                    "message": f"{obj['name']} ({obj['id']}) reaches {top:.2f} m, above the {h:.2f} m ceiling",
                }
            )
    return out


# ---------------------------------------------------------------- walkway


def _grid(scene: dict, blockers: list[dict]) -> tuple[list[list[bool]], float, float, int, int]:
    x0, z0, x1, z1 = m.room_bounds(scene)
    poly = m.outline(scene)
    cols = max(1, int(math.ceil((x1 - x0) / WALKWAY_GRID)))
    rows = max(1, int(math.ceil((z1 - z0) / WALKWAY_GRID)))
    half = WALKWAY_MIN / 2.0
    inflated = [g.rect_corners((o["position_m"][0], o["position_m"][2]), o["dimensions_m"][0] + 2 * half, o["dimensions_m"][2] + 2 * half, o.get("yaw_rad", 0.0)) for o in blockers]
    free = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        cz = z0 + (r + 0.5) * WALKWAY_GRID
        for c in range(cols):
            cx = x0 + (c + 0.5) * WALKWAY_GRID
            p = (cx, cz)
            if not g.point_in_polygon(p, poly):
                continue
            # keep half a walkway from the walls too
            n = len(poly)
            if min(g.point_segment_distance(p, poly[i], poly[(i + 1) % n]) for i in range(n)) < half - 1e-9:
                continue
            if any(g.point_in_polygon(p, fp) for fp in inflated):
                continue
            free[r][c] = True
    return free, x0, z0, cols, rows


def _reachable(free: list[list[bool]], start: tuple[int, int], goal: tuple[int, int]) -> bool:
    rows, cols = len(free), len(free[0])
    sr, sc = start
    gr, gc = goal
    sr, sc = max(0, min(rows - 1, sr)), max(0, min(cols - 1, sc))
    gr, gc = max(0, min(rows - 1, gr)), max(0, min(cols - 1, gc))
    if not free[sr][sc]:
        # the start cell may itself be in the wall clearance band; look around it
        for dr in (-2, -1, 0, 1, 2):
            for dc in (-2, -1, 0, 1, 2):
                r, c = sr + dr, sc + dc
                if 0 <= r < rows and 0 <= c < cols and free[r][c]:
                    sr, sc = r, c
                    break
            else:
                continue
            break
        else:
            return False
    if not free[gr][gc]:
        for dr in (-3, -2, -1, 0, 1, 2, 3):
            for dc in (-3, -2, -1, 0, 1, 2, 3):
                r, c = gr + dr, gc + dc
                if 0 <= r < rows and 0 <= c < cols and free[r][c]:
                    gr, gc = r, c
                    break
            else:
                continue
            break
        else:
            return False
    seen = {(sr, sc)}
    q = deque([(sr, sc)])
    while q:
        r, c = q.popleft()
        if (r, c) == (gr, gc):
            return True
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and free[nr][nc] and (nr, nc) not in seen:
                seen.add((nr, nc))
                q.append((nr, nc))
    return False


def _walkway(scene: dict) -> list[dict]:
    doors = [o for o in scene["room"]["openings"] if o["kind"] in ("door", "opening")]
    if not doors:
        return []
    objs = _floor_objects(scene)
    if not objs:
        return []
    poly = m.outline(scene)
    cx, cz = g.centroid(poly)
    out = []
    for door in doors:
        start, end = m.opening_span(scene, door)
        n = m.wall_inward_normal(scene, door["wall_id"])
        mid = g.add(g.scale(g.add(start, end), 0.5), g.scale(n, WALKWAY_MIN / 2.0 + 0.05))

        def cell(p: g.Point, x0: float, z0: float) -> tuple[int, int]:
            return (int((p[1] - z0) / WALKWAY_GRID), int((p[0] - x0) / WALKWAY_GRID))

        free, x0, z0, _cols, _rows = _grid(scene, objs)
        if _reachable(free, cell(mid, x0, z0), cell((cx, cz), x0, z0)):
            continue
        # find which objects, removed alone, would open the path
        culprits = []
        for o in objs:
            others = [x for x in objs if x["id"] != o["id"]]
            f2, _x0, _z0, _c, _r = _grid(scene, others)
            if _reachable(f2, cell(mid, x0, z0), cell((cx, cz), x0, z0)):
                culprits.append(o["id"])
        names = ", ".join(f"{m.find_object(scene, i)['name']} ({i})" for i in culprits) if culprits else "several objects together"
        out.append(
            {
                "code": "tight_walkway",
                "severity": "warning",
                "ids": [door["id"]] + culprits,
                "message": f"No {WALKWAY_MIN:.1f} m wide path from {door['kind']} {door['id']} to the middle of the room; narrowed by {names}",
            }
        )
    return out
