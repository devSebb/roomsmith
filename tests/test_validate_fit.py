from rs_core import fitcheck, validate
from rs_core import model as m
from rs_core import ops


def scene_with(*objects):
    s = m.new_scene("p", "R", 4.0, 5.0, 2.5)
    r = ops.apply_operations(
        s,
        [
            {"op": "add_opening", "wall_id": "w4", "kind": "door", "offset_m": 0.5, "width_m": 0.9},
            {"op": "add_opening", "wall_id": "w1", "kind": "window", "offset_m": 1.5, "width_m": 1.2, "sill_m": 0.9, "height_m": 1.2},
            *objects,
        ],
    )
    return r.scene


def codes(issues):
    return sorted(i["code"] for i in issues)


def test_clean_room_only_uncalibrated():
    s = scene_with({"op": "add_object", "name": "Sofa", "dimensions_m": [2, 0.85, 0.9], "place": {"against_wall": "w3", "align": "center"}})
    assert codes(validate.issues(s)) == ["uncalibrated"]


def test_overlap_detected():
    s = scene_with(
        {"op": "add_object", "name": "A", "dimensions_m": [1, 1, 1], "position_m": [2, 0, 2.5]},
        {"op": "add_object", "name": "B", "dimensions_m": [1, 1, 1], "position_m": [2.5, 0, 2.5]},
    )
    found = [i for i in validate.issues(s) if i["code"] == "overlap"]
    assert len(found) == 1
    assert found[0]["ids"] == ["ob1", "ob2"]
    assert abs(found[0]["overlap_m"] - 0.5) < 1e-6


def test_touching_is_not_overlap():
    s = scene_with(
        {"op": "add_object", "name": "A", "dimensions_m": [1, 1, 1], "position_m": [2, 0, 2.5]},
        {"op": "add_object", "name": "B", "dimensions_m": [1, 1, 1], "position_m": [3, 0, 2.5]},
    )
    assert "overlap" not in codes(validate.issues(s))


def test_outside_room():
    s = scene_with({"op": "add_object", "name": "A", "dimensions_m": [1, 1, 1], "position_m": [3.8, 0, 2.5]})
    found = [i for i in validate.issues(s) if i["code"] == "outside_room"]
    assert found and abs(found[0]["outside_m"] - 0.3) < 1e-6


def test_blocks_door():
    # w4 runs from v4 (0,5) to v1 (0,0); offset 0.5 puts the door at z 4.5..3.6.
    # A box right in front of it blocks; the same box lower down the wall does not.
    s = scene_with({"op": "add_object", "name": "A", "dimensions_m": [0.6, 1, 0.6], "position_m": [0.4, 0, 4.05]})
    found = [i for i in validate.issues(s) if i["code"] == "blocks_door"]
    assert found and found[0]["ids"] == ["ob1", "o1"]
    s = scene_with({"op": "add_object", "name": "A", "dimensions_m": [0.6, 1, 0.6], "position_m": [0.4, 0, 1.0]})
    assert "blocks_door" not in codes(validate.issues(s))


def test_blocks_window_only_when_above_sill():
    # window on w1 (z=0) from x=1.5 to 2.7, sill 0.9
    low = scene_with({"op": "add_object", "name": "Low", "dimensions_m": [1, 0.5, 0.5], "place": {"against_wall": "w1", "align": "center"}})
    assert "blocks_window" not in codes(validate.issues(low))
    tall = scene_with({"op": "add_object", "name": "Tall", "dimensions_m": [1, 1.8, 0.4], "place": {"against_wall": "w1", "align": "center"}})
    assert "blocks_window" in codes(validate.issues(tall))


def test_too_tall():
    s = scene_with({"op": "add_object", "name": "Tower", "dimensions_m": [0.5, 2.6, 0.5], "position_m": [2, 0, 2.5]})
    assert "too_tall" in codes(validate.issues(s))


def test_tight_walkway_blocked_by_a_wall_of_furniture():
    # door at z 3.6..4.5 on the left wall, centre at (2, 2.5): a 3.9 m wide block
    # at z 3.0 lies between them and leaves only 5 cm at each end
    s = scene_with({"op": "add_object", "name": "Wall of boxes", "dimensions_m": [3.9, 1, 0.6], "position_m": [2.0, 0, 3.0]})
    found = [i for i in validate.issues(s) if i["code"] == "tight_walkway"]
    assert found, validate.issues(s)
    assert "ob1" in found[0]["ids"]


def test_walkway_ok_with_gap():
    s = scene_with({"op": "add_object", "name": "Sofa", "dimensions_m": [2, 0.85, 0.9], "place": {"against_wall": "w2", "align": "center"}})
    assert "tight_walkway" not in codes(validate.issues(s))


def test_fits_at_reports_clearance():
    s = scene_with({"op": "add_object", "name": "Shelf", "dimensions_m": [0.8, 2, 0.3], "place": {"against_wall": "w3", "align": "left"}})
    res = fitcheck.fits_at(s, [2.0, 0.85, 0.9], {"against_wall": "w3", "align": "right"})
    assert res["fits"] is True
    # shelf occupies x 0..0.8 on w3; sofa right-aligned occupies x 2..4.
    # Facing +... w3 is the front wall; from inside facing it, "right" is toward w3's end (x=0).
    assert res["clearance_m"]["left"] > 0 or res["clearance_m"]["right"] > 0
    assert "Fits" in res["verdict"]


def test_fits_at_detects_overlap():
    s = scene_with({"op": "add_object", "name": "Shelf", "dimensions_m": [3.0, 2, 0.3], "place": {"against_wall": "w3", "align": "center"}})
    res = fitcheck.fits_at(s, [2.0, 0.85, 0.9], {"against_wall": "w3", "align": "center"})
    assert res["fits"] is False
    assert "overlap" in [i["code"] for i in res["issues"]]


def test_where_fits_finds_spots():
    s = scene_with({"op": "add_object", "name": "Bed", "dimensions_m": [1.6, 0.5, 2.0], "place": {"against_wall": "w1", "align": "center"}})
    res = fitcheck.where_fits(s, [1.2, 0.8, 0.5])
    assert res["found"] >= 1
    assert res["candidates"][0]["clearance_m"]["left"] >= 0


def test_passes_door():
    s = scene_with()
    assert fitcheck.passes_door(s, [2.0, 0.85, 0.9])["passes"] is True  # 0.85 x 0.9 vs 0.9 x 2.03
    assert fitcheck.passes_door(s, [2.0, 1.0, 0.95])["passes"] is False


def test_fits_at_with_object_id_and_dimensions_tests_a_replacement(tmp_path):
    """Mini product run: 'would this (bigger) bed fit where my bed is?' passed object_id and
    dimensions_m; the old code used the old bed's size and said yes; without object_id it
    overlapped the old bed and said no. Replacement semantics make the answer honest."""
    from rs_core.service import RoomService

    s = RoomService(tmp_path / "data.db", tmp_path)
    pid = s.create_project("B", width_m=2.82, depth_m=4.0)["project_id"]
    s.apply({"project_id": pid, "operations": [{"op": "add_object", "name": "Double bed", "category": "bed_double", "dimensions_m": [1.4, 0.5, 2.0], "place": {"against_wall": "right", "align": "center"}}]})
    # the replacement bed, 1.70 wide: fits on the 2.82 m wall where the 1.40 m bed is (ignoring the old bed)
    r = s.check(pid, question="fits_at", object_id="ob1", dimensions_m=[1.70, 0.8, 2.18], name="Queen")
    assert r["ok"] and r["fits"] is True, r
    assert r["replacing"]["id"] == "ob1" and r["tested_dimensions_m"] == [1.7, 0.8, 2.18]
    assert r["placement"]  # placed at the old bed's spot by default
    # without object_id the same box overlaps the existing bed and the result says what to do
    r2 = s.check(pid, question="fits_at", dimensions_m=[1.70, 0.8, 2.18], place={"position_m": [2.12, 0, 1.5]})
    assert r2["fits"] is False and "object_id='ob1'" in r2["hint"]
    # too wide for the wall it stands on: fails even as a replacement
    r3 = s.check(pid, question="fits_at", object_id="ob1", dimensions_m=[4.5, 0.8, 2.0])
    assert r3["fits"] is False
