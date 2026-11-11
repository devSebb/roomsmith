"""Relational placement: turn a ``place`` instruction into a position and yaw.

Models are poor at coordinates and good at relations, so ``add_object`` and
``move_object`` accept any of:

    {"against_wall": "w3", "align": "center"|"left"|"right", "offset_m": 0.3, "gap_m": 0.02}
    {"next_to": "ob2", "side": "left"|"right"|"front"|"behind", "gap_m": 0.1}
    {"in_corner": ["w1", "w2"], "gap_m": 0.02}
    {"centered_in_room": true}
    {"by": [dx, dz]}
    {"position_m": [x, y, z]}  and/or  {"yaw_rad": r}

Conventions
- "left"/"right" on a wall are as seen from inside the room facing that wall:
  "left" is the wall's start vertex (a), "right" its end vertex (b).
- "left"/"right"/"front"/"behind" of an object are relative to that object's
  own facing direction.
- Everything returned is in metres and radians; the object's y stays as given.
"""

from __future__ import annotations

import math

from typing import Any

from rs_core import geometry as g
from rs_core import model as m
from rs_core.model import SceneError

DEFAULT_GAP = 0.02


def resolve(scene: dict, obj: dict, place: dict[str, Any]) -> tuple[list[float], float, str]:
    """Return (position_m, yaw_rad, description) for `obj` placed per `place`.

    `obj` must already carry dimensions and (for relative moves) a position.
    Raises SceneError on unknown ids or malformed instructions.
    """
    if not isinstance(place, dict):
        raise SceneError("invalid_value", "place must be an object", field="place")

    w, _h, d = (float(v) for v in obj["dimensions_m"])
    x, y, z = (float(v) for v in obj.get("position_m", [0.0, 0.0, 0.0]))
    yaw = float(obj.get("yaw_rad", 0.0))
    gap = _float(place.get("gap_m", DEFAULT_GAP), "gap_m")
    desc = ""

    if "against_wall" in place:
        wall = m.find_wall(scene, str(place["against_wall"]))
        a, b = m.wall_segment(scene, wall)
        n = g.inward_normal(a, b)
        dirv = g.normalize(g.sub(b, a))
        L = g.distance(a, b)
        align = str(place.get("align", "center")).lower()
        offset = _float(place.get("offset_m", 0.0), "offset_m")
        if align == "left":
            t = w / 2.0 + offset
        elif align == "right":
            t = L - w / 2.0 - offset
        elif align == "center":
            t = L / 2.0 + offset
        else:
            raise SceneError("invalid_value", "align must be left, center or right", field="align")
        t = max(w / 2.0, min(L - w / 2.0, t)) if L >= w else L / 2.0
        along = g.add(a, g.scale(dirv, t))
        center = g.add(along, g.scale(n, d / 2.0 + gap))
        x, z = center
        yaw = g.yaw_facing(n)
        desc = f"against wall {wall['id']} ({wall.get('label') or 'wall'}), {align}"

    elif "next_to" in place:
        ref = m.find_object(scene, str(place["next_to"]))
        if ref["id"] == obj.get("id"):
            raise SceneError("invalid_value", "An object cannot be placed next to itself", field="next_to")
        side = str(place.get("side", "right")).lower()
        rw, _rh, rd = (float(v) for v in ref["dimensions_m"])
        rx, _ry, rz = (float(v) for v in ref["position_m"])
        ryaw = float(ref.get("yaw_rad", 0.0))
        f = g.front_vector(ryaw)
        r = g.right_vector(ryaw)
        if side == "right":
            off = g.scale(r, rw / 2.0 + w / 2.0 + gap)
        elif side == "left":
            off = g.scale(r, -(rw / 2.0 + w / 2.0 + gap))
        elif side == "front":
            off = g.scale(f, rd / 2.0 + d / 2.0 + gap)
        elif side == "behind":
            off = g.scale(f, -(rd / 2.0 + d / 2.0 + gap))
        else:
            raise SceneError("invalid_value", "side must be left, right, front or behind", field="side")
        x, z = g.add((rx, rz), off)
        # in front of something you face it (a chair at a desk, an armchair at a sofa); beside or behind it you face its way
        yaw = ryaw + math.pi if side == "front" else ryaw
        desc = f"{side} of {ref['name']} ({ref['id']})" + (", facing it" if side == "front" else "")

    elif "in_corner" in place:
        pair = place["in_corner"]
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise SceneError("invalid_value", "in_corner needs two wall ids", field="in_corner")
        wa = m.find_wall(scene, str(pair[0]))
        wb = m.find_wall(scene, str(pair[1]))
        shared = _shared_vertex(wa, wb)
        if shared is None:
            raise SceneError("invalid_value", f"Walls {wa['id']} and {wb['id']} do not meet", field="in_corner")
        corner = m.find_vertex(scene, shared)
        cpt = (float(corner["x"]), float(corner["z"]))
        a, b = m.wall_segment(scene, wa)
        na = g.inward_normal(a, b)
        # along wall a, away from the corner
        away = g.normalize(g.sub(b, a)) if shared == wa["a"] else g.normalize(g.sub(a, b))
        # the corner sits at the end of wall b, so the side gap is along `away`
        center = g.add(cpt, g.add(g.scale(na, d / 2.0 + gap), g.scale(away, w / 2.0 + gap)))
        x, z = center
        yaw = g.yaw_facing(na)
        desc = f"in the corner of walls {wa['id']} and {wb['id']}, back to {wa['id']}"

    elif place.get("centered_in_room"):
        x, z = g.centroid(m.outline(scene))
        desc = "centred in the room"

    elif "on" in place:
        host = m.find_object(scene, str(place["on"]))
        if host["id"] == obj.get("id"):
            raise SceneError("invalid_value", "An object cannot be placed on itself", field="on")
        x, z = float(host["position_m"][0]), float(host["position_m"][2])
        yaw = float(host.get("yaw_rad", 0.0))
        desc = f"on {host['name']} ({host['id']})"

    elif "by" in place:
        delta = place["by"]
        if not isinstance(delta, (list, tuple)) or len(delta) != 2:
            raise SceneError("invalid_value", "by needs [dx, dz]", field="by")
        dx, dz = _float(delta[0], "by"), _float(delta[1], "by")
        x, z = x + dx, z + dz
        desc = f"nudged by ({dx:+.2f}, {dz:+.2f}) m"

    if "position_m" in place:
        pos = place["position_m"]
        if not isinstance(pos, (list, tuple)) or len(pos) not in (2, 3):
            raise SceneError("invalid_value", "position_m needs [x, y, z]", field="position_m")
        if len(pos) == 2:
            x, z = _float(pos[0], "position_m"), _float(pos[1], "position_m")
        else:
            x, y, z = (_float(v, "position_m") for v in pos)
        desc = desc or f"at ({x:.2f}, {z:.2f}) m"

    if "yaw_rad" in place:
        yaw = _float(place["yaw_rad"], "yaw_rad")
        desc = desc or "rotated"
    elif "yaw_deg" in place:
        yaw = _float(place["yaw_deg"], "yaw_deg") * 3.141592653589793 / 180.0
        desc = desc or "rotated"
    elif "facing" in place:
        yaw = facing_yaw(scene, str(place["facing"]))
        desc = desc or f"facing {place['facing']}"

    # "on": rest on top of a host object (y = host top), combinable with any of the above
    if "on" in place:
        host = m.find_object(scene, str(place["on"]))
        y = m.object_top(host)
        if "on " not in desc:
            desc = f"{desc}, on {host['name']} ({host['id']})"

    if not desc:
        raise SceneError(
            "invalid_value",
            "place needs one of against_wall, next_to, in_corner, centered_in_room, on, by, position_m, yaw_rad, facing",
            field="place",
        )
    return [x, y, z], g.normalize_yaw(yaw), desc


def facing_yaw(scene: dict, target: str) -> float:
    """Yaw so the object faces a wall (by id or label) or an object (by id)."""
    key = target.strip()
    walls = m.wall_map(scene)
    wall = walls.get(key) or m._find_wall_by_label(scene, key)  # noqa: SLF001 (same package)
    if wall is not None:
        n = m.wall_inward_normal(scene, wall)
        # face the wall = face against its inward normal
        return g.yaw_facing((-n[0], -n[1]))
    raise SceneError("unknown_id", f"Cannot face {target!r}: not a wall id or label", id=target)


def _shared_vertex(wa: dict, wb: dict) -> str | None:
    for v in (wa["a"], wa["b"]):
        if v in (wb["a"], wb["b"]):
            return v
    return None


def _float(v: Any, field: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SceneError("invalid_value", f"{field} must be a number", field=field)
    f = float(v)
    if not g.is_finite(f):
        raise SceneError("invalid_value", f"{field} must be finite", field=field)
    return f
