"""Compact descriptions of a scene for the agent and for export."""

from __future__ import annotations

import math

from rs_core import geometry as g
from rs_core import model as m
from rs_core import money


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _cm(v: float) -> str:
    return f"{v * 100:.0f} cm"


def wall_facts(scene: dict) -> list[dict]:
    out = []
    for w in scene["room"]["walls"]:
        a, b = m.wall_segment(scene, w)
        out.append(
            {
                "id": w["id"],
                "label": w.get("label", ""),
                "length_m": round(g.distance(a, b), 3),
                "from": [round(a[0], 3), round(a[1], 3)],
                "to": [round(b[0], 3), round(b[1], 3)],
                "color": w.get("color"),
                "openings": [o["id"] for o in scene["room"]["openings"] if o["wall_id"] == w["id"]],
            }
        )
    return out


def opening_facts(scene: dict) -> list[dict]:
    out = []
    for o in scene["room"]["openings"]:
        d = {
            "id": o["id"],
            "kind": o["kind"],
            "wall_id": o["wall_id"],
            "offset_m": round(float(o["offset_m"]), 3),
            "width_m": round(float(o["width_m"]), 3),
            "height_m": round(float(o["height_m"]), 3),
            "sill_m": round(float(o["sill_m"]), 3),
        }
        if o["kind"] == "door":
            d["swing"] = o.get("swing", "in")
            d["hinge"] = o.get("hinge", "left")
        out.append(d)
    return out


def nearest_wall(scene: dict, obj: dict) -> tuple[str, float] | None:
    fp = m.footprint(obj)
    best = None
    for w in scene["room"]["walls"]:
        a, b = m.wall_segment(scene, w)
        dist = min(g.point_segment_distance(c, a, b) for c in fp)
        if best is None or dist < best[1]:
            best = (w["id"], dist)
    return best


def object_facts(scene: dict, obj: dict) -> dict:
    w, h, d = obj["dimensions_m"]
    x, y, z = obj["position_m"]
    nw = nearest_wall(scene, obj)
    facts = {
        "id": obj["id"],
        "name": obj["name"],
        "category": obj.get("category", "other"),
        "dimensions_m": [round(w, 3), round(h, 3), round(d, 3)],
        "position_m": [round(x, 3), round(y, 3), round(z, 3)],
        "yaw_deg": round(math.degrees(float(obj.get("yaw_rad", 0.0))), 1),
        "mount": obj.get("mount", "floor"),
        "locked": bool(obj.get("locked")),
        "dims_source": (obj.get("provenance") or {}).get("dims_source", "estimated"),
    }
    if nw:
        facts["nearest_wall"] = {"id": nw[0], "distance_m": round(nw[1], 3)}
    if obj.get("product"):
        p = obj["product"]
        facts["product"] = {k: p.get(k) for k in ("title", "url", "price") if p.get(k)}
    return facts


def object_line(scene: dict, obj: dict) -> str:
    w, h, d = obj["dimensions_m"]
    x, _y, z = obj["position_m"]
    nw = nearest_wall(scene, obj)
    where = f"near wall {nw[0]} ({_cm(nw[1])} away)" if nw else ""
    yaw = math.degrees(float(obj.get("yaw_rad", 0.0)))
    src = (obj.get("provenance") or {}).get("dims_source", "estimated")
    flags = []
    if src == "estimated":
        flags.append("est.")
    if obj.get("locked"):
        flags.append("locked")
    if obj.get("product"):
        flags.append("product")
    fl = f" [{', '.join(flags)}]" if flags else ""
    return f"{obj['id']}: {obj['name']} — {_f(w)} x {_f(h)} x {_f(d)} m (w x h x d), at ({_f(x)}, {_f(z)}), facing {yaw:.0f}°, {where}{fl}"


def summary_text(scene: dict, issues: list[dict] | None = None, revision: int | None = None) -> str:
    room = scene["room"]
    rw, rd = m.room_size(scene)
    area = g.polygon_area(m.outline(scene))
    cal = scene.get("calibration", {}).get("status", "uncalibrated")
    lines = [
        f"Room '{scene['project']['name']}'" + (f" (revision {revision})" if revision is not None else "") + f": {_f(rw)} x {_f(rd)} m footprint, {_f(area)} m², ceiling {_f(float(room['height_m']))} m, {cal}.",
    ]
    if not m.is_rectangle(scene):
        lines[0] += f" Outline has {len(room['vertices'])} corners (not a rectangle)."
    budget = money.budget_status(scene)
    if budget:
        lines.append(budget["text"] + ".")
    lines.append("Walls: " + "; ".join(f"{w['id']} ({w.get('label') or 'wall'}) {_f(m.wall_length(scene, w))} m" for w in room["walls"]))
    if room["openings"]:
        lines.append(
            "Openings: "
            + "; ".join(
                f"{o['id']} {o['kind']} on {o['wall_id']}, {_f(float(o['width_m']))} m wide x {_f(float(o['height_m']))} m, {_f(float(o['offset_m']))} m from the wall's start"
                + (f", sill {_f(float(o['sill_m']))} m" if o["kind"] == "window" else "")
                for o in room["openings"]
            )
        )
    else:
        lines.append("Openings: none yet.")
    if scene["objects"]:
        lines.append(f"Objects ({len(scene['objects'])}):")
        for obj in scene["objects"]:
            lines.append("  " + object_line(scene, obj))
    else:
        lines.append("Objects: none yet.")
    if issues:
        real = [i for i in issues if i["code"] != "uncalibrated"]
        if real:
            lines.append(f"Issues ({len(real)}):")
            for i in real:
                lines.append(f"  - {i['code']}: {i['message']}")
        else:
            lines.append("Issues: none.")
    lines.append("Conventions: metres; x runs along the back wall (w1) from its start, z runs from the back wall toward the front wall; yaw 0° faces the back wall, 180° faces the front wall; left/right on a wall are as seen from inside facing it.")
    return "\n".join(lines)


def compact(scene: dict, issues: list[dict] | None = None, revision: int | None = None) -> dict:
    rw, rd = m.room_size(scene)
    budget = money.budget_status(scene)
    return {
        **({"budget": budget} if budget else {}),
        "project": scene["project"],
        "revision": revision,
        "calibration": scene.get("calibration"),
        "room": {
            "width_m": round(rw, 3),
            "depth_m": round(rd, 3),
            "height_m": round(float(scene["room"]["height_m"]), 3),
            "area_m2": round(g.polygon_area(m.outline(scene)), 3),
            "is_rectangle": m.is_rectangle(scene),
            "vertices": [{"id": v["id"], "x": round(float(v["x"]), 3), "z": round(float(v["z"]), 3)} for v in scene["room"]["vertices"]],
            "walls": wall_facts(scene),
            "openings": opening_facts(scene),
            "floor_color": scene["room"]["floor"]["color"],
        },
        "objects": [object_facts(scene, o) for o in scene["objects"]],
        "issues": issues or [],
        "text": summary_text(scene, issues, revision),
    }


def shopping_list(scene: dict) -> str:
    """Everything in the room with sizes; products with price and link; totals when priced."""
    budget = scene.get("budget") if isinstance(scene.get("budget"), dict) else {}
    cur = money.currency_code(budget.get("currency"))
    lines = [f"Roomsmith — {scene['project']['name']}", ""]
    totals: dict[str | None, int] = {}
    unpriced = 0
    for obj in scene["objects"]:
        w, h, d = obj["dimensions_m"]
        line = f"- {obj['name']}: {_f(w)} x {_f(h)} x {_f(d)} m (w x h x d)"
        p = obj.get("product") or {}
        if p.get("title") and p["title"] != obj["name"]:
            line += f" — {p['title']}"
        price = money.product_price(p) if p else None
        if price:
            line += f", {money.format_money(price[0], price[1] or cur)}"
            totals[price[1] or cur] = totals.get(price[1] or cur, 0) + round(price[0] * 100)
        elif p:
            line += ", price not known"
            unpriced += 1
        if p.get("url"):
            line += f"\n  {p['url']}"
        lines.append(line)
    if totals:
        lines.append("")
        for c, cents in totals.items():
            lines.append(f"Total: {money.format_money(cents / 100, c)}")
        if unpriced:
            lines.append(f"({unpriced} product(s) without a known price are not in the total.)")
    status = money.budget_status(scene)
    if status:
        lines.append(status["text"])
    if totals:
        lines.append("Prices as read from the product pages; they can change.")
    return "\n".join(lines)
