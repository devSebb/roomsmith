# Compatibility record

The compatibility target is the set of Hermes public surfaces this plugin
actually uses — not whichever version a particular machine runs.
`requires_hermes` in `plugin.yaml` is the highest "first seen" value below.

| Surface | Used by | First seen (verified) | Last verified on | Notes |
|---|---|---|---|---|
| `plugin.yaml` fields `name`, `version`, `description`, `requires_hermes`, `provides_tools`, `provides_hooks`, `provides_middleware`, `requires_env` | manifest | 0.21.0 (docs) | 0.21.0 `hermes plugins doctor --ci` | unknown fields are ignored by contract |
| `register(ctx)` entry point; package loaded as `hermes_plugins.<slug>` with `__path__` = plugin dir | `__init__.py` | 0.21.0 (`hermes_cli/plugins.py` `_load_directory_plugin`) | 0.21.0 | we put the plugin root on `sys.path` so `rs_core` is one module in every process |
| `ctx.register_tool(name, toolset, schema, handler, check_fn, requires_env, is_async, description, emoji, override)` | 9 tools | 0.21.0 | 0.21.0 doctor | handler `(args: dict, **kwargs) -> str`; kwargs seen: `task_id`, `session_id`, `user_task` |
| `ctx.register_command(name, handler, description, args_hint)` | `/room` | 0.21.0 | 0.21.0 doctor | handler `(raw_args: str) -> str` |
| `ctx.register_skill(name, path, description)` | `room-design` | 0.21.0 | 0.21.0 doctor | wrapped in try/except: optional |
| `ctx.register_hook("pre_llm_call", cb)` returning `{"context": str}` | awareness | 0.21.0 | 0.21.0 doctor | kwargs seen: `session_id`, `task_id`, `turn_id`, `user_message`, … ; injected into the user message only |
| `ctx.llm.complete_structured(instructions=, input=[{type:text}|{type:image,data,mime_type,file_name}], json_schema=, schema_name=, purpose=, temperature=, max_tokens=, timeout=)` → `.parsed` / `.text` | `rs_agent/photo.py` | 0.21.0 (`agent/plugin_llm.py`) | **not yet run live** (spike S2 on the Mini) | read lazily at call time, never in `register()` |
| `plugins.plugin_storage.plugin_data_dir(name)` | `rs_agent/paths.py` | 0.21.0 | 0.21.0 | in the public API list on main; lazy import with a `~/.hermes/plugin-data` fallback |
| Dashboard `dashboard/manifest.json` (`name`, `label`, `icon`, `version`, `tab.path`, `tab.position`, `entry`, `api`) | dashboard tab | 0.21.0 (docs) | 0.21.0 live (`hermes dashboard`) | gated on `plugins.enabled` |
| Dashboard `plugin_api.py` exporting FastAPI `router`, mounted at `/api/plugins/<name>/`, imported standalone | backend | 0.21.0 | 0.21.0 live | no relative imports; behind the dashboard's auth |
| Dashboard JS SDK: `window.__HERMES_PLUGIN_SDK__.React`, `SDK.fetchJSON`, `window.__HERMES_PLUGINS__.register(name, Component)`, `window.__HERMES_SESSION_TOKEN__` + `X-Hermes-Session-Token` | `web/src/dashboard.tsx` | 0.21.0 | 0.21.0 live | `fetchJSON` throws `Error("<status>: <body>")` on non-2xx; we parse the body back |
| Desktop SDK (`@hermes/plugin-sdk`): `host.notify`, `host.navigate`, `atom`, `useValue`, `PANES_AREA`, `ROUTES_AREA`, `SIDEBAR_NAV_AREA`, `STATUSBAR_AREAS`, `PALETTE_AREA`; `ctx.registerMany`, `ctx.rest(path, {method, body, upload, timeoutMs})`, `ctx.storage.get/set`, `ctx.os.openExternal` | `web/src/desktop.tsx` | 0.21.0 (docs) | 0.21.0 (+37159) Desktop live, 2026-11-08 | single uncompiled ESM file; only three import specifiers resolve. Pane, sidebar nav, status chip, palette, `ROUTES_AREA` full page (`#/roomsmith`) and `ctx.rest` (incl. auth) all work. Caveat: **routes register only at app start** — the Desktop hot-reloads `plugin.js` for panes/chips but a route added or renamed while the app runs does not mount until a full relaunch (what looked like a host gap on 8 Nov). Pane and page can be open at once (two editor instances, each follows the active room) |
| Catalog validator (`hermes plugins validate`, main only): manifest + SemVer floor, capability probe with a methods-only stub, security scan (≤400 files, ≤10 MB, ≤1 MB/file), Desktop-surface lint, private-imports warning | repo layout, build | main (0.23.x) | **passed on the Mini**, Hermes 0.23.0+689 (a9ff9799), commit 0bf14fc, 2026-11-08 | `validate` takes a **directory**, not a plugin name. It reports `Isolation — runs in the plugin host (plugins.isolation: host)` and `dashboard backend API is served through the plugin host (buffered responses)`: on 0.23 our API is proxied; the long-poll `wait` is a plain buffered JSON reply and the editor shortens its wait window on repeated transport failures |

## Python

- Engine and tools: standard library only; `Pillow` used through a guarded import.
- Tested on Python **3.11.15** (MacBook) and **3.14.7** (the Mini's version). No
  syntax newer than 3.11.

## Machines

| Machine | Hermes | Python | Role |
|---|---|---|---|
| MacBook (dev) | 0.21.0 (`~/.hermes/hermes-agent`, unused install; Desktop build +37159) | 3.11 / 3.14 | all code; lower-bound runtime checks in an isolated `HERMES_HOME` (session scratchpad `hermes-home/`). Desktop is run isolated with `HERMES_HOME=<isolated> HERMES_DESKTOP_USER_DATA_DIR=<isolated userData> HERMES_DESKTOP_HERMES_ROOT=~/.hermes/hermes-agent hermes desktop --skip-build`; `desktop.electron_flags: [--remote-debugging-port=9333]` in the isolated config lets a CDP script drive the UI |
| Mac mini (production) | live: 0.21.5+5263.g895b506 **dirty** git install; test env `/Users/jessica/room-studio-test/` checkout a9ff9799 = **0.23.0+689**, Pillow 13.0.0 | 3.14.7 | runtime tests only in the approved isolated home through `run-isolated.py`; never the live `~/.hermes`. Roomsmith 0bf14fc installed there via `hermes plugins install devSebb/roomsmith --ref …` |
| Judges (assumed) | latest release, 0.23.0 on 2026-11-05 | — | catalog `validate` + clean install |

## Spike log (M0)

| Spike | Result | Date |
|---|---|---|
| S0 Mini reachable | passed (read-only SSH as `jessica`) | 2026-11-07 |
| S1 skeleton loads | passed on 0.21.0: `hermes plugins doctor --ci` OK; dashboard tab + backend live in an isolated home. Mini (0.23.0+689): install + doctor passed; chat turn blocked until the test home has Codex OAuth | 2026-11-08 |
| S2 `ctx.llm` with an image on GPT astra | pending (needs the Mini test home) | |
| S3 photo draft quality | in progress: first real photo in `fixtures/photos/` (gitignored, 1200×1600 PNG) with a hand-written reference draft beside it; pipeline run offline with a mock `ctx.llm` → room, 4 objects, door, photo registered, 176 KB JPEG sent to the model. The model-read half runs on the Mini (S2) | 2026-11-08 |
| S4 bundled three.js in Desktop | **passed**: Hermes Desktop 0.21.0 (+37159) on the MacBook, fully isolated launch; plugin discovered under Settings → Plugins ("Roomsmith · on disk" + agent plugin "roomsmith · git"), pane renders the WebGL room, `ctx.rest` works behind auth, status chip and sidebar entry present; 593 KB; `validate`'s desktop-surface lint passed on the Mini. Full page mounts at `#/roomsmith` after a cold start (routes are not hot-reloaded). Agent-created rooms switch the open editor (long-poll `active` wake) — verified live with the photo room | 2026-11-08 |
| S5 tool write reaches the pane | passed in the dashboard (7 Nov) and **in Hermes Desktop** (8 Nov): `roomsmith_apply` against the backend's DB shows in the pane within ~2 s with a toast | 2026-11-08 |
| S6 attached photo → tool | pending; Route B (`new_room` with `layout`) implemented and tested as the path that needs nothing | |
| S7 `hermes plugins validate` | **passed** on the Mini test checkout (0.23.0+689) at 0bf14fc: all 16 checks ✓ incl. security scan, no core override, desktop surface. Also `doctor --ci` OK (9 tools, 1 hook). Run by Harvey; full output in `ROOMSMITH_MINI_SPIKE_RESULTS.md` | 2026-11-08 |
| S8 CI runs Hermes's own checks | `.github/workflows/validate.yml`: engine tests (py 3.11/3.13), editor typecheck + tests + reproducible bundles, `hermes plugins doctor --ci` and `plugins validate` on a fresh hermes-agent checkout (pinned a9ff9799; `main` non-blocking). First run: see Actions on the repo | 2026-11-08 |
