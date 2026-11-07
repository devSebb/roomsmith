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
| Desktop SDK (`@hermes/plugin-sdk`): `host.notify`, `host.navigate`, `atom`, `useValue`, `PANES_AREA`, `ROUTES_AREA`, `SIDEBAR_NAV_AREA`, `STATUSBAR_AREAS`, `PALETTE_AREA`; `ctx.registerMany`, `ctx.rest(path, {method, body, upload, timeoutMs})`, `ctx.storage.get/set`, `ctx.os.openExternal` | `web/src/desktop.tsx` | 0.21.0 (docs) | **not yet run live** (spike S4 in Desktop) | single uncompiled ESM file; only three import specifiers resolve |
| Catalog validator (`hermes plugins validate`, main only): manifest + SemVer floor, capability probe with a methods-only stub, security scan (≤400 files, ≤10 MB, ≤1 MB/file), Desktop-surface lint, private-imports warning | repo layout, build | main (0.23.x) | **mirrored** in `web/build.mjs`; authoritative run pending (spike S7) | |

## Python

- Engine and tools: standard library only; `Pillow` used through a guarded import.
- Tested on Python **3.11.15** (MacBook) and **3.14.7** (the Mini's version). No
  syntax newer than 3.11.

## Machines

| Machine | Hermes | Python | Role |
|---|---|---|---|
| MacBook (dev) | 0.21.0 (`~/.hermes/hermes-agent`, unused install) | 3.11 / 3.14 | all code; lower-bound runtime checks in an isolated `HERMES_HOME` (`.scratch/hermes-home`) |
| Mac mini (production) | 0.21.5+5263.g895b506 **dirty** git install, upstream a9ff9799 | 3.14.7 | runtime tests only in an approved isolated home; never the live `~/.hermes` |
| Judges (assumed) | latest release, 0.23.0 on 2026-11-05 | — | catalog `validate` + clean install |

## Spike log (M0)

| Spike | Result | Date |
|---|---|---|
| S0 Mini reachable | passed (read-only SSH as `jessica`) | 2026-11-07 |
| S1 skeleton loads | passed on 0.21.0: `hermes plugins doctor --ci` OK; dashboard tab + backend live in an isolated home | 2026-11-07 |
| S2 `ctx.llm` with an image on GPT astra | pending (needs the Mini test home) | |
| S3 photo draft quality | pending (needs photos) | |
| S4 bundled three.js in Desktop | half: both bundles 593 KB, lint clean by mirror, dashboard shell renders in the real dashboard; Desktop app run pending | 2026-11-07 |
| S5 tool write reaches the pane | passed: agent-actor commands appear in the editor within ~1 s with a toast and flash (long-poll) | 2026-11-07 |
| S6 attached photo → tool | pending; Route B (`new_room` with `layout`) implemented and tested as the path that needs nothing | |
| S7 `hermes plugins validate` | pending (throwaway 0.23.0) | |
