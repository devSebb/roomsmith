"""Typical sizes per furniture category.

Used to clamp model estimates to plausible ranges, to fill defaults when the
agent adds an object by category only, and to pick a sensible colour.
All sizes are (width, height, depth) in metres: width across the front,
depth front-to-back.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategorySpec:
    default: tuple[float, float, float]
    min: tuple[float, float, float]
    max: tuple[float, float, float]
    color: str
    shape: str = "box"
    mount: str = "floor"
    against_wall_typical: bool = False


_C = CategorySpec

CATALOG: dict[str, CategorySpec] = {
    "sofa": _C((2.0, 0.85, 0.9), (1.2, 0.6, 0.7), (4.0, 1.1, 1.3), "#6b7a8f", against_wall_typical=True),
    "loveseat": _C((1.5, 0.85, 0.9), (1.2, 0.6, 0.7), (1.9, 1.1, 1.2), "#6b7a8f", against_wall_typical=True),
    "armchair": _C((0.9, 0.85, 0.9), (0.6, 0.6, 0.6), (1.3, 1.2, 1.2), "#7a6b8f"),
    "chair": _C((0.45, 0.9, 0.5), (0.35, 0.7, 0.35), (0.7, 1.2, 0.7), "#8f7a6b"),
    "stool": _C((0.4, 0.7, 0.4), (0.3, 0.4, 0.3), (0.6, 0.9, 0.6), "#8f7a6b"),
    "bench": _C((1.2, 0.45, 0.4), (0.8, 0.35, 0.3), (2.5, 0.6, 0.6), "#8f7a6b"),
    "bed_single": _C((1.0, 0.5, 2.0), (0.8, 0.3, 1.8), (1.2, 1.2, 2.2), "#8fa3b8", against_wall_typical=True),
    "bed_double": _C((1.4, 0.5, 2.0), (1.3, 0.3, 1.8), (1.6, 1.2, 2.2), "#8fa3b8", against_wall_typical=True),
    "bed_queen": _C((1.6, 0.5, 2.0), (1.5, 0.3, 1.9), (1.7, 1.2, 2.2), "#8fa3b8", against_wall_typical=True),
    "bed_king": _C((1.8, 0.5, 2.0), (1.7, 0.3, 1.9), (2.2, 1.2, 2.2), "#8fa3b8", against_wall_typical=True),
    "bed": _C((1.5, 0.5, 2.0), (0.8, 0.3, 1.8), (2.2, 1.2, 2.2), "#8fa3b8", against_wall_typical=True),
    "nightstand": _C((0.45, 0.55, 0.4), (0.3, 0.4, 0.3), (0.7, 0.8, 0.6), "#a08a6e"),
    "desk": _C((1.4, 0.75, 0.7), (0.8, 0.65, 0.4), (2.4, 0.85, 1.0), "#a08a6e", against_wall_typical=True),
    "table_dining": _C((1.6, 0.75, 0.9), (0.8, 0.65, 0.7), (3.0, 0.8, 1.3), "#a08a6e"),
    "table_coffee": _C((1.1, 0.42, 0.6), (0.5, 0.3, 0.4), (1.6, 0.55, 1.0), "#a08a6e"),
    "table_side": _C((0.5, 0.55, 0.5), (0.3, 0.4, 0.3), (0.7, 0.75, 0.7), "#a08a6e"),
    "table": _C((1.2, 0.75, 0.8), (0.4, 0.3, 0.4), (3.0, 1.0, 1.5), "#a08a6e"),
    "bookshelf": _C((0.8, 2.0, 0.3), (0.4, 0.8, 0.2), (2.4, 2.6, 0.5), "#8a6e50", against_wall_typical=True),
    "shelf": _C((0.8, 1.2, 0.3), (0.3, 0.2, 0.15), (2.4, 2.6, 0.6), "#8a6e50", against_wall_typical=True),
    "wardrobe": _C((1.5, 2.1, 0.6), (0.5, 1.5, 0.4), (3.0, 2.6, 0.8), "#8a6e50", against_wall_typical=True),
    "dresser": _C((1.2, 0.8, 0.5), (0.6, 0.6, 0.35), (2.0, 1.3, 0.7), "#8a6e50", against_wall_typical=True),
    "cabinet": _C((0.9, 0.9, 0.45), (0.3, 0.3, 0.25), (3.0, 2.6, 0.8), "#8a6e50", against_wall_typical=True),
    "sideboard": _C((1.6, 0.8, 0.45), (0.8, 0.5, 0.35), (2.6, 1.1, 0.6), "#8a6e50", against_wall_typical=True),
    "tv_stand": _C((1.6, 0.5, 0.4), (0.8, 0.3, 0.3), (2.6, 0.8, 0.6), "#55595e", against_wall_typical=True),
    "tv": _C((1.2, 0.7, 0.08), (0.5, 0.3, 0.03), (2.2, 1.3, 0.2), "#1f2124", mount="surface"),
    "rug": _C((2.0, 0.01, 1.4), (0.6, 0.005, 0.6), (5.0, 0.03, 4.0), "#b58c6a"),
    "plant": _C((0.5, 1.2, 0.5), (0.2, 0.3, 0.2), (1.2, 2.5, 1.2), "#4f7a4a", shape="cylinder"),
    "lamp_floor": _C((0.35, 1.6, 0.35), (0.2, 1.2, 0.2), (0.6, 2.0, 0.6), "#d9c89a", shape="cylinder"),
    "lamp_table": _C((0.3, 0.5, 0.3), (0.15, 0.25, 0.15), (0.5, 0.8, 0.5), "#d9c89a", shape="cylinder", mount="surface"),
    "lamp_ceiling": _C((0.5, 0.4, 0.5), (0.1, 0.05, 0.1), (2.0, 1.2, 2.0), "#2b2b2b", mount="ceiling"),
    "mirror": _C((0.6, 1.6, 0.04), (0.3, 0.4, 0.02), (1.5, 2.2, 0.1), "#b8c4cc", mount="wall"),
    "picture": _C((0.6, 0.45, 0.03), (0.15, 0.15, 0.01), (2.0, 1.5, 0.1), "#c7a07a", mount="wall"),
    "fridge": _C((0.7, 1.8, 0.7), (0.5, 0.8, 0.5), (1.0, 2.1, 0.8), "#c9ccd1", against_wall_typical=True),
    "oven": _C((0.6, 0.9, 0.6), (0.5, 0.6, 0.5), (0.9, 1.0, 0.7), "#55595e", against_wall_typical=True),
    "counter": _C((1.8, 0.9, 0.6), (0.4, 0.85, 0.5), (4.0, 0.95, 0.7), "#d5cfc3", against_wall_typical=True),
    "sink": _C((0.6, 0.9, 0.6), (0.4, 0.8, 0.4), (1.2, 1.0, 0.7), "#d5cfc3", against_wall_typical=True),
    "washing_machine": _C((0.6, 0.85, 0.6), (0.5, 0.8, 0.5), (0.7, 1.0, 0.7), "#c9ccd1", against_wall_typical=True),
    "toilet": _C((0.4, 0.8, 0.7), (0.35, 0.6, 0.6), (0.5, 0.9, 0.8), "#eceff1", against_wall_typical=True),
    "bathtub": _C((1.7, 0.6, 0.75), (1.4, 0.5, 0.7), (2.0, 0.7, 1.0), "#eceff1", against_wall_typical=True),
    "shower": _C((0.9, 2.0, 0.9), (0.7, 1.8, 0.7), (1.4, 2.3, 1.4), "#dde6ea", against_wall_typical=True),
    "piano": _C((1.5, 1.2, 0.6), (1.4, 0.9, 0.5), (1.6, 1.3, 0.7), "#2b2b2b", against_wall_typical=True),
    "crib": _C((0.7, 0.9, 1.3), (0.6, 0.8, 1.2), (0.8, 1.0, 1.4), "#d9c89a"),
    "ottoman": _C((0.6, 0.45, 0.6), (0.4, 0.3, 0.4), (1.2, 0.5, 1.2), "#7a6b8f"),
    "box": _C((0.5, 0.5, 0.5), (0.01, 0.01, 0.01), (20.0, 20.0, 20.0), "#9aa0a6"),
    "other": _C((0.6, 0.8, 0.6), (0.01, 0.01, 0.01), (20.0, 20.0, 20.0), "#9aa0a6"),
}

ALIASES = {
    "couch": "sofa",
    "settee": "sofa",
    "sectional": "sofa",
    "lounge chair": "armchair",
    "recliner": "armchair",
    "office chair": "chair",
    "dining chair": "chair",
    "single bed": "bed_single",
    "twin bed": "bed_single",
    "double bed": "bed_double",
    "full bed": "bed_double",
    "queen bed": "bed_queen",
    "king bed": "bed_king",
    "bedside table": "nightstand",
    "night stand": "nightstand",
    "dining table": "table_dining",
    "coffee table": "table_coffee",
    "side table": "table_side",
    "end table": "table_side",
    "bookcase": "bookshelf",
    "shelves": "shelf",
    "shelving": "shelf",
    "closet": "wardrobe",
    "armoire": "wardrobe",
    "chest of drawers": "dresser",
    "drawers": "dresser",
    "tv unit": "tv_stand",
    "media console": "tv_stand",
    "television": "tv",
    "carpet": "rug",
    "floor lamp": "lamp_floor",
    "table lamp": "lamp_table",
    "ceiling light": "lamp_ceiling",
    "ceiling lamp": "lamp_ceiling",
    "pendant": "lamp_ceiling",
    "pendant light": "lamp_ceiling",
    "chandelier": "lamp_ceiling",
    "light fixture": "lamp_ceiling",
    "hanging light": "lamp_ceiling",
    "ceiling fan": "lamp_ceiling",
    "fan": "lamp_ceiling",
    "refrigerator": "fridge",
    "stove": "oven",
    "cooker": "oven",
    "countertop": "counter",
    "kitchen counter": "counter",
    "worktop": "counter",
    "washer": "washing_machine",
    "bath": "bathtub",
    "tub": "bathtub",
    "pouf": "ottoman",
    "footstool": "ottoman",
    "painting": "picture",
    "artwork": "picture",
    "frame": "picture",
}


# Phrases in a product's name that say what it is, longest first. A product title is
# often all the caller has ("SONGMICS HOME Area Rug, 5x7 ft", "TARVA Bed frame - pine Queen").
PHRASES = {
    "tv stand": "tv_stand", "tv console": "tv_stand", "tv cabinet": "tv_stand", "media stand": "tv_stand", "entertainment center": "tv_stand",
    "area rug": "rug", "wall art": "picture", "art print": "picture", "canvas print": "picture", "framed print": "picture", "poster": "picture",
    "floor mirror": "mirror", "wall mirror": "mirror", "book shelf": "bookshelf", "ladder shelf": "bookshelf", "ladder bookshelf": "bookshelf",
    "storage organizer": "bookshelf", "cube organizer": "bookshelf", "cube storage": "bookshelf",
    "desk chair": "chair", "task chair": "chair", "accent chair": "armchair", "arm chair": "armchair", "club chair": "armchair", "wingback": "armchair",
    "bar stool": "stool", "counter stool": "stool", "storage bench": "bench", "nesting table": "table_coffee", "console table": "table_side",
    "writing desk": "desk", "standing desk": "desk", "computer desk": "desk", "uplighter": "lamp_floor", "torchiere": "lamp_floor",
    "floor uplighter": "lamp_floor", "arc lamp": "lamp_floor", "tripod lamp": "lamp_floor", "desk lamp": "lamp_table", "bedside lamp": "lamp_table",
    "love seat": "loveseat", "sofa bed": "sofa", "futon": "sofa", "daybed": "bed_single", "chest": "dresser", "credenza": "sideboard", "buffet": "sideboard",
    "plant": "plant", "planter": "plant", "tree": "plant",
}
_BED_SIZES = (("bed_king", ("king",)), ("bed_queen", ("queen",)), ("bed_double", ("full", "double")), ("bed_single", ("twin", "single")))


def normalize_category(category: str | None) -> str:
    """A catalog category from a category word or from a product's whole name."""
    if not category:
        return "other"
    key = str(category).strip().lower().replace("-", "_")
    if key in CATALOG:
        return key
    spaced = " ".join("".join(ch if ch.isalnum() else " " for ch in key).split())
    if spaced in ALIASES:
        return ALIASES[spaced]
    if spaced in CATALOG:
        return spaced
    words = spaced.split()
    singular = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words]
    text = " " + " ".join(singular) + " "
    # a bed is a bed whatever else its name mentions ("bed frame" must not become a picture frame)
    if " bed " in text or " bedframe " in text:
        for cat, size_words in _BED_SIZES:
            if any(f" {w} " in text for w in size_words):
                return cat
        return "bed"
    phrases = {**ALIASES, **PHRASES}
    for phrase in sorted((k for k in phrases if " " in k), key=len, reverse=True):
        if f" {phrase} " in text:
            return phrases[phrase]
    # then the last word that names something ("leather sofa" -> "sofa")
    for token in reversed(singular):
        if token in CATALOG:
            return token
        if token in phrases and token != "frame":
            return phrases[token]
    return "picture" if "frame" in singular else "other"


def spec_for(category: str | None) -> CategorySpec:
    return CATALOG[normalize_category(category)]


def clamp_dimensions(category: str | None, dims: tuple[float, float, float]) -> tuple[tuple[float, float, float], bool]:
    """Clamp (w, h, d) into the category's range. Returns (dims, was_clamped)."""
    spec = spec_for(category)
    out = []
    clamped = False
    for v, lo, hi in zip(dims, spec.min, spec.max):
        c = min(max(float(v), lo), hi)
        if abs(c - v) > 1e-9:
            clamped = True
        out.append(c)
    return (out[0], out[1], out[2]), clamped


def categories() -> list[str]:
    return sorted(CATALOG)
