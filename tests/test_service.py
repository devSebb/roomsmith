import json
import threading

from rs_core.service import RoomService


def test_create_and_inspect(svc):
    r = svc.create_project("Living room", 4.2, 5.1, 2.6)
    assert r["ok"] and r["created"]
    assert r["revision"] == 1
    assert r["room"]["width_m"] == 4.2
    assert "Room 'Living room'" in r["text"]
    lst = svc.list_projects()
    assert lst["active_project_id"] == r["project_id"]
    assert lst["projects"][0]["active"] is True


def test_no_active_room_error(svc):
    r = svc.inspect()
    assert not r["ok"] and r["error"]["code"] == "no_active_room"


def test_apply_revision_conflict_and_retry(svc, room):
    head = svc.head(room)
    assert head["revision"] == 2
    r = svc.apply({"project_id": room, "expected_revision": 1, "operations": [{"op": "set_room_height", "height_m": 2.7}]})
    assert not r["ok"] and r["error"]["code"] == "revision_conflict"
    assert r["error"]["current_revision"] == 2
    r = svc.apply({"project_id": room, "expected_revision": 2, "operations": [{"op": "set_room_height", "height_m": 2.7}]})
    assert r["ok"] and r["revision"] == 3


def test_apply_without_expected_revision_is_allowed(svc, room):
    r = svc.apply({"project_id": room, "operations": [{"op": "add_object", "name": "Chair", "category": "chair"}]})
    assert r["ok"]
    assert r["results"][0]["created_id"] == "ob1"


def test_idempotent_command_id(svc, room):
    cmd = {"project_id": room, "command_id": "abc", "operations": [{"op": "add_object", "name": "Chair", "category": "chair"}]}
    r1 = svc.apply(cmd)
    r2 = svc.apply(cmd)
    assert r1["ok"] and r2["ok"]
    assert r2["replayed"] is True
    assert r2["revision"] == r1["revision"]
    assert len(svc.scene(room)["scene"]["objects"]) == 1


def test_validation_error_returns_not_raises(svc, room):
    r = svc.apply({"project_id": room, "operations": [{"op": "move_object", "id": "ob99", "by": [1, 0]}]})
    assert not r["ok"] and r["error"]["code"] == "unknown_id"
    assert svc.head(room)["revision"] == 2


def test_undo_redo_are_forward_revisions(svc, room):
    svc.apply({"project_id": room, "operations": [{"op": "add_object", "name": "A", "dimensions_m": [1, 1, 1], "position_m": [1, 0, 1]}]})
    svc.apply({"project_id": room, "operations": [{"op": "move_object", "id": "ob1", "by": [1, 0]}]})
    assert svc.head(room)["revision"] == 4
    u = svc.undo(room)
    assert u["ok"] and u["revision"] == 5
    assert svc.scene(room)["scene"]["objects"][0]["position_m"][0] == 1.0
    u2 = svc.undo(room)
    assert u2["revision"] == 6 and svc.scene(room)["scene"]["objects"] == []
    r = svc.redo(room)
    assert r["revision"] == 7 and len(svc.scene(room)["scene"]["objects"]) == 1
    r2 = svc.redo(room)
    assert r2["revision"] == 8 and svc.scene(room)["scene"]["objects"][0]["position_m"][0] == 2.0
    assert not svc.redo(room)["ok"]
    # a new edit after undo clears redo
    svc.undo(room)
    svc.apply({"project_id": room, "operations": [{"op": "set_room_height", "height_m": 2.6}]})
    assert not svc.redo(room)["ok"]
    assert svc.undo(room)["ok"]


def test_history_cap(svc, room):
    for i in range(230):
        # keep the ceiling above the 2.03 m door
        r = svc.apply({"project_id": room, "operations": [{"op": "set_room_height", "height_m": 2.4 + (i % 10) * 0.05}]})
        assert r["ok"], r
    h = svc.history(room, limit=5)
    assert h["revisions"][0]["revision"] == 232
    undo, _ = svc.store.history_stacks(room)
    assert len(undo) == 200
    # undo still works for the newest 200
    assert svc.undo(room)["ok"]


def test_issues_reported_on_apply(svc, room):
    r = svc.apply({"project_id": room, "operations": [{"op": "add_object", "name": "A", "dimensions_m": [1, 1, 1], "position_m": [3.8, 0, 2.5]}]})
    assert "outside_room" in [i["code"] for i in r["issues"]]


def test_check_questions(svc, room):
    svc.apply({"project_id": room, "operations": [{"op": "add_object", "name": "Bed", "category": "bed_double", "dimensions_m": [1.6, 0.5, 2.0], "place": {"against_wall": "w1", "align": "center"}}]})
    assert svc.check(room, "issues")["count"] == 0
    f = svc.check(room, "fits_at", dimensions_m=[2.0, 0.85, 0.9], place={"against_wall": "w3", "align": "center"})
    assert f["ok"] and f["fits"]
    w = svc.check(room, "where_fits", dimensions_m=[1.0, 2.0, 0.4])
    assert w["found"] >= 1
    d = svc.check(room, "passes_door", dimensions_m=[2.0, 0.85, 0.9])
    assert d["passes"] is True
    c = svc.check(room, "clearance", object_id="ob1")
    assert set(c["clearance_m"]) == {"front", "back", "left", "right"}
    bad = svc.check(room, "fits_at", dimensions_m=[1, 1, 1])
    assert not bad["ok"]


def test_add_product_parses_text(svc, room):
    r = svc.add_product(room, "KIVIK sofa", dimensions_text="Width: 228 cm, Depth: 95 cm, Height: 83 cm", url="https://example.com/kivik", price="€699", place={"against_wall": "w3", "align": "center"})
    assert r["ok"], r
    o = r["object"]
    assert o["dimensions_m"] == [2.28, 0.83, 0.95]
    assert o["dims_source"] == "stated"
    assert o["product"]["url"] == "https://example.com/kivik"
    assert r["passes_door"]["passes"] is True
    bad = svc.add_product(room, "Mystery", dimensions_text="big")
    assert not bad["ok"] and bad["error"]["code"] == "dimensions_unreadable"
    partial = svc.add_product(room, "Rug", dimensions_text="200 x 140 cm")
    assert not partial["ok"] and partial["error"]["code"] == "dimensions_incomplete"


def test_export_formats(svc, room, tmp_path):
    svc.apply({"project_id": room, "operations": [{"op": "add_object", "name": "Plant", "category": "plant"}]})
    j = svc.export(room, "json", tmp_path / "out")
    g = svc.export(room, "glb", tmp_path / "out")
    t = svc.export(room, "summary", tmp_path / "out")
    assert j["ok"] and g["ok"] and t["ok"]
    payload = json.loads(open(j["path"]).read())
    assert payload["scene"]["project"]["name"] == "Test room"
    data = open(g["path"], "rb").read()
    assert data[:4] == b"glTF"
    assert "Plant" in open(t["path"]).read()
    imp = svc.import_json(payload, name="Copy")
    assert imp["ok"] and imp["name"] == "Copy"


def test_unseen_changes_tracking(svc, room):
    # the agent's own edits are seen; user edits are not
    svc.apply({"project_id": room, "actor": "agent", "operations": [{"op": "set_room_height", "height_m": 2.6}]})
    assert svc.unseen_changes(room)["changes"] == []
    svc.apply({"project_id": room, "actor": "user", "operations": [{"op": "set_room_height", "height_m": 2.7}]})
    svc.apply({"project_id": room, "actor": "user", "operations": [{"op": "add_object", "name": "Chair", "category": "chair"}]})
    u = svc.unseen_changes(room)
    assert len(u["changes"]) == 2
    assert u["changes"][0]["actor"] == "user"
    svc.inspect(room, mark_seen=True)
    assert svc.unseen_changes(room)["changes"] == []


def test_two_process_style_access(tmp_path):
    """Two Store instances (as two processes would have) on the same file."""
    a = RoomService(tmp_path / "data.db", tmp_path)
    b = RoomService(tmp_path / "data.db", tmp_path)
    pid = a.create_project("Shared", 4, 5, 2.5)["project_id"]
    assert b.head(pid)["revision"] == 1
    errors = []

    def writer(s, n):
        for i in range(n):
            r = s.apply({"project_id": pid, "operations": [{"op": "add_object", "name": f"x{i}", "dimensions_m": [0.2, 0.2, 0.2], "position_m": [1 + i * 0.01, 0, 1]}]})
            if not r["ok"]:
                errors.append(r)

    ta = threading.Thread(target=writer, args=(a, 25))
    tb = threading.Thread(target=writer, args=(b, 25))
    ta.start(), tb.start()
    ta.join(), tb.join()
    assert not errors
    assert a.head(pid)["revision"] == 51
    assert len(b.scene(pid)["scene"]["objects"]) == 50
    # optimistic concurrency between the two
    rev = a.head(pid)["revision"]
    assert b.apply({"project_id": pid, "expected_revision": rev, "operations": [{"op": "set_room_height", "height_m": 2.6}]})["ok"]
    conflict = a.apply({"project_id": pid, "expected_revision": rev, "operations": [{"op": "set_room_height", "height_m": 2.8}]})
    assert conflict["error"]["code"] == "revision_conflict"
    a.close(), b.close()


def test_rename_delete_activate(svc):
    p1 = svc.create_project("One", 3, 3, 2.5)["project_id"]
    p2 = svc.create_project("Two", 3, 3, 2.5)["project_id"]
    assert svc.list_projects()["active_project_id"] == p2
    assert svc.activate(p1)["active_project_id"] == p1
    assert svc.activate("Two")["active_project_id"] == p2  # by name
    assert svc.rename(p1, "Uno")["name"] == "Uno"
    assert svc.inspect(p1)["name"] == "Uno"
    d = svc.delete(p2)
    assert d["ok"] and d["active_project_id"] == p1
    assert not svc.inspect(p2)["ok"]
