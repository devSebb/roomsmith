"""The demo script (plan §18a) run end to end through the tool layer, exactly
as the model calls it: photo → draft room → calibrate → talk to the room →
a manual drag the agent must notice → "does anything block the door?" → a
product link → undo → export. One test, in order, so a regression anywhere
along the demo path shows up as the beat that broke."""

import json
from pathlib import Path

import pytest

from test_plugin_contract import ROOT, RecordingContext, _load_plugin  # noqa: F401 (shared harness)


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    draft = json.loads((ROOT / "fixtures" / "drafts" / "living_room_basic.json").read_text())

    class Result:
        parsed = draft
        text = json.dumps(draft)

    class Llm:
        def complete_structured(self, **kw):
            return Result()

    class HostCtx:
        llm = Llm()

    mod._ctx = HostCtx()
    img = tmp_path / "room.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    def call(tool, **args):
        return json.loads(ctx.tools[tool]["handler"](args, task_id="demo", session_id="demo"))

    return {"call": call, "ctx": ctx, "img": img, "tools": tools, "tmp": tmp_path}


def _by_name(objects, name):
    return next(o for o in objects if o["name"] == name)


def test_demo_script_end_to_end(demo):
    call, ctx, img = demo["call"], demo["ctx"], demo["img"]

    # 0–8 s  "Build this room."
    r = call("roomsmith_from_photo", images=[str(img)], name="Living room")
    assert r["ok"], r
    pid = r["project_id"]
    assert r["revision"] == 1
    assert "uncalibrated" in r["text"]  # the Draft badge
    names = {o["name"] for o in r["objects"]}
    assert {"Grey sofa", "Coffee table", "Bookshelf", "Floor plant"} <= names
    sofa_w_est = _by_name(r["objects"], "Grey sofa")["dimensions_m"][0]

    # 8–22 s  "The back wall is 4.6 m."  → everything rescales, the badge goes
    r = call("roomsmith_apply", expected_revision=1, operations=[{"op": "calibrate", "reference": {"kind": "wall_length", "id": "back", "real_m": 4.6}}])
    assert r["ok"], r
    insp = call("roomsmith_inspect")
    assert insp["room"]["width_m"] == pytest.approx(4.6, abs=1e-6)
    assert "calibrated" in insp["text"] and "uncalibrated" not in insp["text"]
    # a wall measurement corrects the room and positions; furniture keeps the sizes the model anchored on known objects
    assert _by_name(insp["objects"], "Grey sofa")["dimensions_m"][0] == pytest.approx(sofa_w_est, abs=1e-6)
    assert _by_name(insp["objects"], "Grey sofa")["nearest_wall"]["distance_m"] < 0.03  # still against its wall
    rev = insp["revision"]

    # 22–40 s  "Swap the sofa and the coffee table, and put the bookshelf against the window wall."
    objs = {o["name"]: o["id"] for o in insp["objects"]}
    r = call(
        "roomsmith_apply",
        expected_revision=rev,
        operations=[
            {"op": "swap_objects", "a": objs["Grey sofa"], "b": objs["Coffee table"]},
            {"op": "move_object", "id": objs["Bookshelf"], "place": {"against_wall": "back", "align": "right"}},
        ],
    )
    assert r["ok"], r
    assert len(r["results"]) == 2
    after = {o["name"]: o for o in call("roomsmith_inspect")["objects"]}
    before = {o["name"]: o for o in insp["objects"]}
    assert after["Grey sofa"]["position_m"][0] == pytest.approx(before["Coffee table"]["position_m"][0], abs=1e-6)
    assert after["Coffee table"]["position_m"][2] == pytest.approx(before["Grey sofa"]["position_m"][2], abs=1e-6)
    # the bookshelf's back is now within a few cm of the back wall (z ≈ depth/2 of the shelf)
    assert after["Bookshelf"]["position_m"][2] == pytest.approx(after["Bookshelf"]["dimensions_m"][2] / 2 + 0.02, abs=0.03)

    # 40–52 s  The plant is dragged by hand into the doorway; "Does anything block the door now?"
    svc = demo["tools"].get_service()
    door = next(o for o in call("roomsmith_inspect")["room"]["openings"] if o["kind"] == "door")
    plant_w = after["Floor plant"]["dimensions_m"][0]
    in_doorway = {"against_wall": door["wall_id"], "align": "left", "offset_m": door["offset_m"] + door["width_m"] / 2 - plant_w / 2, "gap_m": 0.1}
    manual = svc.apply({"project_id": pid, "actor": "user", "operations": [{"op": "move_object", "id": objs["Floor plant"], "place": in_doorway}]})
    assert manual["ok"], manual
    r = call("roomsmith_check", question="issues")
    assert r["ok"]
    blocks = [i for i in r["issues"] if i["code"] == "blocks_door"]
    assert any(objs["Floor plant"] in b["ids"] for b in blocks), r["issues"]
    # ...and Hermes is told about the manual move before its next answer in this session
    hook = ctx.hooks["pre_llm_call"][0]
    note = hook(session_id="demo")
    assert note and "Floor plant" in note["context"]
    assert hook(session_id="demo") is None  # only once

    # 52–70 s  A product link: "Would this sofa fit against the right wall instead?"
    rev = call("roomsmith_inspect")["revision"]
    r = call(
        "roomsmith_add_product",
        expected_revision=rev,
        title="KIVIK 3-seat sofa",
        dimensions_text="Width: 228 cm, Depth: 95 cm, Height: 83 cm",
        url="https://example.com/kivik",
        price="€799",
        place={"against_wall": "right", "align": "center"},
    )
    assert r["ok"], r
    assert r["object"]["dimensions_m"] == [2.28, 0.83, 0.95]
    assert r["object"]["dims_source"] == "stated" and r["object"]["category"] == "sofa"
    assert r["object"]["product"]["price"] == "€799"
    assert isinstance(r["clearance_m"], dict) and "passes" in r["passes_door"]  # the numbers Hermes quotes
    clearance = call("roomsmith_check", question="clearance", object_id=r["object"]["id"])
    assert clearance["ok"] and any(isinstance(v, (int, float)) for v in clearance["clearance_m"].values())

    # 70–82 s  Undo twice, plan view (data is the same), export
    r = call("roomsmith_history", action="undo")
    assert r["ok"] and "KIVIK" not in {o["name"] for o in r["objects"]}
    r = call("roomsmith_history", action="undo")
    assert r["ok"]
    plant = _by_name(r["objects"], "Floor plant")
    assert plant["position_m"] == pytest.approx(after["Floor plant"]["position_m"], abs=1e-6)  # the manual drag is undone
    issues = call("roomsmith_check", question="issues")["issues"]
    assert not [i for i in issues if i["code"] == "blocks_door" and objs["Floor plant"] in i["ids"]]
    for fmt in ("glb", "json", "text"):
        r = call("roomsmith_export", format=fmt, out_dir=str(demo["tmp"] / "export"))
        assert r["ok"] and Path(r["path"]).stat().st_size > 50, r

    # the close: the room list and /room still agree
    r = call("roomsmith_projects")
    assert r["ok"] and r["projects"][0]["name"] == "Living room"
    assert "Living room" in ctx.commands["room"]("")
