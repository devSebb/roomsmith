"""The application service. Tools, the dashboard backend and tests all call this
and nothing else. Every method returns JSON-serialisable dicts and never raises
for user-level errors: failures come back as ``{"ok": False, "error": {...}}``.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from rs_core import dims as dims_mod
from rs_core import export_glb, fitcheck, layout, ops, summarize, validate
from rs_core import model as m
from rs_core.model import SceneError
from rs_core.store import NotFound, RevisionConflict, Store

ACTORS = ("user", "agent", "system")


def _err(code: str, message: str, **extra: Any) -> dict:
    e = {"code": code, "message": message}
    e.update(extra)
    return {"ok": False, "error": e}


class RoomService:
    def __init__(self, db_path: str | Path, data_dir: str | Path | None = None):
        self.db_path = Path(db_path)
        self.data_dir = Path(data_dir) if data_dir else self.db_path.parent
        self.store = Store(self.db_path)
        (self.data_dir / "photos").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "exports").mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.store.close()

    # ------------------------------------------------------------ helpers

    def _resolve_project(self, project_id: str | None) -> str | None:
        if project_id:
            try:
                self.store.get_project(project_id)
                return project_id
            except NotFound:
                # allow a name match as a convenience
                for p in self.store.list_projects():
                    if p["name"].lower() == str(project_id).lower():
                        return p["id"]
                return None
        return self.store.active_project_id()

    def _no_project(self, project_id: str | None) -> dict:
        if project_id:
            return _err("not_found", f"No room {project_id!r}. Call roomsmith_projects to list rooms.")
        return _err("no_active_room", "There is no room yet. Create one with roomsmith_new_room or roomsmith_from_photo.")

    @staticmethod
    def _actor(actor: str | None) -> str:
        a = (actor or "agent").lower()
        return a if a in ACTORS else "agent"

    def _head_block(self, project_id: str) -> dict:
        h = self.store.head(project_id)
        return {"project_id": project_id, "name": h["name"], "revision": h["revision"], "updated_at": h["updated_at"], "actor": h["actor"], "summary": h["summary"], "changed_ids": h["changed_ids"]}

    # ------------------------------------------------------------ projects

    def list_projects(self) -> dict:
        active = self.store.active_project_id()
        rows = []
        for p in self.store.list_projects():
            try:
                scene, rev = self.store.get_scene(p["id"])
                w, d = m.room_size(scene)
                n_issues = len([i for i in validate.issues(scene) if i["code"] != "uncalibrated"])
                rows.append(
                    {
                        "project_id": p["id"],
                        "name": p["name"],
                        "revision": rev,
                        "updated_at": p["updated_at"],
                        "size_m": [round(w, 2), round(d, 2)],
                        "objects": len(scene["objects"]),
                        "issues": n_issues,
                        "calibrated": scene.get("calibration", {}).get("status") == "calibrated",
                        "active": p["id"] == active,
                    }
                )
            except NotFound:
                continue
        return {"ok": True, "active_project_id": active, "projects": rows}

    def create_project(self, name: str | None, width_m: float | None = None, depth_m: float | None = None, height_m: float | None = None, draft: dict | None = None, actor: str = "agent", activate: bool = True) -> dict:
        pid = m.new_project_id()
        name = (name or "").strip() or f"Room {time.strftime('%d %b %H:%M')}"
        notes: list[str] = []
        try:
            if draft is not None:
                scene, notes = layout.build_scene(pid, name, draft)
                summary = f"Created '{name}' from a draft with {len(scene['objects'])} objects"
            else:
                w = float(width_m) if width_m is not None else m.DEFAULT_ROOM["width_m"]
                d = float(depth_m) if depth_m is not None else m.DEFAULT_ROOM["depth_m"]
                h = float(height_m) if height_m is not None else m.DEFAULT_ROOM["height_m"]
                for v, lo, hi, field in ((w, m.ROOM_SIDE_MIN, m.ROOM_SIDE_MAX, "width_m"), (d, m.ROOM_SIDE_MIN, m.ROOM_SIDE_MAX, "depth_m"), (h, m.ROOM_HEIGHT_MIN, m.ROOM_HEIGHT_MAX, "height_m")):
                    if not math.isfinite(v) or not (lo <= v <= hi):
                        return _err("out_of_range", f"{field} must be between {lo} and {hi} m", field=field)
                scene = m.new_scene(pid, name, w, d, h)
                if width_m is not None and depth_m is not None:
                    scene["calibration"] = {"status": "calibrated", "reference": {"kind": "stated_room_size", "id": None, "real_m": w}}
                summary = f"Created '{name}' {w:g} x {d:g} x {h:g} m"
            validate.validate_hard(scene)
        except SceneError as e:
            return {"ok": False, "error": e.to_dict()}
        self.store.create_project(pid, name, m.round_scene(scene), actor=self._actor(actor), summary=summary)
        if activate:
            self.store.set_active(pid)
        out = self.inspect(pid, detail="summary")
        out["notes"] = notes
        out["created"] = True
        return out

    def activate(self, project_id: str) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        self.store.set_active(pid)
        return {"ok": True, "active_project_id": pid, "head": self._head_block(pid)}

    def rename(self, project_id: str | None, name: str) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        name = (name or "").strip()
        if not name:
            return _err("invalid_value", "name must not be empty")
        scene, rev = self.store.get_scene(pid)
        scene["project"]["name"] = name
        self.store.rename_project(pid, name)
        new_rev = self.store.commit_revision(pid, rev, scene, "system", f"Renamed to '{name}'", [], history_mode="none")
        return {"ok": True, "project_id": pid, "name": name, "revision": new_rev}

    def delete(self, project_id: str | None) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        self.store.delete_project(pid)
        return {"ok": True, "deleted": pid, "active_project_id": self.store.active_project_id()}

    # ------------------------------------------------------------ reads

    def head(self, project_id: str | None = None) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        return {"ok": True, **self._head_block(pid)}

    def scene(self, project_id: str | None = None, revision: int | None = None, with_issues: bool = True) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        try:
            scene, rev = self.store.get_scene(pid, revision)
        except NotFound as e:
            return _err("not_found", str(e))
        out = {"ok": True, "project_id": pid, "revision": rev, "scene": scene}
        if with_issues:
            out["issues"] = validate.issues(scene)
        undo, redo = self.store.history_stacks(pid)
        out["can_undo"] = bool(undo)
        out["can_redo"] = bool(redo)
        out["head"] = self._head_block(pid)
        return out

    def inspect(self, project_id: str | None = None, detail: str = "summary", mark_seen: bool = False) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        scene, rev = self.store.get_scene(pid)
        issues = validate.issues(scene)
        out = {"ok": True, "project_id": pid, "revision": rev, "name": scene["project"]["name"]}
        if detail == "full":
            out["scene"] = scene
            out["issues"] = issues
            out["summary"] = summarize.summary_text(scene, issues, rev)
        else:
            out.update(summarize.compact(scene, issues, rev))
            out["revision"] = rev
        undo, redo = self.store.history_stacks(pid)
        out["can_undo"], out["can_redo"] = bool(undo), bool(redo)
        if mark_seen:
            self.store.mark_agent_seen(pid, rev)
        return out

    # ------------------------------------------------------------ writes

    def apply(self, command: dict) -> dict:
        """Apply one atomic batch. See plan section 7 for the envelope."""
        if not isinstance(command, dict):
            return _err("invalid_value", "command must be an object")
        pid = self._resolve_project(command.get("project_id"))
        if not pid:
            return self._no_project(command.get("project_id"))
        command_id = command.get("command_id")
        if command_id:
            prior = self.store.get_command_result(str(command_id))
            if prior is not None:
                prior = dict(prior)
                prior["replayed"] = True
                return prior
        operations = command.get("operations")
        if isinstance(operations, dict):
            operations = [operations]
        actor = self._actor(command.get("actor"))
        expected = command.get("expected_revision")
        if expected is not None:
            try:
                expected = int(expected)
            except (TypeError, ValueError):
                return _err("invalid_value", "expected_revision must be an integer")

        # Read-modify-write under the database write lock, so a writer in another
        # process waits instead of racing and no update is ever lost. The commit
        # re-checks the revision it was derived from as a belt-and-braces guard.
        with self.store.write_transaction():
            try:
                scene, current = self.store.get_scene(pid)
            except NotFound as e:
                return _err("not_found", str(e))
            if expected is not None and expected != current:
                return _err("revision_conflict", f"The room changed since you last looked: you expected revision {expected}, it is {current}. Re-read it (roomsmith_inspect) and retry.", expected_revision=expected, current_revision=current)
            try:
                batch = ops.apply_operations(scene, operations)
            except SceneError as e:
                return {"ok": False, "error": e.to_dict(), "revision": current}
            new_scene = m.round_scene(batch.scene)
            who = {"agent": "Hermes", "user": "You", "system": "System"}[actor]
            summary = f"{who}: {batch.summary}"
            changed = batch.changed_ids
            issues = validate.issues(new_scene)
            touched_issues = [i for i in issues if not i["ids"] or set(i["ids"]) & set(changed)]
            result = {
                "ok": True,
                "project_id": pid,
                "results": [r.to_dict() for r in batch.results],
                "changed_ids": changed,
                "summary": batch.summary,
                "issues": touched_issues,
                "all_issue_count": len([i for i in issues if i["code"] != "uncalibrated"]),
            }
            try:
                new_rev = self.store.commit_revision(pid, current, new_scene, actor, summary, changed, command_id=str(command_id) if command_id else None, result=result)
            except RevisionConflict as e:
                return _err("revision_conflict", f"The room changed while applying: expected revision {e.expected}, it is {e.current}. Re-read and retry.", expected_revision=e.expected, current_revision=e.current)
            result["revision"] = new_rev
            if actor == "agent":
                self.store.mark_agent_seen(pid, new_rev)
            return result

    def undo(self, project_id: str | None = None, steps: int = 1, actor: str = "agent") -> dict:
        return self._step_history(project_id, steps, "undo", actor)

    def redo(self, project_id: str | None = None, steps: int = 1, actor: str = "agent") -> dict:
        return self._step_history(project_id, steps, "redo", actor)

    def _step_history(self, project_id: str | None, steps: int, mode: str, actor: str) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        steps = max(1, min(int(steps or 1), 50))
        done = 0
        last_summary = ""
        for _ in range(steps):
            with self.store.write_transaction():
                undo, redo = self.store.history_stacks(pid)
                stack = undo if mode == "undo" else redo
                if not stack:
                    break
                target = stack[-1]
                try:
                    scene, _rev = self.store.get_scene(pid, target)
                except NotFound:
                    # pruned; drop it and continue
                    break
                head = self.store.head(pid)
                label = "Undo" if mode == "undo" else "Redo"
                prev = head["summary"]
                for prefix in ("Hermes: ", "You: ", "System: "):
                    if prev.startswith(prefix):
                        prev = prev[len(prefix):]
                what = prev if mode == "undo" else f"back to revision {target}"
                summary = f"{label}: {what}"
                self.store.commit_revision(pid, head["revision"], scene, self._actor(actor), summary, head["changed_ids"], history_mode=mode, restore_revision=target)
                done += 1
                last_summary = summary
        if done == 0:
            return {"ok": False, "error": {"code": "nothing_to_" + mode, "message": f"Nothing to {mode}."}, "head": self._head_block(pid)}
        out = self.inspect(pid, detail="summary")
        out["steps"] = done
        out["summary"] = last_summary
        if self._actor(actor) == "agent":
            self.store.mark_agent_seen(pid, out["revision"])
        return out

    def history(self, project_id: str | None = None, limit: int = 20) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        undo, redo = self.store.history_stacks(pid)
        return {"ok": True, "project_id": pid, "head": self._head_block(pid), "revisions": self.store.list_revisions(pid, limit), "can_undo": bool(undo), "can_redo": bool(redo)}

    # ------------------------------------------------------------ checks

    def check(self, project_id: str | None = None, question: str = "issues", dimensions_m: list[float] | None = None, place: dict | None = None, opening_id: str | None = None, object_id: str | None = None, name: str = "candidate") -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        scene, rev = self.store.get_scene(pid)
        q = (question or "issues").lower()
        dims = None
        if object_id:
            try:
                obj = m.find_object(scene, object_id)
            except SceneError as e:
                return {"ok": False, "error": e.to_dict()}
            dims = list(obj["dimensions_m"])
            name = obj["name"]
        elif dimensions_m is not None:
            try:
                dims = ops._dims(dimensions_m)  # noqa: SLF001 (same package)
            except SceneError as e:
                return {"ok": False, "error": e.to_dict()}
        base = {"ok": True, "project_id": pid, "revision": rev, "question": q}
        if q == "issues":
            issues = validate.issues(scene)
            return {**base, "issues": issues, "count": len([i for i in issues if i["code"] != "uncalibrated"]), "text": "\n".join(f"- {i['code']}: {i['message']}" for i in issues) or "No issues."}
        if dims is None:
            return _err("missing_field", f"{q} needs dimensions_m [width, height, depth] or an object_id")
        if q == "fits_at":
            if not place:
                return _err("missing_field", "fits_at needs a place instruction, e.g. {\"against_wall\": \"w2\", \"align\": \"center\"}")
            return {**base, **fitcheck.fits_at(scene, dims, place, name, ignore_ids=[object_id] if object_id else None)}
        if q == "where_fits":
            return {**base, **fitcheck.where_fits(scene, dims, name)}
        if q == "passes_door":
            return {**base, **fitcheck.passes_door(scene, dims, opening_id)}
        if q == "clearance":
            if not object_id:
                return _err("missing_field", "clearance needs an object_id")
            return {**base, "object_id": object_id, "clearance_m": fitcheck.clearances(scene, m.find_object(scene, object_id))}
        return _err("invalid_value", "question must be one of issues, fits_at, where_fits, passes_door, clearance")

    # ------------------------------------------------------------ products

    def add_product(self, project_id: str | None, title: str, dimensions_text: str | None = None, dimensions_m: list[float] | None = None, url: str | None = None, image_url: str | None = None, price: str | None = None, category: str | None = None, color: str | None = None, place: dict | None = None, expected_revision: int | None = None, actor: str = "agent", command_id: str | None = None) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        title = (title or "").strip()
        if not title:
            return _err("missing_field", "title is required")
        parsed = None
        if dimensions_m is None and dimensions_text:
            parsed = dims_mod.parse_dimensions(dimensions_text)
            if parsed is None:
                return _err("dimensions_unreadable", f"Could not read dimensions from {dimensions_text!r}. Ask the user for width x height x depth.", dimensions_text=dimensions_text)
            if parsed.get("partial"):
                return _err("dimensions_incomplete", f"Only part of the size was readable from {dimensions_text!r}; missing {', '.join(parsed['missing'])}. Ask the user for the missing value.", parsed=parsed)
            dimensions_m = [parsed["width_m"], parsed["height_m"], parsed["depth_m"]]
        if dimensions_m is None:
            return _err("missing_field", "Give dimensions_m [width, height, depth] or dimensions_text")
        product = {
            "title": title,
            "url": url or None,
            "image_url": image_url or None,
            "price": price or None,
            "dimensions_text": dimensions_text or None,
            "assumed_order": bool(parsed and parsed.get("assumed_order")),
        }
        op: dict = {
            "op": "add_object",
            "name": title[:60],
            "category": category or title,
            "dimensions_m": dimensions_m,
            "provenance": {"class": "dimensioned_placeholder", "dims_source": "stated", "confidence": 0.9},
            "product": product,
        }
        if color:
            op["color"] = color
        if place:
            op["place"] = place
        res = self.apply({"project_id": pid, "expected_revision": expected_revision, "actor": actor, "operations": [op], "command_id": command_id})
        if not res.get("ok"):
            return res
        created = res["results"][0].get("created_id")
        scene, _ = self.store.get_scene(pid)
        try:
            obj = m.find_object(scene, created)
            res["object"] = summarize.object_facts(scene, obj)
            res["clearance_m"] = fitcheck.clearances(scene, obj)
            res["passes_door"] = fitcheck.passes_door(scene, obj["dimensions_m"])
        except SceneError:
            pass
        if parsed and parsed.get("assumed_order"):
            res["note"] = parsed["order_note"]
        return res

    # ------------------------------------------------------------ photos

    def register_photo(self, source_path: str | Path, project_id: str | None = None, photo_id: str | None = None) -> dict:
        """Copy an image into the data folder and record it. No decoding here."""
        src = Path(source_path).expanduser()
        if not src.is_file():
            return _err("not_found", f"No file at {src}")
        data = src.read_bytes()
        if len(data) > 15 * 1024 * 1024:
            return _err("too_large", "Photos must be under 15 MB")
        kind = sniff_image(data)
        if kind is None:
            return _err("unsupported_format", "Only JPEG, PNG and WebP photos are supported (HEIC is not yet).")
        sha = hashlib.sha256(data).hexdigest()
        pid = photo_id or ("p" + sha[:12])
        dest = self.data_dir / "photos" / f"{pid}.{kind}"
        if not dest.exists():
            shutil.copyfile(src, dest)
        row = self.store.add_photo(pid, str(dest), sha, None, None, project_id)
        return {"ok": True, "photo_id": pid, "file": row["file"], "sha256": sha, "format": kind}

    def photo_path(self, photo_id: str) -> Path | None:
        try:
            return Path(self.store.get_photo(photo_id)["file"])
        except NotFound:
            return None

    def attach_photos(self, project_id: str, photo_ids: list[str]) -> None:
        for p in photo_ids:
            try:
                self.store.attach_photo(p, project_id)
            except Exception:
                pass

    # ------------------------------------------------------------ export

    def export(self, project_id: str | None = None, fmt: str = "json", out_dir: str | Path | None = None) -> dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        scene, rev = self.store.get_scene(pid)
        fmt = (fmt or "json").lower()
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in scene["project"]["name"])[:40] or "room"
        folder = Path(out_dir).expanduser() if out_dir else (self.data_dir / "exports")
        folder.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            path = folder / f"{safe}-r{rev}.room.json"
            path.write_text(json.dumps({"roomsmith": 1, "schema_version": scene["schema_version"], "revision": rev, "scene": scene}, indent=2))
        elif fmt == "glb":
            path = folder / f"{safe}-r{rev}.glb"
            path.write_bytes(export_glb.scene_to_glb(scene))
        elif fmt in ("summary", "txt", "text"):
            path = folder / f"{safe}-r{rev}.txt"
            issues = validate.issues(scene)
            path.write_text(summarize.summary_text(scene, issues, rev) + "\n\n" + summarize.shopping_list(scene) + "\n")
        else:
            return _err("invalid_value", "format must be json, glb or summary")
        return {"ok": True, "project_id": pid, "revision": rev, "format": fmt, "path": str(path), "bytes": path.stat().st_size}

    def export_bytes(self, project_id: str | None, fmt: str) -> tuple[bytes, str, str] | dict:
        pid = self._resolve_project(project_id)
        if not pid:
            return self._no_project(project_id)
        scene, rev = self.store.get_scene(pid)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in scene["project"]["name"])[:40] or "room"
        if fmt == "glb":
            return export_glb.scene_to_glb(scene), "model/gltf-binary", f"{safe}-r{rev}.glb"
        if fmt == "json":
            return json.dumps({"roomsmith": 1, "schema_version": scene["schema_version"], "revision": rev, "scene": scene}, indent=2).encode(), "application/json", f"{safe}-r{rev}.room.json"
        issues = validate.issues(scene)
        return (summarize.summary_text(scene, issues, rev) + "\n\n" + summarize.shopping_list(scene) + "\n").encode(), "text/plain", f"{safe}-r{rev}.txt"

    def import_json(self, payload: dict, name: str | None = None, actor: str = "user") -> dict:
        scene = payload.get("scene") if isinstance(payload, dict) and "scene" in payload else payload
        if not isinstance(scene, dict) or "room" not in scene:
            return _err("invalid_value", "Not a Roomsmith JSON file")
        scene = m.clone(scene)
        pid = m.new_project_id()
        scene["project"] = {"id": pid, "name": name or scene.get("project", {}).get("name") or "Imported room", "units": "m"}
        try:
            validate.validate_hard(scene)
        except SceneError as e:
            return {"ok": False, "error": e.to_dict()}
        self.store.create_project(pid, scene["project"]["name"], m.round_scene(scene), actor=self._actor(actor), summary="Imported room")
        self.store.set_active(pid)
        return self.inspect(pid)

    # ------------------------------------------------------------ awareness

    def unseen_changes(self, project_id: str | None = None) -> dict:
        """Revisions made by the user since the agent last saw the room."""
        pid = self._resolve_project(project_id)
        if not pid:
            return {"ok": True, "project_id": None, "changes": []}
        h = self.store.head(pid)
        seen = int(h.get("agent_seen_revision") or 0)
        if h["revision"] <= seen:
            return {"ok": True, "project_id": pid, "revision": h["revision"], "changes": []}
        changes = [c for c in self.store.revisions_between(pid, seen) if c["actor"] != "agent"]
        return {"ok": True, "project_id": pid, "name": h["name"], "revision": h["revision"], "seen_revision": seen, "changes": changes}

    def mark_seen(self, project_id: str | None = None) -> None:
        pid = self._resolve_project(project_id)
        if pid:
            self.store.mark_agent_seen(pid, self.store.head(pid)["revision"])

    def health(self) -> dict:
        from rs_core import __version__

        return {"ok": True, "version": __version__, "schema_version": m.SCHEMA_VERSION, "store": self.store.stats(), "data_dir": str(self.data_dir)}


def sniff_image(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def new_command_id() -> str:
    return str(uuid.uuid4())
