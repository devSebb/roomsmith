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
    spec = importlib.util.spec_from_file_location("hermes_plugins.room_studio_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "hermes_plugins.room_studio_test"
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
    monkeypatch.setenv("ROOM_STUDIO_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    ctx = RecordingContext()
    mod.register(ctx)
    manifest = _manifest()
    assert sorted(ctx.tools) == sorted(manifest["provides_tools"])
    assert sorted(ctx.hooks) == sorted(manifest["provides_hooks"])
    assert "room" in ctx.commands
    assert "room-design" in ctx.skills
    assert manifest["name"] == "room-studio"
    assert manifest["requires_hermes"].startswith(">=")
    for name, t in ctx.tools.items():
        assert t["toolset"] == "room_studio"
        assert t["schema"]["name"] == name
        assert t["schema"]["parameters"]["type"] == "object"
        assert len(t["description"]) <= 160
        json.dumps(t["schema"])  # serialisable


def test_tool_round_trip_through_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOM_STUDIO_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    call = lambda tool, **args: json.loads(ctx.tools[tool]["handler"](args, task_id="t", session_id="s1"))  # noqa: E731

    r = call("room_studio_new_room", name="Study", width_m=3.5, depth_m=4.0, height_m=2.6)
    assert r["ok"] and r["revision"] == 1 and r["calibration"] == "calibrated"
    rev = r["revision"]
    r = call(
        "room_studio_apply",
        expected_revision=rev,
        operations=[
            {"op": "add_opening", "wall_id": "left", "kind": "door", "position_fraction": 0.5, "width_m": 0.9},
            {"op": "add_object", "name": "Desk", "category": "desk", "place": {"against_wall": "back", "align": "center"}},
            {"op": "add_object", "name": "Chair", "category": "chair", "place": {"next_to": "ob1", "side": "front", "gap_m": 0.05}},
        ],
    )
    assert r["ok"], r
    assert r["results"][1]["created_id"] == "ob1"
    r = call("room_studio_inspect")
    assert r["ok"] and len(r["objects"]) == 2 and "Desk" in r["text"]
    stale = call("room_studio_apply", expected_revision=1, operations=[{"op": "set_room_height", "height_m": 2.7}])
    assert stale["error"]["code"] == "revision_conflict"
    r = call("room_studio_check", question="where_fits", dimensions_m=[0.8, 2.0, 0.3])
    assert r["ok"] and r["found"] >= 1
    r = call("room_studio_add_product", title="BILLY bookcase", dimensions_text="Width: 80 cm, Depth: 28 cm, Height: 202 cm", url="https://example.com/billy", place={"against_wall": "right", "align": "left"})
    assert r["ok"] and r["object"]["dimensions_m"] == [0.8, 2.02, 0.28]
    r = call("room_studio_history", action="undo")
    assert r["ok"] and len(r["objects"]) == 2
    r = call("room_studio_history", action="list")
    assert r["ok"] and r["revisions"][0]["actor"] == "agent"
    r = call("room_studio_export", format="glb", out_dir=str(tmp_path / "exp"))
    assert r["ok"] and Path(r["path"]).stat().st_size > 100
    r = call("room_studio_projects")
    assert r["ok"] and r["projects"][0]["name"] == "Study"
    # bad input never raises
    r = call("room_studio_apply", operations="nope")
    assert r["ok"] is False
    r = ctx.tools["room_studio_apply"]["handler"](None)
    assert json.loads(r)["ok"] is False
    assert "Study" in ctx.commands["room"]("")


def test_awareness_hook_only_after_tool_use(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOM_STUDIO_DATA_DIR", str(tmp_path))
    mod = _load_plugin()
    from rs_agent import tools

    tools.reset_service()
    ctx = RecordingContext()
    mod.register(ctx)
    hook = ctx.hooks["pre_llm_call"][0]
    assert hook(session_id="fresh") is None
    call = lambda tool, **args: json.loads(ctx.tools[tool]["handler"](args, session_id="s9"))  # noqa: E731
    call("room_studio_new_room", name="Bedroom", width_m=4, depth_m=4)
    assert hook(session_id="s9") is None  # nothing unseen: the agent made the room
    svc = tools.get_service()
    svc.apply({"actor": "user", "operations": [{"op": "add_object", "name": "Bed", "category": "bed_double"}]})
    svc.apply({"actor": "user", "operations": [{"op": "move_object", "id": "ob1", "place": {"against_wall": "w1"}}]})
    out = hook(session_id="s9")
    assert out and "Bed" in out["context"] and "revision 3" in out["context"]
    assert hook(session_id="s9") is None  # marked seen
    assert hook(session_id="other") is None


def test_from_photo_without_llm_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOM_STUDIO_DATA_DIR", str(tmp_path))
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
    r = json.loads(ctx.tools["room_studio_from_photo"]["handler"]({"images": [str(img)], "name": "Fallback"}))
    assert r["ok"] and r["name"] == "Fallback"
    assert any("default room" in n for n in r["notes"])
    assert r["photos"]


def test_from_photo_with_fake_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOM_STUDIO_DATA_DIR", str(tmp_path))
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
    r = json.loads(ctx.tools["room_studio_from_photo"]["handler"]({"images": [str(img)], "name": "Living", "notes": "the sofa is 2.1 m"}))
    assert r["ok"], r
    assert len(r["objects"]) == len(draft["objects"])
    assert seen["json_schema"]["type"] == "object"
    assert any(b.get("type") == "image" for b in seen["input"])
    assert "2.1 m" in seen["input"][0]["text"]
    assert "estimated" in r["next_step"]
