"""Parse product dimension text into metres.

Handles the shapes retailers actually use:
    "W 180 x D 88 x H 76 cm"      "180 x 88 x 76 cm"       "180x88x76cm"
    "Width: 228 cm Depth: 93 cm Height: 83 cm"
    "71 x 35 x 30 in"              "71\" W x 35\" D x 30\" H"
    "6 ft 2 in x 3 ft"             "L 200 cm, W 90 cm, H 45 cm"
    "1800 x 880 x 760 mm"          "1,8 m x 0,88 m"   (decimal commas)
Returns a dict {width_m, height_m, depth_m, assumed_order, confidence, parsed_from}.
Unlabelled triples are read as width x depth x height (the most common
furniture convention) and flagged ``assumed_order``.
"""

from __future__ import annotations

import math
import re
from typing import Any

UNIT_TO_M = {
    "mm": 0.001,
    "millimeter": 0.001,
    "millimetre": 0.001,
    "cm": 0.01,
    "centimeter": 0.01,
    "centimetre": 0.01,
    "m": 1.0,
    "meter": 1.0,
    "metre": 1.0,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
    '"': 0.0254,
    "”": 0.0254,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
    "'": 0.3048,
    "’": 0.3048,
}

LABELS = {
    "w": "width",
    "width": "width",
    "wide": "width",
    "breite": "width",
    "ancho": "width",
    "largeur": "width",
    "d": "depth",
    "depth": "depth",
    "deep": "depth",
    "tiefe": "depth",
    "profundidad": "depth",
    "profondeur": "depth",
    "l": "length",
    "length": "length",
    "long": "length",
    "länge": "length",
    "largo": "length",
    "longueur": "length",
    "h": "height",
    "height": "height",
    "high": "height",
    "tall": "height",
    "höhe": "height",
    "alto": "height",
    "hauteur": "height",
}

_NUM = r"(?:\d+(?:[.,]\d+)?)"
_UNIT = r"(?:mm|cm|m|in|inches|inch|ft|feet|foot|\"|”|'|’|millimet(?:er|re)s?|centimet(?:er|re)s?|met(?:er|re)s?)"
_LABEL = r"(?:" + "|".join(sorted((re.escape(k) for k in LABELS), key=len, reverse=True)) + r")"

# "6 ft 2 in" / "6'2\"" compound imperial
_FT_IN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:ft|feet|foot|'|’)\s*(\d+(?:[.,]\d+)?)?\s*(?:in|inch|inches|\"|”)?", re.I)

# labelled value: "W 180 cm", "Width: 228 cm", "180 cm W", "71\" W"
# labels may be glued to their number ("W88.6\"", "180cmW"): bound them by non-letters, not \b
_PART_OF_IT = re.compile(r"\b(seat|arm|armrest|leg|legs|back|backrest|shelf|drawer|interior|inside|inner|cushion|mattress|clearance|package|packaging|box|carton|table ?top|top|base|shade|cord|cable)\s*[:\-]?\s*$")
_NOT_ITS_SIZE = re.compile(r"(fits? through|door(way)?s?|clearance|from (the )?(floor|ground)|floor to|box size|package size|shipping)\b[^.;\n]{0,24}$")
_FT_AND_IN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:ft\b|feet\b|foot\b|'|’)\s*(\d+(?:[.,]\d+)?)\s*(?:in\b|inch(?:es)?\b|\"|”)", re.I)
_LABEL_FIRST = re.compile(rf"(?<![A-Za-z])({_LABEL})(?![A-Za-z])\s*[:=]?\s*({_NUM})\s*({_UNIT})?", re.I)
_VALUE_FIRST = re.compile(rf"({_NUM})\s*({_UNIT})?\s*(?<![A-Za-z])({_LABEL})(?![A-Za-z])", re.I)
_TRIPLE = re.compile(rf"({_NUM})\s*({_UNIT})?\s*(?:x|×|\*|by)\s*({_NUM})\s*({_UNIT})?\s*(?:x|×|\*|by)\s*({_NUM})\s*({_UNIT})?", re.I)
_PAIR = re.compile(rf"({_NUM})\s*({_UNIT})?\s*(?:x|×|\*|by)\s*({_NUM})\s*({_UNIT})?", re.I)
_TRAILING_UNIT = re.compile(rf"\b({_UNIT})\b\s*$", re.I)


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def _unit_factor(unit: str | None, default: str | None) -> tuple[float | None, str | None]:
    u = (unit or default or "").strip().lower()
    if not u:
        return None, None
    if u in UNIT_TO_M:
        return UNIT_TO_M[u], u
    for k, v in UNIT_TO_M.items():
        if u.startswith(k):
            return v, k
    return None, None


def _guess_unit(values: list[float]) -> str:
    """When no unit is written: mm if values are in the hundreds-thousands,
    cm if tens-hundreds, m if small, inches if moderate and non-metric looking."""
    mx = max(values)
    if mx > 1000:
        return "mm"
    if mx > 12:
        return "cm"
    return "m"


# Categories whose "length" is the long side you lie or walk along, i.e. our depth
# (front-to-back), not the width across the front. Everything else ("L x W x H" for
# sofas, tables, sideboards) keeps L as the width across the front.
LENGTH_IS_DEPTH = frozenset({"bed", "bed_single", "bed_double", "bed_queen", "bed_king", "crib", "bathtub", "rug", "bench", "mattress"})


# Roomsmith's "width" runs along the wall the piece stands against and "depth" comes out
# into the room. Shops label these every possible way ("24 D x 42 W", "L x W x H"), so
# when the category makes the answer obvious the reading is turned to match.
WIDER_THAN_DEEP = {"sofa", "loveseat", "desk", "table_dining", "table_coffee", "bookshelf", "wardrobe", "dresser", "sideboard", "tv_stand", "tv", "bench", "counter"}
LONGER_THAN_WIDE = {"bed", "bed_single", "bed_double", "bed_queen", "bed_king", "crib", "bathtub"}
TALLEST_SIDE_IS_HEIGHT = {"lamp_floor"}


def orient_for_category(parsed: dict[str, Any] | None, category: str | None) -> dict[str, Any] | None:
    if not parsed or not category or parsed.get("partial"):
        return parsed
    w, h, d = parsed["width_m"], parsed["height_m"], parsed["depth_m"]
    note = ""
    if category in TALLEST_SIDE_IS_HEIGHT and h and h < max(w, d):
        if w >= d:
            w, h = h, w
        else:
            d, h = h, d
        note = "Took the longest side as the height (a floor lamp stands up)."
    if category in WIDER_THAN_DEEP and h and d > w * 1.3:  # clearly turned; small cube-like pieces are left as labelled
        w, d = d, w
        note = "Took the longer side as the width (along the wall) and the shorter as the depth."
    elif category in LONGER_THAN_WIDE and w > d * 1.05:
        w, d = d, w
        note = "Took the longer side as the length of the bed and the shorter as its width."
    if note:
        parsed = {**parsed, "width_m": w, "height_m": h, "depth_m": d, "reoriented": True}
        parsed["order_note"] = (parsed.get("order_note") + " " if parsed.get("order_note") else "") + note
    return parsed


_MIXED = re.compile(r"(?<![\d./])(\d+)[\s\u00a0-]+(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])")
_FRACTION = re.compile(r"(?<![\d./])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])")


def unfraction(text: str) -> str:
    """'18 7/8' -> '18.875', '3/4' -> '0.75': inch sizes are often printed as fractions."""

    def mixed(m: re.Match) -> str:
        den = int(m.group(3))
        return m.group(0) if den == 0 else f"{int(m.group(1)) + int(m.group(2)) / den:.4f}".rstrip("0").rstrip(".")

    def plain(m: re.Match) -> str:
        den = int(m.group(2))
        return m.group(0) if den == 0 or int(m.group(1)) >= den else f"{int(m.group(1)) / den:.4f}".rstrip("0").rstrip(".")

    return _FRACTION.sub(plain, _MIXED.sub(mixed, text))


def plausible(parsed: dict[str, Any] | None, category: str | None) -> bool:
    """False when a parsed size cannot belong to this category (a third of its smallest
    usual size, or over twice its largest). Unknown categories are not judged."""
    if not parsed or not category:
        return True
    from rs_core.catalog import CATALOG

    spec = CATALOG.get(category)
    if spec is None or category in ("box", "other"):
        return True
    got = (parsed.get("width_m") or 0.0, parsed.get("height_m") or 0.0, parsed.get("depth_m") or 0.0)
    for value, lo, hi in zip(got, spec.min, spec.max):
        if value and not (lo * 0.33 <= value <= hi * 2.0):
            return False
    return True


def _inches_if_that_fits_better(parsed: dict[str, Any] | None, category: str | None) -> dict[str, Any] | None:
    """Three bare numbers ("80 x 34 x 33") were read as centimetres. When the category is
    known and the same numbers as inches sit much closer to its usual size, they are inches."""
    if not parsed or parsed.get("guessed_unit") != "cm" or not category or parsed.get("partial"):
        return parsed
    from rs_core.catalog import CATALOG

    spec = CATALOG.get(category)
    if spec is None or category in ("box", "other"):
        return parsed
    keys = ("width_m", "height_m", "depth_m")

    def distance(scale: float) -> float:
        return sum(abs(math.log(parsed[k] * scale / usual)) for k, usual in zip(keys, spec.default) if parsed[k] > 0 and usual > 0)

    if distance(2.54) + 0.5 < distance(1.0):
        parsed = {**parsed, **{k: parsed[k] * 2.54 for k in keys}, "guessed_unit": "in"}
        parsed["order_note"] = (parsed.get("order_note") + " " if parsed.get("order_note") else "") + "No unit was printed: read as inches, which fits this kind of piece."
    return parsed


def parse_dimensions(text: str | None, default_unit: str | None = None, category: str | None = None) -> dict[str, Any] | None:
    """Read printed dimensions and turn them to Roomsmith's width/height/depth."""
    parsed = _parse_dimensions(unfraction(text) if text else text, default_unit, category)
    return orient_for_category(_inches_if_that_fits_better(parsed, category), category)


def _parse_dimensions(text: str | None, default_unit: str | None = None, category: str | None = None) -> dict[str, Any] | None:
    """Return parsed dimensions or None when nothing usable is found."""
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    s = raw.replace("×", "x").replace("＊", "*")
    s = re.sub(r"(\d)\s*(?:''|’’|″|\u201d)", r'\1"', s)  # two apostrophes are an inch mark, not feet
    s = re.sub(r"\b(in|ft|cm|mm|inch|inches)\.(?=\s|$)", r"\1", s, flags=re.I)  # "58 in. W"
    s = re.sub(r"\(\s*([WDHL])\s*\)", r" \1 ", s, flags=re.I)  # "180 cm (L)"
    # "4 ft 10.5 in", 5'3": one length written in two units becomes one number, before anything is split on "x"
    s = _FT_AND_IN.sub(lambda m: f"{_to_float(m.group(1)) * 0.3048 + _to_float(m.group(2)) * 0.0254:.4f} m", s)
    s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)  # 1,800 -> 1800 (thousands separators)
    labelled: dict[str, float] = {}
    unit_seen: str | None = None

    # trailing unit applies to all values ("180 x 88 x 76 cm")
    m_tr = _TRAILING_UNIT.search(s)
    trailing_unit = m_tr.group(1) if m_tr else None

    # compound imperial first ("6 ft 2 in")
    comp = []
    for mt in _FT_IN.finditer(s):
        ft = _to_float(mt.group(1))
        inch = _to_float(mt.group(2)) if mt.group(2) else 0.0
        comp.append(ft * 0.3048 + inch * 0.0254)

    # labelled values first; a unit printed on one of them ("W 27.5 x D 27.5 x H 34.5 inches")
    # is the unit of the ones printed without, before any guess from the numbers
    # "Seat height 18 in", "Arm height 25 in", "fits through doors 30 in wide" measure a part or a doorway,
    # not the piece: they are skipped. "Overall height" outranks a bare "Height".
    found: list[tuple[int, str, float, str | None]] = []
    for kind, pattern in (("label", _LABEL_FIRST), ("value", _VALUE_FIRST)):
        for mt in pattern.finditer(s):
            before = s[max(0, mt.start() - 26): mt.start()].lower()
            if _PART_OF_IT.search(before) or _NOT_ITS_SIZE.search(s[max(0, mt.start() - 40): mt.start()].lower()):
                continue
            label, val, unit = (LABELS[mt.group(1).lower()], _to_float(mt.group(2)), mt.group(3)) if kind == "label" else (LABELS[mt.group(3).lower()], _to_float(mt.group(1)), mt.group(2))
            found.append((0 if "overall" in before or "total" in before else 1, label, val, unit))
    found.sort(key=lambda f: f[0])  # stable: overall values first, otherwise the order they were found in
    # label-first matches keep priority over value-first ones ("Width: 228 cm Depth: 93 cm" must not read 228 as the depth)
    shared = trailing_unit or default_unit or next((u for _, _, _, u in found if _unit_factor(u, None)[0] is not None), None)
    for _, label, val, unit in found:
        factor, u = _unit_factor(unit, shared)
        if factor is None:
            factor = UNIT_TO_M[_guess_unit([val])]
        else:
            unit_seen = u
        labelled.setdefault(label, val * factor)

    if labelled:
        # "L x W x H" listings (sofas, tables, rugs): L is the long side across the
        # front, W is front-to-back. With only W, D, H: the usual meaning.
        if "length" in labelled and "width" in labelled and "depth" not in labelled:
            if (category or "") in LENGTH_IS_DEPTH:
                width, depth = labelled["width"], labelled["length"]  # bed: W is the headboard side, L the length
            else:
                width, depth = labelled["length"], labelled["width"]  # sofa/table: L runs across the front
        else:
            width = labelled.get("width", labelled.get("length"))
            depth = labelled.get("depth")
            if depth is None and "length" in labelled and "width" not in labelled:
                depth = None
        height = labelled.get("height")
        if width is not None and depth is not None and height is not None:
            return _result(width, height, depth, raw, assumed_order=False, confidence=0.95)
        if width is not None and (depth is not None or height is not None):
            out = _result(width, height if height is not None else 0.0, depth if depth is not None else 0.0, raw, assumed_order=False, confidence=0.7)
            out["partial"] = True
            out["missing"] = [k for k, v in (("height_m", height), ("depth_m", depth)) if v is None]
            return out

    mt = _TRIPLE.search(s)
    if mt:
        nums = [_to_float(mt.group(i)) for i in (1, 3, 5)]
        units = [mt.group(i) for i in (2, 4, 6)]
        last_unit = next((u for u in reversed(units) if u), None) or trailing_unit or default_unit
        vals = []
        guessed = None
        for v, u in zip(nums, units):
            factor, _ = _unit_factor(u or last_unit, None)
            if factor is None:
                guessed = _guess_unit(nums)
                factor = UNIT_TO_M[guessed]
            vals.append(v * factor)
        # unlabelled: assume W x D x H
        out = _result(vals[0], vals[2], vals[1], raw, assumed_order=True, confidence=0.6)
        if guessed:
            out["guessed_unit"] = guessed
        return out

    if len(comp) >= 3:
        return _result(comp[0], comp[2], comp[1], raw, assumed_order=True, confidence=0.55)

    mt = _PAIR.search(s)
    if mt:
        nums = [_to_float(mt.group(1)), _to_float(mt.group(3))]
        units = [mt.group(2), mt.group(4)]
        last_unit = next((u for u in reversed(units) if u), None) or trailing_unit or default_unit
        vals = []
        for v, u in zip(nums, units):
            factor, _ = _unit_factor(u or last_unit, None)
            if factor is None:
                factor = UNIT_TO_M[_guess_unit(nums)]
            vals.append(v * factor)
        out = _result(vals[0], 0.0, vals[1], raw, assumed_order=True, confidence=0.4)
        out["partial"] = True
        out["missing"] = ["height_m"]
        return out

    if len(comp) == 2:
        out = _result(comp[0], 0.0, comp[1], raw, assumed_order=True, confidence=0.4)
        out["partial"] = True
        out["missing"] = ["height_m"]
        return out
    _ = unit_seen
    return None


def _result(width: float, height: float, depth: float, raw: str, assumed_order: bool, confidence: float) -> dict[str, Any]:
    return {
        "width_m": round(width, 4),
        "height_m": round(height, 4),
        "depth_m": round(depth, 4),
        "assumed_order": assumed_order,
        "order_note": "Read as width x depth x height; say so if the listing uses another order." if assumed_order else "",
        "confidence": confidence,
        "parsed_from": raw,
    }


_LENGTH_WITH_UNIT = re.compile(r"(?<![\d.])(\d+(?:[.,]\d+)?)\s*(cm|mm|inches|inch|in|ft|m|\"|\u201d|\u2033)(?![a-z])", re.I)


def length_with_unit(text: str | None) -> float | None:
    """The last length in a text that carries its own unit ('… dark red 72 "' -> 1.83), in metres.
    Numbers without a unit (a model year, a product number) are never taken."""
    if not text or not isinstance(text, str):
        return None
    found = _LENGTH_WITH_UNIT.findall(unfraction(text))
    if not found:
        return None
    value, unit = found[-1]
    factor, _ = _unit_factor(unit, None)
    return _to_float(value) * factor if factor else None


def parse_length(text: str | None, default_unit: str | None = None) -> float | None:
    """One length ("4.2 m", "14 ft", "6'2\"", "250cm") -> metres."""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    mt = _FT_IN.search(s)
    if mt and (mt.group(2) or re.search(r"ft|feet|foot|'|’", s, re.I)):
        return _to_float(mt.group(1)) * 0.3048 + (_to_float(mt.group(2)) if mt.group(2) else 0.0) * 0.0254
    mt = re.search(rf"({_NUM})\s*({_UNIT})?", s, re.I)
    if not mt:
        return None
    val = _to_float(mt.group(1))
    factor, _ = _unit_factor(mt.group(2), default_unit)
    if factor is None:
        factor = UNIT_TO_M[_guess_unit([val])]
    return val * factor
