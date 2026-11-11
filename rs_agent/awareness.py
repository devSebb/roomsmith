"""pre_llm_call hook: tell the agent what the user did in the editor.

Fires only in sessions that have already used a Roomsmith tool. Two things, each
only when there is something new: revisions the user made by hand that the agent
has not seen, and what the user has selected (so "this" and "it" mean something).
The text goes into the current user message for this turn only, so the cached
system prompt is untouched. Never more than a few lines.
"""

from __future__ import annotations

from typing import Any

from rs_agent import tools

MAX_LINES = 4


def pre_llm_call(**kwargs: Any) -> dict | None:
    session_id = kwargs.get("session_id")
    if not tools.session_uses_rooms(session_id):
        return None
    try:
        svc = tools.get_service()
        info = svc.unseen_changes(None)
        selected = svc.selection(None)
    except Exception:
        return None
    lines: list[str] = []
    changes = info.get("changes") or []
    if changes:
        lines.append(f"[Roomsmith] The user edited room '{info.get('name')}' in the editor since you last looked (now revision {info['revision']}):")
        for c in changes[-MAX_LINES:]:
            summary = c["summary"]
            if summary.startswith("You: "):
                summary = summary[5:]
            lines.append(f"- r{c['revision']}: {summary}")
        if len(changes) > MAX_LINES:
            lines.append(f"- and {len(changes) - MAX_LINES} earlier change(s)")
        lines.append("Call roomsmith_inspect before editing so you work from the current revision.")
        try:
            svc.mark_seen(None)
        except Exception:
            pass
    if tools.selection_is_news(str(session_id), selected):
        lines.append(f"[Roomsmith] In the editor the user has '{selected['name']}' ({selected['id']}) selected. \"This\", \"it\" or \"that one\" most likely means it.")
    return {"context": "\n".join(lines)} if lines else None
