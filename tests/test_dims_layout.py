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


def test_ceiling_light_hangs_overhead_and_does_not_block_the_door():
    """From the Mini S2 run: the model listed a pendant as category 'other' with no
    vertical placement, so it landed on the floor and 'blocked the door'."""
    draft = {
        "room": {"width_m": 2.65, "depth_m": 4.4, "height_m": 2.7},
        "openings": [{"wall": "back", "kind": "door", "position_fraction": 0.5, "width_m": 1.55, "height_m": 2.1}],
        "objects": [
            {"label": "Black branching ceiling light", "category": "other", "width_m": 1.25, "height_m": 0.65, "depth_m": 0.95, "against_wall": "none", "across_fraction": 0.45, "into_fraction": 0.4},
            {"label": "Framed poster", "category": "picture", "width_m": 0.6, "height_m": 0.45, "depth_m": 0.03, "against_wall": "left", "across_fraction": 0.0, "into_fraction": 0.5, "mount": "wall", "elevation_m": 1.4},
            {"label": "Pendant over table", "category": "pendant", "width_m": 0.3, "height_m": 0.3, "depth_m": 0.3, "against_wall": "none", "across_fraction": 0.5, "into_fraction": 0.6, "mount": "ceiling", "elevation_m": 1.95},
        ],
    }
    scene, notes = layout.build_scene("p", "Photo", draft)
    validate.validate_hard(scene)
    light, poster, pendant = scene["objects"]
    assert light["category"] == "lamp_ceiling" and light["mount"] == "ceiling"
    assert abs(light["position_m"][1] - (2.7 - 0.65)) < 1e-6  # flush to the ceiling when no elevation given
    assert poster["mount"] == "wall" and abs(poster["position_m"][1] - 1.4) < 1e-6
    assert pendant["mount"] == "ceiling" and abs(pendant["position_m"][1] - 1.95) < 1e-6
    codes = {i["code"] for i in validate.issues(scene)}
    assert "blocks_door" not in codes and "tight_walkway" not in codes and "overlap" not in codes, validate.issues(scene)


def test_floor_object_raised_overhead_stops_blocking():
    """An object the agent lifted with position_m y ≥ 1.9 (mount still 'floor') is walked under."""
    from rs_core import model as m, ops

    scene = m.new_scene("p", "R", 3.0, 4.0, 2.7)
    scene["room"]["openings"].append(m.make_opening(scene, "w1", "door", 1.0, 1.0, 2.1, 0.0))
    scene = ops.apply_operations(scene, [{"op": "add_object", "name": "Light", "category": "other", "dimensions_m": [1.2, 0.6, 0.9], "place": {"position_m": [1.5, 0, 0.5]}}]).scene
    assert any(i["code"] == "blocks_door" for i in validate.issues(scene))
    scene = ops.apply_operations(scene, [{"op": "move_object", "id": "ob1", "place": {"position_m": [1.5, 2.05, 0.5]}}]).scene
    assert not [i for i in validate.issues(scene) if i["code"] in ("blocks_door", "tight_walkway")]


def test_draft_notes_are_clipped_at_a_word():
    long = "word " * 200
    scene, notes = layout.build_scene("p", "N", {"room": {"width_m": 3, "depth_m": 3}, "objects": [], "notes": long})
    clipped = notes[-1]
    assert clipped.endswith("…") and len(clipped) <= 501 and not clipped.endswith("wor…")


def test_nudge_apart_lets_the_larger_object_give_way_and_carries_riders():
    """Calibrating the first real photo compressed depth and pushed the side table
    into the sofa; the table was already against the back wall, so the sofa must
    move, and the plant on the table must stay on the table."""
    from rs_core import model as m

    s = m.new_scene("p", "R", 2.85, 3.0, 2.7)
    sofa = m.make_object(s, "Sofa", "sofa", (2.0, 0.82, 0.88)); sofa["position_m"] = [2.39, 0.0, 1.2]; sofa["yaw_rad"] = 1.5707963
    table = m.make_object(s, "Table", "table_side", (0.4, 0.58, 0.36)); table["position_m"] = [2.25, 0.0, 0.36]; table["yaw_rad"] = 1.5707963
    plant = m.make_object(s, "Plant", "plant", (0.25, 0.3, 0.23), mount="surface"); plant["position_m"] = [2.22, 0.58, 0.36]
    s["objects"] += [sofa, table, plant]
    moved = layout.nudge_apart(s)
    assert "Sofa (ob1)" in moved and "Table (ob2)" in moved
    assert not [i for i in validate.issues(s) if i["code"] == "overlap"], validate.issues(s)
    assert abs(plant["position_m"][2] - table["position_m"][2]) < 1e-6  # rode with the table, not the sofa
    assert plant["position_m"][1] == 0.58


def test_real_product_pages_parse_with_the_right_axes():
    """Strings copied from live product pages (Floyd, 2026-11-09). A bed's L is its
    length (our depth); a sofa's L would be its width across the front."""
    from rs_core import dims

    sofa = dims.parse_dimensions('Overall: 86"W x 34"D x 32"H', category="sofa")
    assert (round(sofa["width_m"], 3), round(sofa["depth_m"], 3), round(sofa["height_m"], 3)) == (2.184, 0.864, 0.813)
    bed = dims.parse_dimensions('Overall: 67” W x 86" L x 7.5” H', category="bed_double")
    assert (round(bed["width_m"], 2), round(bed["depth_m"], 2), round(bed["height_m"], 2)) == (1.70, 2.18, 0.19)
    king = dims.parse_dimensions('Overall 89” W x 86" L x 31.5” H', category="bed_double")
    assert round(king["width_m"], 2) == 2.26 and round(king["depth_m"], 2) == 2.18
    table = dims.parse_dimensions("L 160 x W 90 x H 75 cm", category="table_dining")
    assert (table["width_m"], table["depth_m"]) == (1.6, 0.9)  # unchanged convention for tables/sofas
    block = dims.parse_dimensions('Overall: 15" W x 12.56" L x 22" H', category="shelf")
    assert round(block["width_m"], 3) == 0.319 and round(block["depth_m"], 3) == 0.381  # shelf: L runs along the front


def test_add_product_uses_the_title_to_pick_the_axis_rule(tmp_path):
    from rs_core.service import RoomService

    s = RoomService(tmp_path / "data.db", tmp_path)
    pid = s.create_project("B", width_m=2.82, depth_m=4.0)["project_id"]
    r = s.add_product(pid, title="The Floyd Bed - Original (Queen)", dimensions_text='Overall: 67” W x 86" L x 7.5” H', url="https://floydhome.com/products/the-bed-frame", place={"against_wall": "right", "align": "left"})
    assert r["ok"], r
    assert r["object"]["category"].startswith("bed")
    assert round(r["object"]["dimensions_m"][0], 2) == 1.70 and round(r["object"]["dimensions_m"][2], 2) == 2.18


def test_sizes_are_turned_to_match_the_category_when_the_shop_labels_them_the_other_way():
    from rs_core import dims

    desk = dims.parse_dimensions('24" D x 42" W x 30" H', category="desk")
    assert round(desk["width_m"], 2) == 1.07 and round(desk["depth_m"], 2) == 0.61
    turned = dims.parse_dimensions("61 x 106 x 76 cm", category="desk")  # unlabelled, deeper than wide
    assert round(turned["width_m"], 2) == 1.06 and round(turned["depth_m"], 2) == 0.61 and turned["reoriented"] and "longer side as the width" in turned["order_note"]
    bed = dims.parse_dimensions("191 x 139 x 41 cm", category="bed_double")
    assert round(bed["width_m"], 2) == 1.39 and round(bed["depth_m"], 2) == 1.91
    lamp = dims.parse_dimensions("97 x 44 x 44 cm", category="lamp_floor")
    assert round(lamp["height_m"], 2) == 0.97 and round(lamp["width_m"], 2) == 0.44
    plain = dims.parse_dimensions("120 x 60 x 75 cm", category="desk")
    assert round(plain["width_m"], 2) == 1.2 and not plain.get("reoriented")
    assert not dims.parse_dimensions("61 x 106 x 76 cm")["width_m"] == 1.06  # no category: left as read


def test_a_unit_printed_once_applies_to_the_labelled_values_beside_it():
    """Found live: 'W 27.5 x D 27.5 x H 34.5 inches' read the first two as centimetres."""
    from rs_core import dims

    c = dims.parse_dimensions("W 27.5 x D 27.5 x H 34.5 inches overall; seat height adjusts from 17 to 20.75 inches from floor", category="chair")
    assert [round(c[k], 2) for k in ("width_m", "depth_m", "height_m")] == [0.7, 0.7, 0.88]
    m = dims.parse_dimensions("Width: 180 cm, Depth: 88, Height: 76", category="sofa")
    assert [round(m[k], 2) for k in ("width_m", "depth_m", "height_m")] == [1.8, 0.88, 0.76]


def test_product_names_say_what_the_thing_is():
    from rs_core.catalog import normalize_category as n
    from rs_core import dims

    cases = {"SONGMICS HOME Area Rug, 5x7 ft": "rug", "Queen bed frame": "bed_queen", "TARVA Bed frame - pine Queen": "bed_queen", "TV stand": "tv_stand",
             "Draper Mid Century Low TV Stand": "tv_stand", "IKEA PS 2026 Floor uplighter, dark red": "lamp_floor", "Wall art print, framed": "picture",
             "6-Shelf Ladder Bookshelf Oak Matte Black": "bookshelf", "Nightstands (set of 2)": "nightstand", "Counter Stool, walnut": "stool",
             "leather sofa": "sofa", "picture frame": "picture", "drawers": "dresser", "bedding set": "other", "lamp_floor": "lamp_floor"}
    for name, want in cases.items():
        assert n(name) == want, (name, n(name))
    assert round(dims.length_with_unit('IKEA PS 2026 Floor uplighter - dark red 72 "'), 2) == 1.83
    assert dims.length_with_unit("Model 2026 lamp") is None and round(dims.length_with_unit("Height 150 cm, model 3000"), 2) == 1.5
