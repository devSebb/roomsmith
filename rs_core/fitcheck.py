"""Answers to "will it fit" questions. All numbers come from code, with units.

fits_at(scene, dims, place)   -> does a box of `dims` fit at `place`, with how much to spare
where_fits(scene, dims)       -> up to three candidate placements, ranked by clearance
passes_door(scene, dims, id)  -> conservative pass-through rule
"""

from __future__ import annotations

import math
from typing import Any

from rs_core import geometry as g
from rs_core import model as m
from rs_core import placement
from rs_core import validate
from rs_core.model import SceneError


def _probe(scene: dict, dims: list[float], name: str = "candidate") -> dict:
    return {
        "id": "__probe__",
        "name": name,
        "category": "other",
        "shape": "box",
        "dimensions_m": [float(d) for d in dims],
        "position_m": [0.0, 0.0, 0.0],
        "yaw_rad": 0.0,
        "mount": "floor",
        "color": "#000000",
        "locked": False,
        "provenance": {"class": "user_supplied", "dims_source": "stated", "confidence": 1.0},
        "product": None,
    }


def clearances(scene: dict, obj: dict, ignore_ids: set[str] | None = None) -> dict[str, Any]:
    """Free distance from each side of `obj` to the nearest wall or object.

    Sides are relative to the object's own facing: front, back, left, right.
    """
    ignore = set(ignore_ids or ())
    ignore.add(obj["id"])
    fp = m.footprint(obj)
    poly = m.outline(scene)
    others = [m.footprint(o) for o in scene["objects"] if o["id"] not in ignore and o.get("mount", "floor") == "floor" and o.get("category") != "rug"]
    yaw = float(obj.get("yaw_rad", 0.0))
    f = g.front_vector(yaw)
    r = g.right_vector(yaw)
    cx, _cy, cz = obj["position_m"]
    w, _h, d = obj["dimensions_m"]
    result = {}
    for side, direction, half in (("front", f, d / 2), ("back", (-f[0], -f[1]), d / 2), ("right", r, w / 2), ("left", (-r[0], -r[1]), w / 2)):
        origin = g.add((cx, cz), g.scale(direction, half))
        result[side] = round(_ray_clearance(origin, direction, poly, others, w if side in ("front", "back") else d, r if side in ("front", "back") else f), 3)
    return result


def _ray_clearance(origin: g.Point, direction: g.Point, poly: list[g.Point], others: list[list[g.Point]], span: float, lateral: g.Point) -> float:
    """Distance travelled along `direction` from a face of width `span` before hitting anything."""
    best = math.inf
    samples = 5
    for i in range(samples):
        t = -span / 2 + span * (i / (samples - 1)) if samples > 1 else 0.0
        p = g.add(origin, g.scale(lateral, t))
        far = g.add(p, g.scale(direction, 100.0))
        # walls
        n = len(poly)
        for k in range(n):
            a, b = poly[k], poly[(k + 1) % n]
            hit = _ray_segment(p, direction, a, b)
            if hit is not None:
                best = min(best, hit)
        # objects
        for fp in others:
            for k in range(len(fp)):
                hit = _ray_segment(p, direction, fp[k], fp[(k + 1) % len(fp)])
                if hit is not None:
                    best = min(best, hit)
        _ = far
    return 0.0 if best is math.inf else max(0.0, best)


def _ray_segment(o: g.Point, d: g.Point, a: g.Point, b: g.Point) -> float | None:
    v1 = g.sub(o, a)
    v2 = g.sub(b, a)
    v3 = (-d[1], d[0])
    denom = g.dot(v2, v3)
    if abs(denom) < 1e-12:
        return None
    t1 = g.cross(v2, v1) / denom
    t2 = g.dot(v1, v3) / denom
    if t1 >= -1e-9 and -1e-9 <= t2 <= 1 + 1e-9:
        return max(0.0, t1)
    return None


def fits_at(scene: dict, dims: list[float], place: dict, name: str = "candidate", ignore_ids: list[str] | None = None) -> dict:
    probe = _probe(scene, dims, name)
    try:
        pos, yaw, desc = placement.resolve(scene, probe, place)
    except SceneError as e:
        return {"fits": False, "reason": e.message, "error": e.to_dict()}
    probe["position_m"], probe["yaw_rad"] = pos, yaw
    trial = m.clone(scene)
    trial["objects"] = [o for o in trial["objects"] if o["id"] not in set(ignore_ids or [])]
    trial["objects"].append(probe)
    found = [i for i in validate.issues(trial, only_ids=["__probe__"]) if i["code"] != "uncalibrated"]
    blocking = [i for i in found if i["code"] in ("overlap", "outside_room")]
    clear = clearances(trial, probe, set(ignore_ids or []))
    for i in found:
        i["ids"] = [name if x == "__probe__" else x for x in i["ids"]]
        i["message"] = i["message"].replace("(__probe__)", "").replace("  ", " ")
    return {
        "fits": not blocking,
        "position_m": [round(v, 3) for v in pos],
        "yaw_rad": round(yaw, 4),
        "placement": desc,
        "clearance_m": clear,
        "issues": found,
        "verdict": _verdict(not blocking, found, clear),
    }


def _verdict(fits: bool, found: list[dict], clear: dict[str, float]) -> str:
    if not fits:
        return "Does not fit: " + "; ".join(i["message"] for i in found if i["code"] in ("overlap", "outside_room"))
    warn = [i["message"] for i in found if i["code"] not in ("overlap", "outside_room")]
    spare = min(clear.get("left", 0.0), clear.get("right", 0.0))
    s = f"Fits, with {clear.get('left', 0) * 100:.0f} cm free on the left and {clear.get('right', 0) * 100:.0f} cm on the right"
    if spare < 0.05:
        s += " (tight)"
    if warn:
        s += ". But: " + "; ".join(warn)
    return s


def where_fits(scene: dict, dims: list[float], name: str = "candidate", max_results: int = 3, step_m: float = 0.1) -> dict:
    """Candidate placements along every wall, ranked by clearance; no overlaps."""
    probe = _probe(scene, dims, name)
    w = float(dims[0])
    candidates = []
    for wall in scene["room"]["walls"]:
        L = m.wall_length(scene, wall)
        if L < w:
            continue
        t = 0.0
        best_for_wall = None
        while t + w <= L + 1e-9:
            pos, yaw, _ = placement.resolve(scene, probe, {"against_wall": wall["id"], "align": "left", "offset_m": t})
            probe["position_m"], probe["yaw_rad"] = pos, yaw
            trial = m.clone(scene)
            trial["objects"].append(dict(probe))
            found = [i for i in validate.issues(trial, only_ids=["__probe__"]) if i["code"] != "uncalibrated"]
            if not any(i["code"] in ("overlap", "outside_room", "blocks_door") for i in found):
                clear = clearances(trial, probe)
                score = min(clear["left"], clear["right"]) + 0.25 * clear["front"]
                cand = {
                    "wall_id": wall["id"],
                    "wall_label": wall.get("label", ""),
                    "offset_m": round(t, 2),
                    "position_m": [round(v, 3) for v in pos],
                    "yaw_rad": round(yaw, 4),
                    "clearance_m": clear,
                    "score": round(score, 3),
                    "warnings": [i["message"].replace("(__probe__)", "").replace("  ", " ") for i in found],
                    "place": {"against_wall": wall["id"], "align": "left", "offset_m": round(t, 2)},
                }
                if best_for_wall is None or cand["score"] > best_for_wall["score"]:
                    best_for_wall = cand
            t += step_m
        if best_for_wall:
            candidates.append(best_for_wall)
    candidates.sort(key=lambda c: -c["score"])
    top = candidates[:max_results]
    if not top:
        return {"found": 0, "candidates": [], "verdict": f"Nothing {w:.2f} m wide fits against any wall without overlapping something."}
    return {
        "found": len(candidates),
        "candidates": top,
        "verdict": f"Best spot: wall {top[0]['wall_id']} ({top[0]['wall_label'] or 'wall'}) with {min(top[0]['clearance_m']['left'], top[0]['clearance_m']['right']) * 100:.0f} cm to spare on the tighter side.",
    }


def passes_door(scene: dict, dims: list[float], opening_id: str | None = None) -> dict:
    """Conservative: the two smallest dimensions must fit inside the door's width x height."""
    doors = [o for o in scene["room"]["openings"] if o["kind"] in ("door", "opening")]
    if opening_id:
        doors = [o for o in doors if o["id"] == opening_id]
    if not doors:
        return {"passes": None, "verdict": "There is no door in this room to check against."}
    small = sorted(float(d) for d in dims)[:2]
    results = []
    for o in doors:
        dw, dh = float(o["width_m"]), float(o["height_m"])
        ok = (small[0] <= dw and small[1] <= dh) or (small[1] <= dw and small[0] <= dh)
        results.append(
            {
                "opening_id": o["id"],
                "door_m": [round(dw, 2), round(dh, 2)],
                "passes": ok,
                "margin_m": round(min(dw - small[0], dh - small[1]) if ok else max(small[0] - dw, small[1] - dh) * -1, 3),
            }
        )
    all_ok = all(r["passes"] for r in results)
    return {
        "passes": all_ok,
        "rule": "The two smallest dimensions of the object must be no larger than the door's width and height. A simple rule, not a guarantee: it ignores tilting and hallway turns.",
        "doors": results,
        "verdict": ("Passes through " + ", ".join(r["opening_id"] for r in results if r["passes"])) if all_ok else "Would not pass through " + ", ".join(r["opening_id"] for r in results if not r["passes"]),
    }
