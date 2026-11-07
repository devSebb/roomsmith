"""Route A: the plugin reads photos through the host's model (ctx.llm).

Steps: locate the files (paths or photo ids) -> sniff and size-check ->
normalise with Pillow if available (EXIF rotation, long side 1568 px, JPEG)
-> one structured completion with the draft schema -> build the scene in
code -> save as revision 1. Every failure falls down the ladder in the plan
(section 9) and the tool still returns a room whenever a project could be made.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from rs_core import layout
from rs_core.service import RoomService, sniff_image

MAX_BYTES = 15 * 1024 * 1024
LONG_SIDE = 1568
MAX_IMAGES = 4


def _load_image(svc: RoomService, ref: str) -> tuple[bytes, str, str] | dict:
    """Return (bytes, mime, label) or an error dict."""
    p = svc.photo_path(ref)
    if p is None:
        p = Path(str(ref)).expanduser()
    if not p.is_file():
        return {"code": "not_found", "message": f"No image file at {ref!r}. Give a path to a JPEG/PNG/WebP file, or a photo id from the editor."}
    data = p.read_bytes()
    if len(data) > MAX_BYTES:
        return {"code": "too_large", "message": f"{p.name} is over 15 MB"}
    kind = sniff_image(data)
    if kind is None:
        hint = " HEIC is not supported yet; export as JPEG first." if p.suffix.lower() in (".heic", ".heif") else ""
        return {"code": "unsupported_format", "message": f"{p.name} is not a JPEG, PNG or WebP image.{hint}"}
    data, mime = _normalise(data, kind)
    return data, mime, p.name


def _normalise(data: bytes, kind: str) -> tuple[bytes, str]:
    try:
        from PIL import Image, ImageOps  # optional; Hermes ships Pillow

        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        w, h = im.size
        scale = LONG_SIDE / max(w, h)
        if scale < 1:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[kind]


def _ask(llm: Any, images: list[tuple[bytes, str, str]], notes: str, schema: dict, max_tokens: int) -> dict | None:
    """One structured call. Returns the parsed draft or None."""
    blocks: list[dict] = [{"type": "text", "text": layout.DRAFT_INSTRUCTIONS + (f"\n\nWhat the user said about the room: {notes}" if notes else "")}]
    for data, mime, name in images:
        blocks.append({"type": "image", "data": data, "mime_type": mime, "file_name": name})
    blocks.append({"type": "text", "text": "Return the JSON now."})
    result = llm.complete_structured(
        instructions="You estimate room geometry and furniture from photos and answer only with JSON matching the schema.",
        input=blocks,
        json_schema=schema,
        schema_name="room_draft",
        purpose="room-studio:photo-to-room",
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=120,
    )
    parsed = getattr(result, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    text = getattr(result, "text", None)
    if isinstance(text, str) and text.strip():
        try:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def room_from_photos(svc: RoomService, ctx: Any, args: dict) -> dict:
    refs = args.get("images") or args.get("image") or []
    if isinstance(refs, str):
        refs = [refs]
    refs = [str(r) for r in refs][:MAX_IMAGES]
    if not refs:
        return {"ok": False, "error": {"code": "missing_field", "message": "Give at least one image path or photo id."}}
    name = (args.get("name") or "").strip() or "Room from photo"
    notes = str(args.get("notes") or "").strip()

    images: list[tuple[bytes, str, str]] = []
    problems: list[dict] = []
    for ref in refs:
        loaded = _load_image(svc, ref)
        if isinstance(loaded, dict):
            problems.append(loaded)
        else:
            images.append(loaded)
    if not images:
        return {"ok": False, "error": {"code": "no_readable_images", "message": "; ".join(p["message"] for p in problems), "problems": problems}}

    llm = getattr(ctx, "llm", None) if ctx is not None else None
    ladder: list[str] = []
    draft: dict | None = None
    if llm is None:
        ladder.append("The plugin could not reach the Hermes model from this host; built a default room instead.")
    else:
        try:
            draft = _ask(llm, images, notes, layout.DRAFT_JSON_SCHEMA, 4000)
            if draft is None:
                ladder.append("First read returned no usable JSON; retried with a smaller schema.")
                draft = _ask(llm, images, notes, layout.DRAFT_JSON_SCHEMA_SMALL, 2000)
                if draft is None:
                    ladder.append("Second read failed too; built a default 4 x 5 m room.")
        except Exception as e:  # noqa: BLE001 - any provider error ends in a default room
            msg = f"{type(e).__name__}: {e}"
            if "image" in msg.lower() or "vision" in msg.lower() or "multimodal" in msg.lower():
                ladder.append(f"The active model could not read the image ({msg}). Built a default room; ask the user for the room size instead.")
            else:
                ladder.append(f"Model call failed ({msg}); built a default room.")
            draft = None

    out = svc.create_project(name, draft=draft if draft is not None else {}, actor="agent")
    if not out.get("ok"):
        return out
    pid = out["project_id"]
    registered = []
    for ref in refs:
        p = svc.photo_path(ref) or Path(ref).expanduser()
        if p.is_file():
            r = svc.register_photo(p, project_id=pid)
            if r.get("ok"):
                registered.append(r["photo_id"])
    out["photos"] = registered
    out["notes"] = (out.get("notes") or []) + ladder + [p["message"] for p in problems]
    if draft:
        out["draft"] = {k: draft.get(k) for k in ("scale_anchors", "walls_visible", "notes") if draft.get(k)}
        out["next_step"] = "This is a draft with estimated sizes. Ask the user for one real measurement (a wall length or the door width) and calibrate with room_studio_apply."
    else:
        out["next_step"] = "No draft could be read from the photo. Ask the user for the room's width, depth and the main furniture, then add them with room_studio_apply."
    keep = {k: out[k] for k in ("ok", "project_id", "name", "revision", "text", "issues", "notes", "photos", "draft", "next_step", "room", "objects") if k in out}
    return keep
