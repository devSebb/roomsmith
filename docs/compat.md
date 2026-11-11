# Compatibility record

The compatibility target is the set of Hermes public surfaces this plugin
actually uses — not whichever version a particular machine runs.
`requires_hermes` in `plugin.yaml` is the highest "first seen" value below.

| Surface | Used by | First seen (verified) | Last verified on | Notes |
|---|---|---|---|---|
| `plugin.yaml` fields `name`, `version`, `description`, `requires_hermes`, `provides_tools`, `provides_hooks`, `provides_middleware`, `requires_env` | manifest | 0.21.0 (docs) | 0.21.0 `hermes plugins doctor --ci` | unknown fields are ignored by contract |
| `register(ctx)` entry point; package loaded as `hermes_plugins.<slug>` with `__path__` = plugin dir | `__init__.py` | 0.21.0 (`hermes_cli/plugins.py` `_load_directory_plugin`) | 0.21.0 | we put the plugin root on `sys.path` so `rs_core` is one module in every process |
| `ctx.register_tool(name, toolset, schema, handler, check_fn, requires_env, is_async, description, emoji, override)` | 10 tools | 0.21.0 | 0.21.0 doctor | handler `(args: dict, **kwargs) -> str`; kwargs seen: `task_id`, `session_id`, `user_task` |
| `ctx.register_command(name, handler, description, args_hint)` | `/room` | 0.21.0 | 0.21.0 doctor | handler `(raw_args: str) -> str` |
| `ctx.register_skill(name, path, description)` | `room-design` | 0.21.0 | 0.21.0 doctor | wrapped in try/except: optional |
| `ctx.register_hook("pre_llm_call", cb)` returning `{"context": str}` | awareness | 0.21.0 | 0.21.0 doctor | kwargs seen: `session_id`, `task_id`, `turn_id`, `user_message`, … ; injected into the user message only |
| `ctx.llm.complete_structured(instructions=, input=[{type:text}|{type:image,data,mime_type,file_name}], json_schema=, schema_name=, purpose=, temperature=, max_tokens=, timeout=)` → `.parsed` / `.text` | `rs_agent/photo.py` | 0.21.0 (`agent/plugin_llm.py`) | 0.23.0, live with an image-capable model, 2026-11-08 | read lazily at call time, never in `register()` |
| `plugins.plugin_storage.plugin_data_dir(name)` | `rs_agent/paths.py` | 0.21.0 | 0.21.0 | in the public API list on main; lazy import with a `~/.hermes/plugin-data` fallback |
| Dashboard `dashboard/manifest.json` (`name`, `label`, `icon`, `version`, `tab.path`, `tab.position`, `entry`, `api`) | dashboard tab | 0.21.0 (docs) | 0.21.0 live (`hermes dashboard`) | gated on `plugins.enabled` |
| Dashboard `plugin_api.py` exporting FastAPI `router`, mounted at `/api/plugins/<name>/`, imported standalone | backend | 0.21.0 | 0.21.0 live | no relative imports; behind the dashboard's auth |
| Dashboard JS SDK: `window.__HERMES_PLUGIN_SDK__.React`, `SDK.fetchJSON`, `window.__HERMES_PLUGINS__.register(name, Component)`, `window.__HERMES_SESSION_TOKEN__` + `X-Hermes-Session-Token` | `web/src/dashboard.tsx` | 0.21.0 | 0.21.0 live | `fetchJSON` throws `Error("<status>: <body>")` on non-2xx; we parse the body back |
| Desktop SDK (`@hermes/plugin-sdk`): `host.notify`, `host.navigate`, `atom`, `useValue`, `PANES_AREA`, `ROUTES_AREA`, `SIDEBAR_NAV_AREA`, `STATUSBAR_AREAS`, `PALETTE_AREA`; `ctx.registerMany`, `ctx.rest(path, {method, body, upload, timeoutMs})`, `ctx.storage.get/set`, `ctx.os.openExternal` | `web/src/desktop.tsx` | 0.21.0 (docs) | Desktop 0.21.0 and 0.23.0 live, 2026-11-10 | single uncompiled ESM file; only three import specifiers resolve. Pane, sidebar nav, status chip, palette, `ROUTES_AREA` full page (`#/roomsmith`) and `ctx.rest` (incl. auth) all work. Caveat: **routes register only at app start** — the Desktop hot-reloads `plugin.js` for panes/chips but a route added or renamed while the app runs does not mount until a full relaunch. Pane and page can be open at once (two editor instances, each follows the active room) Host behaviour to design around: right-click anywhere (incl. the WebGL canvas) opens the Desktop's own context menu from the main process; `preventDefault`/`stopPropagation` in the renderer cannot suppress it, so the editor binds no right-button action (pan = ⇧-drag or middle). Performance: 60 objects, two editor instances, orbit + drag = 60 fps, worst frame 34 ms (Apple M2, 8 Nov). Note: rAF and ResizeObserver are suspended while the Desktop window is in the background — bring it frontmost before measuring or judging layout from CDP screenshots Automated checklist: `node web/dev/desktop-attach.mjs 9333 web/dev/desktop-smoke.mjs` (8/8 on 8 Nov; set `SMOKE_AGENT_CMD` to a command that creates a room out-of-process to test the follow behaviour) |
| Catalog validator (`hermes plugins validate`, main only): manifest + SemVer floor, capability probe with a methods-only stub, security scan (≤400 files, ≤10 MB, ≤1 MB/file), Desktop-surface lint, private-imports warning | repo layout, build | main (0.23.x) | passed on Hermes 0.23.0+689 (a9ff9799) and in CI on every push | `validate` takes a **directory**, not a plugin name. It reports `Isolation — runs in the plugin host (plugins.isolation: host)` and `dashboard backend API is served through the plugin host (buffered responses)`: on 0.23 our API is proxied; the long-poll `wait` is a plain buffered JSON reply and the editor shortens its wait window on repeated transport failures |

## Python

- Engine and tools: standard library only; `Pillow` through guarded imports
  (photo downscaling, product thumbnails). Everything works without it.
- Tested on Python **3.11** and **3.14**. No syntax newer than 3.11.

## Where it was run

| Hermes | Python | What |
|---|---|---|
| 0.21.0 (Desktop build +37159) | 3.11 | lower bound: `plugins doctor --ci`, dashboard tab, Desktop pane and page, in an isolated `HERMES_HOME` |
| 0.23.0+689 (a9ff9799) | 3.14 | `plugins validate` (all checks), `doctor --ci`, live chat sessions with photos and product links, Desktop connected to a remote gateway |
| `main` | 3.14 | CI, non-blocking |

To run Desktop against a throwaway home (nothing touches `~/.hermes`):
`HERMES_HOME=<dir> HERMES_DESKTOP_USER_DATA_DIR=<dir> hermes desktop`.
Adding `desktop.electron_flags: [--remote-debugging-port=9333]` to that home's
config lets `node web/dev/desktop-attach.mjs 9333 web/dev/desktop-smoke.mjs`
drive the editor checklist.

## What was verified, and what was found

| Question | Result |
|---|---|
| Does the plugin load? | `hermes plugins doctor --ci`: 10 tools, 1 hook, on 0.21.0 and 0.23.0. In a live chat the model discovered the tools, created a room, applied a batch with correct ids and revision, and `/room` answered from the host command with zero tokens |
| Does `ctx.llm.complete_structured` take images? | Yes, on 0.23.0 with an image-capable model: one to four photos in one call, no fallback rung taken |
| How good is a photo draft? | Two rooms scored with `scripts/score-draft.py` against tape measurements the model never saw. Widths within 1–7 %; depth off by −22 % to +47 % (wide-angle stretch); every object, door and window on the right wall; ceiling and wall mounts right. Hence `calibrate {kind: room_size}`: it fits each axis to the real floor size and keeps furniture sizes |
| Does bundled three.js pass the Desktop lint and the 1 MB limit? | Yes: 657 KB, desktop-surface lint clean; 60 objects at 60 fps |
| Does an agent edit reach the open editor? | Within about 2 s (long-poll), with a toast and a highlight; a room the agent creates becomes the editor's room |
| Product pages | Read correctly live: Castlery, Sixpenny, Albany Park, Thuma, Branch (schema.org JSON-LD, Shopify product JSON, OpenGraph, inline spec JSON). Refused by the site and reported as `blocked`, never retried: Article (bot check), Floyd (429). No size on the page → the plugin asks the user |
| Photo attached in chat | A file path in the prompt works in Desktop and the CLI (`roomsmith_from_photo`). When the model can see an attached photo it can use `roomsmith_new_room` with `layout` instead. `hermes chat --image` is rejected by the gateway-backed CLI before any tool runs |
| Desktop against a remote gateway | Works: Desktop → Settings → Gateways → Remote gateway; the editor lists and edits the remote's rooms. The Desktop half must be installed on the machine running Desktop |
| `hermes plugins validate` | All checks pass on 0.23.0+689 and on `main` in CI (`.github/workflows/validate.yml`), together with engine tests on Python 3.11/3.14, editor typecheck and tests, and a rebuild that must match the committed bundles. On 0.23 the validator reports that the plugin runs in the plugin host and its dashboard API is proxied with buffered responses; the editor's long-poll is a plain JSON reply for that reason |

Host behaviour worth knowing:

- hermes-agent 0.23 installs with `uv sync --locked` on Python 3.14 only.
- `hermes plugins validate` takes a directory, not a plugin name.
- Desktop opens its own context menu on right-click from the main process; the
  editor binds no right-button action (pan is ⇧-drag or the middle button).
- `requestAnimationFrame` and `ResizeObserver` pause while the Desktop window is
  in the background.
- Desktop registers routes at app start: the full-page editor appeared after a
  restart on 0.21.0 (panes and status chips load live).
