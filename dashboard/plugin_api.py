"""Roomsmith backend routes. Mounted by Hermes at /api/plugins/roomsmith/.

This file is imported standalone by the dashboard (not as part of a package),
so it uses no relative imports. It puts the plugin root on sys.path and uses
the same rs_core engine and the same database as the agent tools. The agent
tools may run in another process; SQLite is the shared state.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from rs_agent import paths  # noqa: E402
from rs_core import __version__  # noqa: E402
from rs_core.media import IMAGE_MIME  # noqa: E402
from rs_core.service import RoomService, new_command_id  # noqa: E402

router = APIRouter()

_service: RoomService | None = None


def _svc() -> RoomService:
    global _service
    if _service is None:
        _service = RoomService(paths.db_path(), paths.data_dir())
    return _service


def _reply(result: dict, ok_status: int = 200) -> JSONResponse:
    if result.get("ok"):
        return JSONResponse(result, status_code=ok_status)
    code = (result.get("error") or {}).get("code", "")
    status = {
        "not_found": 404,
        "no_active_room": 404,
        "revision_conflict": 409,
        "invalid_value": 400,
        "missing_field": 400,
        "out_of_range": 400,
        "unknown_id": 400,
        "unknown_op": 400,
        "locked": 409,
        "too_large": 413,
        "unsupported_format": 415,
    }.get(code, 400)
    return JSONResponse(result, status_code=status)


def _steps(body: dict) -> int:
    try:
        return max(1, int(body.get("steps") or 1))
    except (TypeError, ValueError):
        return 1


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


# ------------------------------------------------------------------ health


@router.get("/health")
async def health():
    try:
        return _svc().health()
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": {"code": "internal", "message": str(e)}}, status_code=500)


# ------------------------------------------------------------------ projects


@router.get("/projects")
async def list_projects():
    return _reply(_svc().list_projects())


@router.post("/projects")
async def create_project(request: Request):
    body = await _json_body(request)
    if isinstance(body.get("import"), dict):
        return _reply(_svc().import_json(body["import"], name=body.get("name"), actor="user"), 201)
    draft = body.get("layout") if isinstance(body.get("layout"), dict) else None
    out = _svc().create_project(body.get("name"), body.get("width_m"), body.get("depth_m"), body.get("height_m"), draft=draft, actor="user")
    return _reply(out, 201)


@router.post("/projects/{project_id}/activate")
async def activate(project_id: str):
    return _reply(_svc().activate(project_id))


@router.patch("/projects/{project_id}")
async def rename(project_id: str, request: Request):
    body = await _json_body(request)
    return _reply(_svc().rename(project_id, str(body.get("name") or "")))


@router.delete("/projects/{project_id}")
async def delete(project_id: str):
    return _reply(_svc().delete(project_id))


# ------------------------------------------------------------------ reads


@router.get("/projects/{project_id}/head")
async def head(project_id: str):
    return _reply(_svc().head(project_id))


@router.get("/projects/{project_id}/scene")
async def scene(project_id: str, revision: int | None = None):
    return _reply(_svc().scene(project_id, revision))


@router.get("/projects/{project_id}/history")
async def history(project_id: str, limit: int = 30):
    return _reply(_svc().history(project_id, limit))


# ------------------------------------------------------------------ writes


@router.post("/projects/{project_id}/commands")
async def commands(project_id: str, request: Request):
    body = await _json_body(request)
    command = {
        "project_id": project_id,
        "expected_revision": body.get("expected_revision"),
        "command_id": body.get("command_id") or new_command_id(),
        "actor": "user",  # this API is the editor; only the agent's tools write as "agent"
        "operations": body.get("operations"),
    }
    return _reply(_svc().apply(command))


@router.post("/projects/{project_id}/undo")
async def undo(project_id: str, request: Request):
    body = await _json_body(request)
    return _reply(_svc().undo(project_id, _steps(body), actor="user"))


@router.post("/projects/{project_id}/redo")
async def redo(project_id: str, request: Request):
    body = await _json_body(request)
    return _reply(_svc().redo(project_id, _steps(body), actor="user"))


@router.post("/projects/{project_id}/check")
async def check(project_id: str, request: Request):
    body = await _json_body(request)
    return _reply(
        _svc().check(
            project_id,
            question=str(body.get("question") or "issues"),
            dimensions_m=body.get("dimensions_m"),
            place=body.get("place") if isinstance(body.get("place"), dict) else None,
            opening_id=body.get("opening_id"),
            object_id=body.get("object_id"),
            name=str(body.get("name") or "candidate"),
        )
    )


@router.post("/projects/{project_id}/products")
async def add_product(project_id: str, request: Request):
    body = await _json_body(request)
    return _reply(
        _svc().add_product(
            project_id,
            title=str(body.get("title") or ""),
            dimensions_text=body.get("dimensions_text"),
            dimensions_m=body.get("dimensions_m"),
            url=body.get("url"),
            image_url=body.get("image_url"),
            price=body.get("price"),
            category=body.get("category"),
            color=body.get("color"),
            place=body.get("place") if isinstance(body.get("place"), dict) else None,
            expected_revision=body.get("expected_revision"),
            actor="user",
            command_id=body.get("command_id") or new_command_id(),
        )
    )


# ------------------------------------------------------------------ photos


@router.post("/photos")
async def upload_photo(request: Request):
    """Raw image bytes in the body (image/jpeg, image/png, image/webp)."""
    data = await request.body()
    return _reply(_svc().save_photo_bytes(data, project_id=request.query_params.get("project_id") or None), 201)


@router.get("/photos/{photo_id}")
async def get_photo(photo_id: str):
    p = _svc().photo_path(photo_id)
    if p is None or not p.is_file():
        return JSONResponse({"ok": False, "error": {"code": "not_found", "message": "No such photo"}}, status_code=404)
    data = p.read_bytes()
    mime = IMAGE_MIME.get(p.suffix.lstrip("."), "application/octet-stream")
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


# ------------------------------------------------------------------ export


@router.get("/projects/{project_id}/export")
async def export(project_id: str, format: str = "glb", encoding: str | None = None):
    out = _svc().export_bytes(project_id, format if format in ("glb", "json", "summary") else "glb")
    if isinstance(out, dict):
        return _reply(out)
    data, mime, filename = out
    if encoding == "base64":
        # for hosts whose REST client only speaks JSON (Hermes Desktop's ctx.rest)
        import base64

        return JSONResponse({"ok": True, "filename": filename, "mime": mime, "bytes": len(data), "base64": base64.b64encode(data).decode("ascii")})
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ------------------------------------------------------------------ events (long poll)


@router.get("/projects/{project_id}/wait")
async def wait_for_change(project_id: str, after: int = 0, timeout: float = 25.0, active: str | None = None):
    """Long-poll: returns as soon as the head revision passes `after`, or after
    `timeout` seconds with the current head. Cheaper than polling every second.

    `active` is the active room id the client last saw; when the agent opens or
    creates another room the active id changes and the poll returns at once with
    `active_changed: true` so the editor can follow."""
    import asyncio

    svc = _svc()
    deadline = time.monotonic() + max(0.0, min(float(timeout), 55.0))
    while True:
        h = svc.head(project_id)
        if not h.get("ok"):
            return _reply(h)
        current_active = svc.active_project_id()
        active_changed = active is not None and current_active is not None and current_active != active
        if int(h["revision"]) > int(after) or active_changed or time.monotonic() >= deadline:
            h["changed"] = int(h["revision"]) > int(after)
            h["active_project_id"] = current_active
            h["active_changed"] = active_changed
            return JSONResponse(h)
        await asyncio.sleep(0.5)
