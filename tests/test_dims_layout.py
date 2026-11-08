import pytest

from rs_core import layout, validate
from rs_core.dims import parse_dimensions, parse_length


@pytest.mark.parametrize(
    "text,expected",
    [
        ("W 180 x D 88 x H 76 cm", (1.80, 0.76, 0.88)),
        ("Width: 228 cm Depth: 93 cm Height: 83 cm", (2.28, 0.83, 0.93)),
        ("180 x 88 x 76 cm", (1.80, 0.76, 0.88)),
        ("180x88x76cm", (1.80, 0.76, 0.88)),
        ("1800 x 880 x 760 mm", (1.80, 0.76, 0.88)),
        ("71 x 35 x 30 in", (1.8034, 0.762, 0.889)),
        ('71" W x 35" D x 30" H', (1.8034, 0.762, 0.889)),
        ("L 200 cm, W 90 cm, H 45 cm", (2.0, 0.45, 0.9)),
        ("1,8 m x 0,88 m x 0,76 m", (1.8, 0.76, 0.88)),
        ("Height 83 cm, width 228 cm, depth 95 cm", (2.28, 0.83, 0.95)),
        ("Dimensions: 84.6\"W x 37.4\"D x 33.9\"H", (2.1488, 0.8611, 0.95)),
        ("Product size 2.1 x 0.9 x 0.85 m", (2.1, 0.85, 0.9)),
    ],
)
def test_parse_dimensions(text, expected):
    r = parse_dimensions(text)
    assert r is not None, text
    got = (r["width_m"], r["height_m"], r["depth_m"])
    for a, b in zip(got, expected):
        assert abs(a - b) < 0.002, (text, got, expected)


def test_unlabelled_flags_assumed_order():
    r = parse_dimensions("180 x 88 x 76 cm")
    assert r["assumed_order"] is True
    r = parse_dimensions("W 180 x D 88 x H 76 cm")
    assert r["assumed_order"] is False


def test_partial_and_none():
    r = parse_dimensions("200 x 140 cm")
    assert r["partial"] and r["missing"] == ["height_m"]
    assert parse_dimensions("very comfortable") is None
    assert parse_dimensions("") is None
    assert parse_dimensions(None) is None


def test_parse_length():
    assert abs(parse_length("4.2 m") - 4.2) < 1e-9
    assert abs(parse_length("250cm") - 2.5) < 1e-9
    assert abs(parse_length("14 ft") - 4.2672) < 1e-6
    assert abs(parse_length("6'2\"") - (6 * 0.3048 + 2 * 0.0254)) < 1e-6
    assert abs(parse_length("420") - 4.2) < 1e-9  # guesses cm


DRAFT = {
    "room": {"width_m": 4.2, "depth_m": 5.0, "height_m": 2.6},
    "walls_visible": ["back", "left"],
    "colors": {"walls": "#eeeeee", "floor": "#a0784c"},
    "openings": [
        {"wall": "left", "kind": "door", "position_fraction": 0.3, "width_m": 0.85},
        {"wall": "back", "kind": "window", "position_fraction": 0.5, "width_m": 1.4, "height_m": 1.3, "sill_m": 0.9},
    ],
    "objects": [
        {"label": "Grey sofa", "category": "sofa", "width_m": 2.1, "height_m": 0.85, "depth_m": 0.9, "against_wall": "back", "across_fraction": 0.5, "into_fraction": 0.1, "facing": "front", "color": "#6b7a8f", "confidence": 0.8},
        {"label": "Coffee table", "category": "table_coffee", "width_m": 1.0, "height_m": 0.4, "depth_m": 0.6, "against_wall": "none", "across_fraction": 0.5, "into_fraction": 0.35, "confidence": 0.7},
        {"label": "Bookshelf", "category": "bookshelf", "width_m": 0.8, "height_m": 9.0, "depth_m": 0.3, "against_wall": "right", "across_fraction": 0.95, "into_fraction": 0.6, "confidence": 0.5},
        {"label": "Overlapping chair", "category": "armchair", "width_m": 0.9, "height_m": 0.85, "depth_m": 0.9, "against_wall": "none", "across_fraction": 0.5, "into_fraction": 0.35},
        {"label": "TV", "category": "tv", "width_m": 1.2, "height_m": 0.7, "depth_m": 0.08, "against_wall": "front", "across_fraction": 0.5, "into_fraction": 0.98},
    ],
    "notes": "The right wall is partly guessed.",
}


def test_build_scene_from_draft():
    scene, notes = layout.build_scene("p", "Draft", DRAFT)
    validate.validate_hard(scene)
    assert scene["calibration"]["status"] == "uncalibrated"
    assert len(scene["room"]["openings"]) == 2
    door = scene["room"]["openings"][0]
    assert door["wall_id"] == "w4" and door["kind"] == "door"
    assert len(scene["objects"]) == 5
    sofa = scene["objects"][0]
    assert sofa["provenance"]["dims_source"] == "estimated"
    assert abs(sofa["position_m"][2] - (0.45 + 0.02)) < 1e-6  # snapped flush to the back wall
    shelf = scene["objects"][2]
    assert shelf["dimensions_m"][1] <= 2.6  # clamped
    assert any("clamped" in n for n in notes)
    # chair and coffee table were on top of each other: nudged apart
    issues = [i for i in validate.issues(scene) if i["code"] == "overlap"]
    assert not issues, issues
    assert any("Nudged apart" in n for n in notes)
    assert any("partly guessed" in n for n in notes)
    assert scene["room"]["walls"][0]["color"] == "#eeeeee"


def test_build_scene_from_garbage():
    scene, notes = layout.build_scene("p", "Bad", {"room": "huh", "objects": [None, 3, {"label": "x" * 200, "width_m": "wide"}]})
    validate.validate_hard(scene)
    assert len(scene["objects"]) == 1
    assert len(scene["objects"][0]["name"]) == 60
    scene, notes = layout.build_scene("p", "Empty", None)
    validate.validate_hard(scene)
    assert scene["objects"] == []
    assert any("default" in n for n in notes)


def test_small_plant_on_a_side_table_sits_on_it():
    """From the first real photo: a potted plant whose centre lands on a side
    table is a tabletop plant, not a floor plant overlapping the table."""
    draft = {
        "room": {"width_m": 3.1, "depth_m": 5.6, "height_m": 2.7},
        "objects": [
            {"label": "Side table", "category": "table_side", "width_m": 0.4, "height_m": 0.55, "depth_m": 0.4, "against_wall": "right", "across_fraction": 0.85, "into_fraction": 0.04},
            {"label": "Potted plant", "category": "plant", "width_m": 0.25, "height_m": 0.3, "depth_m": 0.25, "against_wall": "none", "across_fraction": 0.85, "into_fraction": 0.04},
            {"label": "Tall plant", "category": "plant", "width_m": 0.5, "height_m": 1.5, "depth_m": 0.5, "against_wall": "none", "across_fraction": 0.2, "into_fraction": 0.5},
        ],
    }
    scene, notes = layout.build_scene("p", "Photo", draft)
    validate.validate_hard(scene)
    table, plant, tall = scene["objects"]
    assert plant["mount"] == "surface"
    assert abs(plant["position_m"][1] - 0.55) < 1e-6
    assert any("placed on top of Side table" in n for n in notes)
    assert tall["mount"] == "floor" and tall["position_m"][1] == 0.0
    assert not [i for i in validate.issues(scene) if i["code"] == "overlap"]
