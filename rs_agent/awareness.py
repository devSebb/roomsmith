"""pre_llm_call hook: tell the agent what the user did in the editor.

Fires in sessions that have already used a Roomsmith tool (and, for a plain "furnish
my bedroom" request, in a session that has not yet). When the user asks to furnish,
decorate or shop, it gives the agent the furnishing steps and the room's budget state:
tool descriptions are loaded lazily by the host, so this is where the agent is sure to
see them. Otherwise two things, each only when there is something new: revisions the user made by hand that the agent
has not seen, and what the user has selected (so "this" and "it" mean something).
The text goes into the current user message for this turn only, so the cached
system prompt is untouched. Never more than a few lines.
"""

from __future__ import annotations

from typing import Any

import re

from rs_agent import tools

MAX_LINES = 4
_FURNISH = re.compile(r"\b(furnish\w*|decorat\w*|budget|shop(ping)?|buy(ing)?|under\s*[$€£]?\s*\d|for\s*[$€£]\s*\d|[$€£]\s*\d|\d[\d,.]*\s*(k\b|dollars?|usd|euros?|eur|pounds?|gbp|bucks))", re.I)
_FURNISH_COLD = re.compile(r"\b(furnish\w*|decorat\w*)\b.*\b(room|bedroom|office|studio|apartment|flat|kitchen|lounge|nursery)\b|\b(room|bedroom|office|studio|apartment|flat|kitchen|lounge|nursery)\b.*\b(furnish\w*|decorat\w*)\b", re.I | re.S)


def _text(message: Any) -> str:
    """The user's words: a plain string, or the text parts of a multimodal message."""
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return " ".join(str(p.get("text") or "") for p in message if isinstance(p, dict))
    return ""


def furnishing_brief(svc: Any) -> str:
    """What to do when the user asks to furnish: the steps, with the room's own budget state."""
    budget = None
    try:
        out = svc.inspect(None)
        budget = (out.get("budget") or {}).get("text") if out.get("ok") else None
    except Exception:
        pass
    first = (
        f"1. {budget}. Work inside it."
        if budget
        else "1. No budget is set. If this message does not give an amount, ASK the user for their budget now, and ask once whether to keep part of it back as a buffer. Add nothing until they answer."
    )
    return "\n".join(
        [
            "[Roomsmith] This is a furnishing request. Use REAL products, not generic pieces (add_object), unless the user asks for placeholders:",
            first,
            "2. Record it: roomsmith_apply {op: set_budget, limit, currency}; if they named a look, {op: set_style, style}.",
            "3. For each piece: web search for 3 to 6 product-page URLs (never invent a URL) -> roomsmith_shortlist {category, candidates, place} -> roomsmith_add_product {url, category, place} for the chosen row.",
            "4. If a reply carries budget_note (over budget, into the buffer, no price), tell the user and ask before continuing.",
            "5. Finish with a table: piece, size, price, link; the total; what is left. Say prices are as read today.",
        ]
    )


def pre_llm_call(**kwargs: Any) -> dict | None:
    session_id = kwargs.get("session_id")
    said = _text(kwargs.get("user_message"))
    if not tools.session_uses_rooms(session_id):
        # a session that has not touched Roomsmith only hears from it when the user plainly asks to furnish a room
        if not _FURNISH_COLD.search(said):
            return None
        try:
            return {"context": furnishing_brief(tools.get_service())}
        except Exception:
            return None
    try:
        svc = tools.get_service()
        info = svc.unseen_changes(None)
        selected = svc.selection(None)
    except Exception:
        return None
    lines: list[str] = []
    if _FURNISH.search(said):
        lines.append(furnishing_brief(svc))
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
