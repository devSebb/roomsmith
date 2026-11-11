"""pre_llm_call hook: tell the agent what the user did in the editor.

Fires in sessions that have already used a Roomsmith tool (and, for a plain "furnish
my bedroom" instruction, in a session that has not yet). When the user asks to furnish,
decorate or shop, it gives the agent the furnishing steps and the room's budget state
(seven lines): tool descriptions are loaded lazily by the host, so this is where the
agent is sure to see them. Otherwise two things, each only when there is something new: revisions the user made by hand that the agent
has not seen, and what the user has selected (so "this" and "it" mean something).
The text goes into the current user message for this turn only, so the cached
system prompt is untouched. The change and selection notes are a few lines.
"""

from __future__ import annotations

from typing import Any

import re

from rs_agent import tools

MAX_LINES = 4
_ROOM = r"(room|bedroom|office|studio|apartment|flat|kitchen|lounge|nursery|place|space|home|house)"
_PIECE = r"(sofa|couch|rug|lamp|desk|chair|armchair|bed|table|shelf|bookshelf|bookcase|dresser|nightstand|mirror|plant|wardrobe|stool|bench|art|furniture|decor)"
# A request to furnish, decorate or shop for the room, or to find a piece, or a money amount with its currency.
# Deliberately narrow: "under 2 metres wide", "which shop is this from?" and "the decorative box" are ordinary edits.
_FURNISH = re.compile(
    r"\b(furnish|furnishing|decorate|decorating|redecorate|budget|spend|shopping list)\b"
    rf"|\b(pick|recommend|suggest|find|choose|look for|shop for|buy|need (a|an|some)|want (a|an|some))\b[^.?!\n]{{0,40}}\b{_PIECE}s?\b"
    r"|[$€£]\s?\d|\b\d[\d,.]*\s*(k\b|dollars?\b|usd\b|euros?\b|eur\b|pounds?\b|gbp\b|bucks\b)",
    re.I,
)
# In a session that has not used Roomsmith yet: only a plain instruction to furnish or decorate a room.
# "furnished flat" and "decorators" (the Python kind) do not count.
_FURNISH_COLD = re.compile(rf"\b(furnish|decorate|redecorate)\b[^.?!\n]{{0,50}}\b{_ROOM}\b|\b(furnishing|decorating)\b[^.?!\n]{{0,20}}\b(my|our|the|this|a)\b[^.?!\n]{{0,20}}\b{_ROOM}\b", re.I)


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
            "3. For each piece: web search for 3 to 6 product-page URLs (never invent a URL) -> roomsmith_shortlist {category, candidates, place} -> roomsmith_add_product {url, category, place} for the chosen row. "
            "Pages that print the size read best; these shops do: songmics.com (VASAGLE), nathanjames.com, brightech.com, simpli-home.com, walkeredison.com, branchfurniture.com, castlery.com; ikea.com for pieces whose name carries the size (nightstands, desks, shelves). If a shop's pages come back no_dimensions or blocked, switch to a shop you have not tried; if several shops in a row are blocked, this machine's network is being refused: say so and ask the user for links or sizes.",
            "4. If a reply carries budget_note (over budget, into the buffer, no price), tell the user and ask before continuing.",
            "5. A furnished room is more than its big pieces. Once those are in and money is left, add finishing pieces the same way: a rug, a lamp, a plant, a mirror or wall art (mount: wall), a shelf.",
            "6. Finish with a table: piece, size, price, link; the total; what is left. Say prices are as read today.",
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
