"""Registration contract: what the catalog validator's probe and Hermes expect.

The probe calls register() against a stub that exposes only PluginContext's
callable methods (no properties), records every registration, and compares
with plugin.yaml. We do the same here, plus a round trip through the tool
handlers with the data dir redirected to a temp folder.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class RecordingContext:
    """Methods only, like hermes_cli/plugin_validate.py's probe stub."""

    def __init__(self):
        self.tools = {}
        self.commands = {}
        self.hooks = {}
        self.skills = {}

    def register_tool(self, name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, description="", emoji="", override=False):
        assert name not in self.tools
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler, "description": description}

    def register_command(self, name, handler, description="", args_hint="", argument_mode=None):
        self.commands[name] = handler

    def register_hook(self, hook_name, callback):
        self.hooks.setdefault(hook_name, []).append(callback)

    def register_skill(self, name, path, description="", frontmatter=None):
        assert Path(path).exists()
        self.skills[name] = path

    def __getattr__(self, item):
        # any *property* access (ctx.llm, ctx.state, ctx.config) is a contract violation
        raise AssertionError(f"register() touched ctx.{item}, which the validator stub does not provide")


def _load_plugin():
    spec = importlib.util.spec_from_file_location("hermes_plugins.roomsmith_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "hermes_plugins.roomsmith_test"
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _manifest():
    text = (ROOT / "plugin.yaml").read_text()
    out = {"provides_tools": [], "provides_hooks": [], "provides_middleware": [], "requires_env": []}
    key = None
    for line in text.splitlines():
        if line.startswith("provides_tools:"):
            key = "provides_tools"
        elif line.startswith("provides_hooks:"):
            key = "provides_hooks"
        elif line.startswith("provides_middleware:") or line.startswith("requires_env:"):
            key = None
        elif line.strip().startswith("- ") and key:
            out[key].append(line.strip()[2:])
        elif ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"')
    return out


def test_register_matches_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    ctx = RecordingContext()
    mod.register(ctx)
    manifest = _manifest()
    assert sorted(ctx.tools) == sorted(manifest["provides_tools"])
    assert sorted(ctx.hooks) == sorted(manifest["provides_hooks"])
    assert "room" in ctx.commands
    assert "room-design" in ctx.skills
    assert manifest["name"] == "roomsmith"
    assert manifest["requires_hermes"].startswith(">=")
    for name, t in ctx.tools.items():
        assert t["toolset"] == "roomsmith"
        assert t["schema"]["name"] == name
        assert t["schema"]["parameters"]["type"] == "object"
        assert len(t["description"]) <= 160
        json.dumps(t["schema"])  # serialisable


def test_catalog_draft_matches_manifest():
    """catalog/roomsmith.yaml (the one-file PR) must say the same as plugin.yaml."""
    try:
        import yaml  # Hermes ships PyYAML; optional here
    except ImportError:
        pytest.skip("pyyaml not installed")
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    entry = yaml.safe_load((ROOT / "catalog" / "roomsmith.yaml").read_text())
    assert entry["name"] == manifest["name"] == "roomsmith"
    assert entry["version"] == manifest["version"]
    assert entry["requires_hermes"] == manifest["requires_hermes"]
    assert entry["repo"] == manifest["homepage"]
    assert entry["maintainer"] == manifest["author"]
    caps = entry["capabilities"]
    for k in ("provides_tools", "provides_hooks", "provides_middleware", "requires_env"):
        assert sorted(caps[k]) == sorted(manifest[k]), k
    assert len(entry["sha"]) == 40 or entry["sha"] == "<SHA>"
    assert len(entry["description"]) <= 600


def test_tool_round_trip_through_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    call = lambda tool, **args: json.loads(ctx.tools[tool]["handler"](args, task_id="t", session_id="s1"))  # noqa: E731

    r = call("roomsmith_new_room", name="Study", width_m=3.5, depth_m=4.0, height_m=2.6)
    assert r["ok"] and r["revision"] == 1 and r["calibration"] == "calibrated"
    rev = r["revision"]
    r = call(
        "roomsmith_apply",
        expected_revision=rev,
        operations=[
            {"op": "add_opening", "wall_id": "left", "kind": "door", "position_fraction": 0.5, "width_m": 0.9},
            {"op": "add_object", "name": "Desk", "category": "desk", "place": {"against_wall": "back", "align": "center"}},
            {"op": "add_object", "name": "Chair", "category": "chair", "place": {"next_to": "ob1", "side": "front", "gap_m": 0.05}},
        ],
    )
    assert r["ok"], r
    assert r["results"][1]["created_id"] == "ob1"
    r = call("roomsmith_inspect")
    assert r["ok"] and len(r["objects"]) == 2 and "Desk" in r["text"]
    stale = call("roomsmith_apply", expected_revision=1, operations=[{"op": "set_room_height", "height_m": 2.7}])
    assert stale["error"]["code"] == "revision_conflict"
    r = call("roomsmith_check", question="where_fits", dimensions_m=[0.8, 2.0, 0.3])
    assert r["ok"] and r["found"] >= 1
    r = call("roomsmith_add_product", title="BILLY bookcase", dimensions_text="Width: 80 cm, Depth: 28 cm, Height: 202 cm", url="https://example.com/billy", place={"against_wall": "right", "align": "left"})
    assert r["ok"] and r["object"]["dimensions_m"] == [0.8, 2.02, 0.28]
    r = call("roomsmith_history", action="undo")
    assert r["ok"] and len(r["objects"]) == 2
    r = call("roomsmith_history", action="list")
    assert r["ok"] and r["revisions"][0]["actor"] == "agent"
    r = call("roomsmith_export", format="glb")
    assert r["ok"] and Path(r["path"]).stat().st_size > 100
    r = call("roomsmith_projects")
    assert r["ok"] and r["projects"][0]["name"] == "Study"
    # bad input never raises
    r = call("roomsmith_apply", operations="nope")
    assert r["ok"] is False
    r = ctx.tools["roomsmith_apply"]["handler"](None)
    assert json.loads(r)["ok"] is False
    assert "Study" in ctx.commands["room"]("")


def test_awareness_hook_only_after_tool_use(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    hook = ctx.hooks["pre_llm_call"][0]
    assert hook(session_id="fresh") is None
    call = lambda tool, **args: json.loads(ctx.tools[tool]["handler"](args, session_id="s9"))  # noqa: E731
    call("roomsmith_new_room", name="Bedroom", width_m=4, depth_m=4)
    assert hook(session_id="s9") is None  # nothing unseen: the agent made the room
    svc = tools.get_service()
    svc.apply({"actor": "user", "operations": [{"op": "add_object", "name": "Bed", "category": "bed_double"}]})
    svc.apply({"actor": "user", "operations": [{"op": "move_object", "id": "ob1", "place": {"against_wall": "w1"}}]})
    out = hook(session_id="s9")
    assert out and "Bed" in out["context"] and "revision 3" in out["context"]
    assert hook(session_id="s9") is None  # marked seen
    assert hook(session_id="other") is None


def test_the_agent_is_told_what_the_user_selected_once(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    hook = ctx.hooks["pre_llm_call"][0]
    call = lambda tool, **args: json.loads(ctx.tools[tool]["handler"](args, session_id="s1"))  # noqa: E731
    call("roomsmith_new_room", name="Study", width_m=4, depth_m=4)
    call("roomsmith_apply", operations=[{"op": "add_object", "name": "Armchair", "category": "armchair"}, {"op": "add_object", "name": "Desk", "category": "desk"}])
    svc = tools.get_service()
    assert hook(session_id="s1") is None  # nothing selected yet
    assert svc.set_selection(None, "object", "ob1")["selected"]["id"] == "ob1"
    assert hook(session_id="never-used-roomsmith") is None
    out = hook(session_id="s1")
    assert out and "'Armchair' (ob1) selected" in out["context"] and out["context"].count("\n") == 0
    assert hook(session_id="s1") is None  # said once
    assert call("roomsmith_inspect")["selected"] == {"kind": "object", "id": "ob1", "name": "Armchair"}
    svc.set_selection(None, "object", "ob2")
    assert "'Desk' (ob2)" in hook(session_id="s1")["context"]
    svc.set_selection(None, "object", "ob99")  # unknown id clears
    assert svc.selection(None) is None and hook(session_id="s1") is None
    svc.set_selection(None, "object", "ob2")
    hook(session_id="s1")
    svc.apply({"actor": "user", "operations": [{"op": "remove_object", "id": "ob2"}]})
    assert svc.selection(None) is None  # the selected thing is gone
    svc.set_selection(None, "object", "ob1")
    import time

    assert svc.selection(None, now=time.time() + 16 * 60) is None  # stale
    assert svc.set_selection(None, "galaxy", "ob1")["selected"] is None
    assert svc.store.head(svc.active_project_id())["revision"] == 3  # selecting never makes a revision
    tools.reset_service()


def test_a_furnishing_request_gets_the_steps_in_the_turn_where_the_model_will_see_them(tmp_path, monkeypatch):
    """Hermes loads tool descriptions lazily and skills on request, so "furnish it" must
    carry the procedure itself (found in a live run: the model added generic furniture
    without asking for a budget)."""
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    hook = ctx.hooks["pre_llm_call"][0]
    call = lambda tool, **args: json.loads(ctx.tools[tool]["handler"](args, session_id="s1"))  # noqa: E731
    # a session that never used Roomsmith: silent on money talk, speaks only for a plain furnishing request
    assert hook(session_id="cold", user_message="what is my budget for groceries, under $200?") is None
    cold = hook(session_id="cold", user_message="Can you furnish my bedroom?")
    assert cold and "ASK the user for their budget" in cold["context"]
    r = call("roomsmith_new_room", name="Bedroom", width_m=3.4, depth_m=4.2)
    assert "set_budget" in r["to_furnish"] and "ask for their budget" in r["to_furnish"]
    assert hook(session_id="s1", user_message="make the room 10 cm wider") is None
    out = hook(session_id="s1", user_message="furnish it")["context"]
    assert "REAL products" in out and "ASK the user for their budget now" in out and "buffer" in out and "roomsmith_shortlist" in out and "never invent a URL" in out
    assert out.count("\n") <= 6
    call("roomsmith_apply", operations=[{"op": "set_budget", "limit": 1000, "currency": "USD"}])
    out = hook(session_id="s1", user_message=[{"type": "text", "text": "ok, 1,000 dollars, warm minimalist"}, {"type": "image", "data": "..."}])["context"]
    assert "Budget USD 1,000" in out and "ASK the user" not in out
    assert "to_furnish" not in call("roomsmith_inspect")
    # the labels the model sees before it describes any tool point furnishing at the right tool
    labels = {n: ctx.tools[n]["description"] for n in ctx.tools}
    assert "furnish" in labels["roomsmith_apply"].lower() and "shortlist" in labels["roomsmith_apply"]
    assert labels["roomsmith_shortlist"].lower().startswith("furnishing or shopping")
    tools.reset_service()


def test_a_size_the_agent_chose_is_an_estimate_and_a_size_the_user_gave_is_stated(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    from rs_agent import tools

    tools.reset_service()
    json.loads(tools.new_room({"name": "Room", "width_m": 4, "depth_m": 4}))
    r = json.loads(tools.apply({"operations": [
        {"op": "add_object", "name": "Wardrobe", "category": "wardrobe", "dimensions_m": [1.5, 2.0, 0.6]},
        {"op": "add_object", "name": "Sofa", "category": "sofa", "dimensions_m": [2.1, 0.8, 0.9], "dims_source": "stated"},
        {"op": "add_object", "name": "Chair", "category": "chair"},
    ]}))
    assert r["ok"], r
    objs = {o["name"]: o["provenance"]["dims_source"] for o in tools.get_service().scene(None)["scene"]["objects"]}
    assert objs == {"Wardrobe": "estimated", "Sofa": "stated", "Chair": "estimated"}
    p = tools.get_service().add_product(None, title="Desk", dimensions_m=[1.0, 0.75, 0.5], actor="agent")
    assert p["ok"] and tools.get_service().scene(None)["scene"]["objects"][-1]["provenance"]["dims_source"] == "stated"
    tools.reset_service()


def test_from_photo_without_llm_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    # a tiny valid JPEG header is enough for the sniffer; Pillow may fail and we keep bytes as-is
    img = tmp_path / "room.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9")

    class NoLlmCtx:
        pass

    mod._ctx = NoLlmCtx()
    r = json.loads(ctx.tools["roomsmith_from_photo"]["handler"]({"images": [str(img)], "name": "Fallback"}))
    assert r["ok"] and r["name"] == "Fallback"
    assert any("default room" in n for n in r["notes"])
    assert r["photos"]


def test_from_photo_with_fake_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOMSMITH_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    img = tmp_path / "room.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    draft = json.loads((ROOT / "fixtures" / "drafts" / "living_room_basic.json").read_text())
    seen = {}

    class Result:
        parsed = draft
        text = json.dumps(draft)

    class Llm:
        def complete_structured(self, **kw):
            seen.update(kw)
            return Result()

    class Ctx:
        llm = Llm()

    mod._ctx = Ctx()
    r = json.loads(ctx.tools["roomsmith_from_photo"]["handler"]({"images": [str(img)], "name": "Living", "notes": "the sofa is 2.1 m"}))
    assert r["ok"], r
    assert len(r["objects"]) == len(draft["objects"])
    assert seen["json_schema"]["type"] == "object"
    assert any(b.get("type") == "image" for b in seen["input"])
    assert "2.1 m" in seen["input"][0]["text"]
    assert "estimated" in r["next_step"]
