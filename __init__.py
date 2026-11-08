"""Roomsmith — a Hermes Agent plugin.

Turn a room photo into an editable 3D room, edit it by hand in the editor or
by talking to Hermes, add real products as true-size stand-ins, and check
what fits.

``register(ctx)`` only wires things up. It never opens the database, never
touches ``ctx.llm`` or ``ctx.state`` (the catalog validator's probe context has
methods but no properties), and never raises for a missing optional piece.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent

# Make `rs_core` and `rs_agent` importable under their own names in this
# process. The dashboard backend does the same, so both halves share one module.
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from rs_agent import awareness, schemas, tools  # noqa: E402

__version__ = "0.1.0"

_ctx = None


def _get_ctx():
    return _ctx


def register(ctx) -> None:
    global _ctx
    _ctx = ctx

    handlers = {
        "roomsmith_projects": tools.projects,
        "roomsmith_new_room": tools.new_room,
        "roomsmith_from_photo": tools.from_photo_handler(_get_ctx),
        "roomsmith_inspect": tools.inspect,
        "roomsmith_apply": tools.apply,
        "roomsmith_check": tools.check,
        "roomsmith_add_product": tools.add_product,
        "roomsmith_history": tools.history,
        "roomsmith_export": tools.export,
    }
    for spec in schemas.ALL:
        ctx.register_tool(
            name=spec["name"],
            toolset=schemas.TOOLSET,
            schema=spec,
            handler=handlers[spec["name"]],
            description=spec["description"][:160],
            emoji="🛋️",
        )

    ctx.register_command(
        name="room",
        handler=tools.slash_room,
        description="Show the active Roomsmith room (or switch: /room <name>)",
        args_hint="[name]",
    )

    skill = PLUGIN_ROOT / "skills" / "room-design" / "SKILL.md"
    if skill.exists():
        try:
            ctx.register_skill(
                name="room-design",
                path=skill,
                description="How to design a room with Roomsmith: inspect, edit, check fit, add products, calibrate.",
            )
        except Exception:
            pass  # a host without plugin skills still gets the tools

    ctx.register_hook("pre_llm_call", awareness.pre_llm_call)
