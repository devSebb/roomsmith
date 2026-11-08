import math

import pytest

from rs_core import model as m
from rs_core import ops
from rs_core.model import SceneError


def scene():
    return m.new_scene("p1", "Room", 4.0, 5.0, 2.5)


def apply(s, *operations):
    return ops.apply_operations(s, list(operations))


def test_new_scene_is_canonical_rectangle():
    s = scene()
    assert m.is_rectangle(s)
    assert [w["label"] for w in s["room"]["walls"]] == ["back", "right", "front", "left"]
    assert m.wall_length(s, "w1") == 4.0
    assert m.wall_length(s, "w2") == 5.0


def test_add_object_against_wall_faces_in():
    s = scene()
    r = apply(s, {"op": "add_object", "name": "Sofa", "category": "sofa", "dimensions_m": [2.0, 0.85, 0.9], "place": {"against_wall": "w1", "align": "center"}})
    obj = r.scene["objects"][0]
    assert obj["id"] == "ob1"
    x, y, z = obj["position_m"]
    assert abs(x - 2.0) < 1e-9
    assert abs(z - (0.45 + 0.02)) < 1e-9
    assert abs(obj["yaw_rad"] - math.pi) < 1e-9  # faces +Z (into the room)
    assert r.results[0].created_id == "ob1"
    # original untouched
    assert s["objects"] == []


def test_against_wall_left_right_alignment():
    s = scene()
    r = apply(
        s,
        {"op": "add_object", "name": "A", "dimensions_m": [1.0, 1.0, 0.5], "place": {"against_wall": "w1", "align": "left"}},
        {"op": "add_object", "name": "B", "dimensions_m": [1.0, 1.0, 0.5], "place": {"against_wall": "w1", "align": "right", "offset_m": 0.2}},
    )
    a, b = r.scene["objects"]
    assert abs(a["position_m"][0] - 0.5) < 1e-9
    assert abs(b["position_m"][0] - (4.0 - 0.5 - 0.2)) < 1e-9


def test_against_right_wall_orientation():
    s = scene()
    r = apply(s, {"op": "add_object", "name": "Shelf", "dimensions_m": [0.8, 2.0, 0.3], "place": {"against_wall": "w2", "align": "center"}})
    o = r.scene["objects"][0]
    # right wall is x = 4; object centre should be 0.15 + gap inside
    assert abs(o["position_m"][0] - (4.0 - 0.15 - 0.02)) < 1e-9
    assert abs(o["position_m"][2] - 2.5) < 1e-9
    assert abs(o["yaw_rad"] - math.pi / 2) < 1e-9  # faces -X


def test_next_to_and_in_corner():
    s = scene()
    r = apply(
        s,
        {"op": "add_object", "name": "Bed", "category": "bed_double", "dimensions_m": [1.6, 0.5, 2.0], "place": {"against_wall": "w1", "align": "center"}},
        {"op": "add_object", "name": "Nightstand", "category": "nightstand", "dimensions_m": [0.4, 0.5, 0.4], "place": {"next_to": "ob1", "side": "right", "gap_m": 0.05}},
        {"op": "add_object", "name": "Plant", "category": "plant", "dimensions_m": [0.4, 1.2, 0.4], "place": {"in_corner": ["w1", "w2"]}},
    )
    bed, ns, plant = r.scene["objects"]
    # bed faces +Z, so its right is -X
    assert ns["position_m"][0] < bed["position_m"][0]
    assert abs((bed["position_m"][0] - ns["position_m"][0]) - (0.8 + 0.2 + 0.05)) < 1e-9
    # plant: back to w1 (z small), beside w2 (x near 4)
    assert abs(plant["position_m"][2] - 0.22) < 1e-9
    assert abs(plant["position_m"][0] - (4.0 - 0.22)) < 1e-9


def test_move_by_and_rotate():
    s = scene()
    r = apply(s, {"op": "add_object", "name": "Chair", "dimensions_m": [0.5, 0.9, 0.5], "position_m": [1, 0, 1]})
    r = apply(r.scene, {"op": "move_object", "id": "ob1", "by": [0.5, -0.25]}, {"op": "rotate_object", "id": "ob1", "by_deg": 90})
    o = r.scene["objects"][0]
    assert o["position_m"] == [1.5, 0.0, 0.75]
    assert abs(o["yaw_rad"] - math.pi / 2) < 1e-9


def test_locked_object_rejects_move():
    s = scene()
    r = apply(s, {"op": "add_object", "name": "Chair", "dimensions_m": [0.5, 0.9, 0.5], "position_m": [1, 0, 1]}, {"op": "lock", "id": "ob1"})
    with pytest.raises(SceneError) as e:
        apply(r.scene, {"op": "move_object", "id": "ob1", "by": [1, 0]})
    assert e.value.code == "locked"
    r2 = apply(r.scene, {"op": "move_object", "id": "ob1", "by": [1, 0], "force": True})
    assert r2.scene["objects"][0]["position_m"][0] == 2.0


def test_batch_is_atomic_on_error():
    s = scene()
    with pytest.raises(SceneError) as e:
        apply(s, {"op": "add_object", "name": "A", "dimensions_m": [1, 1, 1]}, {"op": "move_object", "id": "nope", "by": [1, 0]})
    assert e.value.code == "unknown_id"
    assert e.value.extra["index"] == 1
    assert s["objects"] == []


def test_set_wall_length_keeps_rectangle():
    s = scene()
    r = apply(s, {"op": "set_wall_length", "id": "w1", "length_m": 6.0})
    assert m.is_rectangle(r.scene)
    assert abs(m.wall_length(r.scene, "w1") - 6.0) < 1e-9
    assert abs(m.wall_length(r.scene, "w3") - 6.0) < 1e-9
    assert abs(m.wall_length(r.scene, "w2") - 5.0) < 1e-9


def test_openings_validation():
    s = scene()
    r = apply(s, {"op": "add_opening", "wall_id": "w1", "kind": "door", "offset_m": 0.2, "width_m": 0.9})
    assert r.scene["room"]["openings"][0]["height_m"] == 2.03
    with pytest.raises(SceneError) as e:
        apply(r.scene, {"op": "add_opening", "wall_id": "w1", "kind": "window", "offset_m": 0.5, "width_m": 1.0})
    assert e.value.code == "openings_overlap"
    with pytest.raises(SceneError) as e:
        apply(r.scene, {"op": "add_opening", "wall_id": "w1", "kind": "window", "offset_m": 3.5, "width_m": 1.0})
    assert e.value.code == "opening_outside_wall"
    with pytest.raises(SceneError) as e:
        apply(r.scene, {"op": "update_opening", "id": "o1", "height_m": 2.6})
    assert e.value.code == "opening_too_tall"


def test_add_opening_accepts_wall_label_and_default_width():
    # The model usually says "a door on the front wall" — no id, no width.
    r = apply(scene(), {"op": "add_opening", "wall": "front", "kind": "door", "position_fraction": 0.3})
    o = r.scene["room"]["openings"][0]
    assert o["wall_id"] == "w3" and o["width_m"] == 0.9
    assert o["offset_m"] == pytest.approx(0.3 * 4.0 - 0.45)
    r = apply(r.scene, {"op": "add_opening", "wall": "left", "kind": "window"})
    w = r.scene["room"]["openings"][1]
    assert w["wall_id"] == "w4" and w["width_m"] == 1.2 and w["sill_m"] == 0.9
    assert w["offset_m"] == pytest.approx((5.0 - 1.2) / 2)  # centred on the wall


def test_set_wall_length_shorter_clamps_openings():
    s = scene()
    r = apply(s, {"op": "add_opening", "wall_id": "w1", "kind": "window", "offset_m": 2.5, "width_m": 1.2})
    r = apply(r.scene, {"op": "set_wall_length", "id": "w1", "length_m": 3.0})
    o = r.scene["room"]["openings"][0]
    assert o["offset_m"] + o["width_m"] <= 3.0 + 1e-9


def test_calibrate_scales_estimated_only():
    s = scene()
    r = apply(
        s,
        {"op": "add_object", "name": "Sofa", "category": "sofa", "place": {"against_wall": "w1"}},  # estimated dims
        {"op": "add_object", "name": "Product", "dimensions_m": [1.0, 1.0, 1.0], "position_m": [2, 0, 2]},  # stated
    )
    r = apply(r.scene, {"op": "calibrate", "reference": {"kind": "wall_length", "id": "w1", "real_m": 8.0}})
    assert r.scene["calibration"]["status"] == "calibrated"
    assert abs(m.wall_length(r.scene, "w1") - 8.0) < 1e-9
    assert abs(m.wall_length(r.scene, "w2") - 10.0) < 1e-9
    sofa, prod = r.scene["objects"]
    assert abs(sofa["dimensions_m"][0] - 4.0) < 1e-9  # estimated: scaled x2
    assert prod["dimensions_m"] == [1.0, 1.0, 1.0]  # stated: unchanged
    assert prod["position_m"] == [4.0, 0.0, 4.0]  # position scaled


def test_duplicate_swap_remove():
    s = scene()
    r = apply(
        s,
        {"op": "add_object", "name": "A", "dimensions_m": [1, 1, 1], "position_m": [1, 0, 1]},
        {"op": "add_object", "name": "B", "dimensions_m": [1, 1, 1], "position_m": [3, 0, 3]},
        {"op": "duplicate_object", "id": "ob1"},
        {"op": "swap_objects", "a": "ob1", "b": "ob2"},
        {"op": "remove_object", "id": "ob3"},
    )
    ids = [o["id"] for o in r.scene["objects"]]
    assert ids == ["ob1", "ob2"]
    assert r.scene["objects"][0]["position_m"] == [3, 0, 3]
    # ids never reused
    r2 = apply(r.scene, {"op": "add_object", "name": "C", "dimensions_m": [1, 1, 1]})
    assert r2.scene["objects"][-1]["id"] == "ob4"


def test_bad_values_rejected():
    s = scene()
    for bad in (
        {"op": "add_object", "name": "X", "dimensions_m": [0, 1, 1]},
        {"op": "add_object", "name": "X", "dimensions_m": [float("nan"), 1, 1]},
        {"op": "add_object", "name": "X", "dimensions_m": [1, 1]},
        {"op": "set_room_height", "height_m": 1.0},
        {"op": "nonsense"},
        {"op": "set_surface_color", "surface": "floor", "color": "red"},
    ):
        with pytest.raises(SceneError):
            apply(s, bad)


def test_surface_colors():
    s = scene()
    r = apply(s, {"op": "set_surface_color", "surface": "floor", "color": "#abc"}, {"op": "set_surface_color", "surface": "walls", "color": "#FFEEDD"}, {"op": "set_surface_color", "surface": "back", "color": "#123456"})
    assert r.scene["room"]["floor"]["color"] == "#aabbcc"
    assert r.scene["room"]["walls"][1]["color"] == "#ffeedd"
    assert r.scene["room"]["walls"][0]["color"] == "#123456"


def test_move_vertex_makes_polygon_and_set_wall_length_refuses():
    s = scene()
    r = apply(s, {"op": "move_vertex", "id": "v3", "by": [0.5, 0.5]})
    assert not m.is_rectangle(r.scene)
    with pytest.raises(SceneError) as e:
        apply(r.scene, {"op": "set_wall_length", "id": "w1", "length_m": 3})
    assert e.value.code == "not_rectangle"


def test_self_intersecting_room_rejected():
    s = scene()
    # (0,0) (4,0) (-1,5) (0,5) is a bow-tie: edge v2->v3 crosses edge v4->v1
    with pytest.raises(SceneError) as e:
        apply(s, {"op": "move_vertex", "id": "v3", "x": -1.0, "z": 5.0})
    assert e.value.code == "invalid_room"


def test_facing_and_on_surface():
    s = scene()
    r = apply(
        s,
        {"op": "add_object", "name": "Desk", "category": "desk", "dimensions_m": [1.4, 0.75, 0.7], "place": {"against_wall": "w2"}},
        {"op": "add_object", "name": "Lamp", "category": "lamp_table", "dimensions_m": [0.3, 0.5, 0.3], "place": {"on": "ob1"}},
        {"op": "rotate_object", "id": "ob1", "facing": "front"},
    )
    desk, lamp = r.scene["objects"]
    assert abs(lamp["position_m"][1] - 0.75) < 1e-9
    assert abs(desk["yaw_rad"] - math.pi) < 1e-9
