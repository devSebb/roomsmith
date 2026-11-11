"""Tool handlers. Each takes (args: dict, **kwargs) and returns a JSON string.
Handlers never raise: every failure is a JSON error the model can act on.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

from rs_agent import paths
from rs_core.service import RoomService, new_command_id

_service: RoomService | None = None
_service_lock = threading.Lock()
_sessions_using_rooms: set[str] = set()


def get_service() -> RoomService:
    """One service per process, opened lazily (never during register())."""
    global _service
    with _service_lock:
        if _service is None:
            _service = RoomService(paths.db_path(), paths.data_dir())
        return _service


def reset_service() -> None:
    global _service
    with _service_lock:
        if _service is not None:
            try:
                _service.close()
            except Exception:
                pass
        _service = None


def note_session(kwargs: dict) -> None:
    sid = kwargs.get("session_id")
    if sid:
        _sessions_using_rooms.add(str(sid))


def session_uses_rooms(session_id: str | None) -> bool:
    return bool(session_id) and str(session_id) in _sessions_using_rooms


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _guard(fn: Callable[[dict, dict], Any]) -> Callable[..., str]:
    def wrapper(args: dict | None = None, **kwargs: Any) -> str:
        args = args if isinstance(args, dict) else {}
        try:
            note_session(kwargs)
            out = fn(args, kwargs)
            return out if isinstance(out, str) else _dump(out)
        except Exception as e:  # noqa: BLE001 - tools must never raise
            return _dump({"ok": False, "error": {"code": "internal", "message": f"{type(e).__name__}: {e}"}})

    wrapper.__name__ = fn.__name__
    return wrapper


def _int(value: Any, default: int) -> int:
    """A count from the model: 2, "2" or 2.0; anything else falls back to the default."""
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


def _obj(value: Any) -> dict | None:
    """An object argument, also accepted as a JSON string (some models send one)."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def _operations(value: Any) -> Any:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value  # the service reports it as invalid
    return [value] if isinstance(value, dict) else value


def _without_image_data(scene: dict) -> dict:
    """The full scene minus embedded product thumbnails (base64, tens of kilobytes each)."""
    objects = []
    for o in scene.get("objects", []):
        product = o.get("product")
        if isinstance(product, dict) and "image_data" in product:
            o = {**o, "product": {k: v for k, v in product.items() if k != "image_data"}}
        objects.append(o)
    return {**scene, "objects": objects}


def _trim_inspect(out: dict) -> dict:
    """Keep inspect replies compact for the model: text first, numbers second."""
    if not out.get("ok"):
        return out
    keep = {k: out[k] for k in ("ok", "project_id", "name", "revision", "can_undo", "can_redo", "text", "issues", "created", "notes", "steps", "summary") if k in out}
    keep["room"] = out.get("room")
    keep["objects"] = out.get("objects")
    keep["calibration"] = (out.get("calibration") or {}).get("status")
    if "scene" in out:
        keep["scene"] = _without_image_data(out["scene"])
    keep["editor_hint"] = EDITOR_HINT
    return keep


EDITOR_HINT = "The user can open this room in Hermes Desktop (Roomsmith pane) or the dashboard's Roomsmith tab; edits there show up here."


@_guard
def projects(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    action = str(args.get("action") or "list").lower()
    if action == "list":
        out = svc.list_projects()
        out["editor_hint"] = EDITOR_HINT
        return out
    if action == "activate":
        return svc.activate(args.get("project_id") or "")
    if action == "rename":
        return svc.rename(args.get("project_id"), args.get("name") or "")
    if action == "delete":
        return svc.delete(args.get("project_id"))
    return {"ok": False, "error": {"code": "invalid_value", "message": "action must be list, activate, rename or delete"}}


@_guard
def new_room(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    layout = _obj(args.get("layout"))
    out = svc.create_project(args.get("name"), args.get("width_m"), args.get("depth_m"), args.get("height_m"), draft=layout, actor="agent")
    if out.get("ok") and args.get("photo_ids"):
        svc.attach_photos(out["project_id"], [str(p) for p in args["photo_ids"]])
    if out.get("ok") and layout is not None:
        out["next_step"] = "Sizes are estimates. Ask the user for one real measurement (a wall length or the door width) and calibrate."
    return _trim_inspect(out)


@_guard
def inspect(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    out = svc.inspect(args.get("project_id"), detail=str(args.get("detail") or "summary"), mark_seen=True)
    return _trim_inspect(out)


@_guard
def apply(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    command = {
        "project_id": args.get("project_id"),
        "expected_revision": args.get("expected_revision"),
        "command_id": new_command_id(),
        "actor": "agent",
        "operations": _operations(args.get("operations")),
    }
    out = svc.apply(command)
    if out.get("ok"):
        out.pop("project_id", None)
    return out


@_guard
def check(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    return svc.check(
        args.get("project_id"),
        question=str(args.get("question") or "issues"),
        dimensions_m=args.get("dimensions_m"),
        place=_obj(args.get("place")),
        opening_id=args.get("opening_id"),
        object_id=args.get("object_id"),
        name=str(args.get("name") or "candidate"),
    )


@_guard
def add_product(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    return svc.add_product(
        args.get("project_id"),
        title=str(args.get("title") or ""),
        dimensions_text=args.get("dimensions_text"),
        dimensions_m=args.get("dimensions_m"),
        url=args.get("url"),
        image_url=args.get("image_url"),
        price=args.get("price"),
        category=args.get("category"),
        color=args.get("color"),
        place=_obj(args.get("place")),
        expected_revision=args.get("expected_revision"),
        actor="agent",
        command_id=new_command_id(),
    )


@_guard
def read_product(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    return svc.read_product(str(args.get("url") or ""), category=args.get("category"))


@_guard
def history(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    action = str(args.get("action") or "list").lower()
    steps = _int(args.get("steps"), 1)
    if action == "undo":
        return _trim_inspect(svc.undo(args.get("project_id"), steps, actor="agent"))
    if action == "redo":
        return _trim_inspect(svc.redo(args.get("project_id"), steps, actor="agent"))
    return svc.history(args.get("project_id"), limit=_int(args.get("limit"), 10))


@_guard
def export(args: dict, kwargs: dict) -> dict:
    svc = get_service()
    return svc.export(args.get("project_id"), fmt=str(args.get("format") or "glb"))


def from_photo_handler(ctx_getter: Callable[[], Any]) -> Callable[..., str]:
    """Built with a getter for the plugin context so ctx.llm is read at call time."""

    @_guard
    def from_photo(args: dict, kwargs: dict) -> dict:
        from rs_agent import photo

        return photo.room_from_photos(get_service(), ctx_getter(), args)

    return from_photo


def slash_room(raw_args: str = "") -> str:
    """The /room command: a one-screen status of the active room."""
    try:
        svc = get_service()
        arg = (raw_args or "").strip()
        if arg:
            res = svc.activate(arg)
            if not res.get("ok"):
                return res["error"]["message"]
        out = svc.inspect(None)
        if not out.get("ok"):
            lst = svc.list_projects()
            if lst["projects"]:
                names = ", ".join(f"{p['name']} ({p['project_id'][:8]})" for p in lst["projects"])
                return f"No active room. Rooms: {names}. Use /room <name> to switch."
            return "No rooms yet. Say 'make a 4 by 5 metre room' or attach a photo and ask for a room."
        issues = [i for i in out["issues"] if i["code"] != "uncalibrated"]
        lines = [out["text"].split("\n")[0], f"Revision {out['revision']}; {len(out['objects'])} objects; {len(issues)} issue(s)."]
        for i in issues[:5]:
            lines.append(f"  - {i['message']}")
        lines.append(EDITOR_HINT)
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        return f"Roomsmith error: {e}"
