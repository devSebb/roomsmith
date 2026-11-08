> **Name:** the plugin was renamed from "Room Studio" to **Roomsmith** on 7 November 2026 (id `roomsmith`, tools `roomsmith_*`, repo `devSebb/roomsmith`). Older mentions below are historical.

# Roomsmith — build plan

A Hermes Agent plugin that turns a room photo into an editable 3D room which you and Hermes edit together.

| | |
|---|---|
| Plan written | Friday 6 November 2026 |
| Hackathon deadline | Wednesday 11 November 2026, 5:00 PM EST |
| Internal ship deadline | Wednesday 11 November, 12:00 noon EST (five-hour buffer) |
| Status | Plan only. Nothing is built. No build, spend, photo upload or publication happens without Sebb's go. |
| Supersedes | `ROOM_STUDIO_FULL_BUILD_BRIEF_V2.md` for the hackathon. The v2 scene, command and undo design is kept; its process and several features are deferred (section 20). |

Every claim about Hermes in this document is marked **verified** (read in source or docs, or run on this Mac) or **unverified** (to be settled by a named spike in milestone M0). Section 22 lists the sources.

---

## 1. What we are building

**The promise.** Drop a photo of a room into Hermes. A few seconds later you have a 3D room you can edit: walls, doors, windows and furniture as separate, sized things. Then you change it two ways, against the same saved room:

- **By hand**, in a live 3D editor inside Hermes Desktop (and in the browser dashboard): drag, rotate, resize, undo.
- **By talking to Hermes**: "swap the sofa and the desk", "make the room 40 cm wider", "would this sofa from this link fit under the window?"

Each side sees the other's edits within about a second. Hermes can also answer questions that need real geometry: what overlaps, what blocks the door, whether a product fits.

**Why this is a plugin and not a prompt or a skill.** The hackathon judges "favor plugins that do more than a prompt or a skill could". Roomsmith has four things a prompt cannot have:

1. A persistent room with stable identities, revisions and undo.
2. A live visual editor inside the Hermes window.
3. Deterministic geometry: placement, snapping, overlap and clearance checks computed by code, not guessed by a model.
4. Two-way awareness: Hermes knows when you moved something by hand.

**What it is not, in version 0.1.** It is not a measured survey. A photo read by a general vision model gives a plausible draft, labelled as estimated. One real measurement from you ("this wall is 4.2 m") rescales the room so sizes become meaningful. Products appear as correctly sized stand-in shapes, not real 3D models.

**The long-term ideal** (section 20): measured reconstruction from several photos or a phone scan, real object meshes, real product models where retailers publish them, floor plans and Blender/USDZ export, multiple rooms, and use from messaging apps.

---

## 2. Hackathon requirements and how the plan meets them

| Requirement (from the Nous Research post) | How we meet it |
|---|---|
| Open a pull request adding the plugin to the Hermes plugin catalog | One file, `plugin-catalog/roomsmith.yaml`, in `NousResearch/hermes-agent`, pinned to a full commit SHA of the public plugin repo (section 16) |
| Post a demo video on X tagging @NousResearch, under 90 seconds, showing the plugin working | Script in section 18; recorded Tuesday |
| Submit both links through the form | After the PR is open; the post says the form can be submitted as soon as the PR is open and catalog checks run later |
| Usefulness | Fit checks and true-size product stand-ins answer a real question: "will it fit, and where?" |
| Reliability | The plugin always produces an editable room (fallback ladder, section 9); atomic edits; undo; zero required accounts or keys; zero third-party Python dependencies |
| Polish | Editor uses the Hermes Desktop component kit and theme variables; animated agent edits; empty and error states designed, not left to chance |
| Creativity | No room or interior plugin exists among the 1,065 catalog entries (**verified** by name search of the full listing on 6 November; names only, descriptions not read) |
| "More than a prompt or a skill could" | Section 1, points 1–4. The demo shows each one |

Nearby existing plugins, so we do not duplicate them: `print3d` (photo or idea → one printable object, needs Blender), `blender` (official, drives Blender), `meshy` (paid mesh generation), `office-3d` (a Desktop pane showing agent profiles as an isometric office). `office-3d` has the same package shape we will use and is a useful reference.

---

## 3. Principles

1. **Plugin only.** The repository contains the plugin and nothing else. No copy, fork or patch of Hermes. Hermes is the host; we use only its published plugin surfaces.
2. **Zero extra accounts.** Works with whatever model the user already runs in Hermes. No API keys, no sign-ups, no paid services. Optional providers can come later, off by default.
3. **One room, one source of truth.** The editor, the agent tools, undo, and export all read and write the same saved scene through the same command path.
4. **Always an editable room.** No path ends in "sorry, failed" without leaving the user something they can edit.
5. **Honest labels.** Every size carries where it came from: measured, stated by a product page, or estimated.
6. **Code does geometry; the model does language and vision.** The model never does coordinate arithmetic when code can.
7. **Public surfaces only.** Catalog rules forbid touching Hermes internals. We also avoid private imports that would only draw a warning.

---

## 4. How Hermes loads this plugin

All of this is **verified** from the installed Hermes v0.21.0 docs and source unless marked.

### 4.1 One folder, four parts

A Hermes plugin is a folder under `~/.hermes/plugins/<id>/`. One folder can carry several independent halves, and Hermes loads each through a different door:

| Part | File | Loaded by | Runs in | Purpose for us |
|---|---|---|---|---|
| Agent half | `plugin.yaml` + `__init__.py` with `register(ctx)` | Hermes plugin manager, when the plugin is in `plugins.enabled` | The process running the agent (CLI process, or the gateway for Desktop and messaging) | Tools, slash command, skill, one hook |
| Backend half | `dashboard/manifest.json` + `dashboard/plugin_api.py` exporting a FastAPI `router` | The web server, mounted at `/api/plugins/roomsmith/` (only when the plugin is in `plugins.enabled`) | The dashboard / gateway process | REST routes the editor calls |
| Desktop half | `desktop/plugin.js` (one plain ESM file) | Hermes Desktop, scanning `~/.hermes/plugins/<id>/desktop/` | The Desktop window (Electron renderer) | The 3D editor as a pane and a page |
| Dashboard half | `dashboard/dist/index.js` (one IIFE file) | The web dashboard (`hermes dashboard`) | The browser | The same editor as a dashboard tab |

Consequences that shape the design:

- **The agent half and the backend half can run in different processes.** A tool call in a terminal chat and an editor request in the dashboard do not share memory. Therefore **SQLite on disk is the only shared state**; no in-memory singletons hold room data.
- **The backend file is imported on its own**, under the module name `hermes_dashboard_plugin_roomsmith`, not as part of the plugin package. It cannot use relative imports. The shared engine therefore lives in a normal package folder that both halves import by path (section 5).
- **The backend has no `ctx`.** Only the agent half receives the plugin context, so only tools can call Hermes's model (`ctx.llm`). The photo read is a tool, not a backend route.
- **Each half has its own enable switch.** The Python halves need the plugin in `plugins.enabled` in `config.yaml`; the Desktop half is toggled in Settings → Plugins and ships off by default. The README must say so in three lines.

### 4.2 Hermes surfaces we use

| Surface | Use | Status |
|---|---|---|
| `ctx.register_tool(name, toolset, schema, handler, ...)` | Nine tools (section 11). Handlers take `(args: dict, **kwargs)`, always return a JSON string, never raise | Verified |
| `ctx.llm.complete_structured(instructions, input=[text, image…], json_schema)` | Read the photo with the user's active model; host owns credentials; falls back to the configured vision model if the active one is text-only | Verified in source and docs; **not yet run** (spike S2) |
| `ctx.register_command("room", …)` | `/room` slash command: status and how to open the editor | Verified |
| `ctx.register_skill(name, path)` | Bundled skill teaching the agent the edit loop | Verified |
| `ctx.register_hook("pre_llm_call", …)` | Tell the agent, in the current turn only, what the user changed by hand since the agent last looked | Verified |
| `plugins.plugin_storage.plugin_data_dir` / `plugin_db` | Durable data at `~/.hermes/plugin-data/roomsmith/` (SQLite in WAL mode, built for one reader and one writer in different processes). Survives plugin update and removal | Verified; listed in the public plugin API |
| Backend router at `/api/plugins/roomsmith/` | Editor REST API, behind the dashboard's normal auth | Verified |
| Desktop SDK (`@hermes/plugin-sdk`): panes, routes, sidebar nav, palette, keybinds, `ctx.rest`, UI kit, theme variables | The editor's home in Hermes Desktop | **Run live 8 Nov** in Desktop 0.21.0: pane, nav, chip, palette, full page, `ctx.rest` work; routes register at app start only (not hot-reloaded) |
| Dashboard SDK (`window.__HERMES_PLUGIN_SDK__`) | The editor as a browser tab | Verified in docs |

What we deliberately do not use: tool overrides, middleware, model or provider overrides, `requires_env`, OAuth, background processes, shell commands, lazy pip installs.

### 4.3 What Hermes gives us for free

Python 3.11, and in its own environment: FastAPI, Pillow, `jsonschema`, numpy (**verified** importable in the installed venv). The engine uses the standard library only. Pillow is used through a guarded import for photo downscaling and rotation; if it is missing, the photo is sent as-is.

### 4.4 Versions and the compatibility target

- Sebb's real Hermes runs on the Mac mini (`admins-mac-mini-1`, Tailscale `100.77.149.17`, user `jessica`, `hermes` at `/Users/jessica/.local/bin/hermes`), on a subscription with GPT astra as the model. **Verified** by read-only SSH probe on 7 November: `Hermes Agent v0.21.5+5263.g895b506.dirty (2026.9.24) · upstream a9ff9799`, git install at `/Users/jessica/.hermes/hermes-agent` with a **dirty working tree** (local modifications; never run `hermes update` or anything that touches it), **Python 3.14.7**, OpenAI SDK 2.24.0. The plugin must therefore run on Python 3.11 (MacBook) and 3.14 (Mini): no syntax or dependency newer than 3.11, nothing without 3.14 support.
- The MacBook also has an unused Hermes v0.21.0 install at `~/.hermes/hermes-agent` (Python 3.11.15). It is the source of the docs and code read for this plan, and a fallback runtime only. It has `hermes plugins doctor` but not `hermes plugins validate`.
- Latest release: v0.23.0, published 5 November 2026 (**verified** via the GitHub releases API). Judges will most likely run this.
- Native plugins are protected by an additive compatibility contract: documented `PluginContext` methods are not removed or renamed, and unknown manifest fields are ignored.
- **The compatibility target is the set of public APIs the plugin actually uses, not whichever version a machine happens to run.** `docs/compat.md` lists every Hermes surface the plugin touches (`ctx.register_tool`, `ctx.register_command`, `ctx.register_skill`, `ctx.register_hook("pre_llm_call")`, `ctx.llm.complete_structured`, `plugins.plugin_storage.plugin_data_dir`, the dashboard `router` contract, the Desktop SDK calls, the `hermes_dashboard_plugin_<name>` import shape), each with the version it first appeared in and the version it was last verified on. `requires_hermes` is the highest "first appeared" value in that list, and must not be newer than the current release.
- The plugin must pass on the lowest version in that list (MacBook v0.21.0), on the Mini's v0.21.5 in the isolated test home, and on v0.23.0.

---

## 5. Repository layout

The repository root **is** the plugin folder, so `hermes plugins install devSebb/roomsmith` works and the catalog entry needs no `subdir`.

```
roomsmith/                      # repo root = plugin root
├── plugin.yaml                   # manifest: name, version, tools, hooks, requires_hermes
├── __init__.py                   # register(ctx): tools, /room, skill, hook. Thin wiring only
├── rs_core/                      # the engine. Standard library only. No Hermes imports
│   ├── __init__.py
│   ├── model.py                  # scene data shapes, defaults, schema version
│   ├── ops.py                    # every operation; pure functions scene -> scene
│   ├── placement.py              # relational placement ("against wall", "next to", swap)
│   ├── geometry.py               # 2D polygons, rectangles, distances, overlaps
│   ├── validate.py               # hard rules (reject) and soft issues (warn)
│   ├── fitcheck.py               # clearance, door swing, walkway, "does it fit"
│   ├── store.py                  # SQLite: projects, revisions, command receipts, undo
│   ├── service.py                # the one application service both halves call
│   ├── layout.py                 # model draft (fractions) -> scene, with fallbacks
│   ├── dims.py                   # "W 180 x D 88 x H 76 cm" / inches -> meters
│   ├── catalog.py                # typical size ranges per furniture category
│   ├── export_glb.py             # scene -> GLB (boxes), written by hand with struct
│   └── summarize.py              # compact text/JSON summaries for the agent
├── rs_agent/                     # the Hermes-facing layer
│   ├── schemas.py                # tool schemas (what the model reads)
│   ├── tools.py                  # tool handlers -> service calls -> JSON strings
│   ├── photo.py                  # image loading, downscale, ctx.llm call, draft schema
│   ├── awareness.py              # pre_llm_call hook
│   └── paths.py                  # resolves the data dir through plugin_storage (lazy import)
├── dashboard/
│   ├── manifest.json             # name, label, icon, tab, entry, api
│   ├── plugin_api.py             # FastAPI router; loads rs_core by path
│   └── dist/index.js             # BUILT: dashboard tab (IIFE)
├── desktop/
│   └── plugin.js                 # BUILT: Desktop plugin (single ESM file, three.js inlined)
├── skills/
│   └── room-design/SKILL.md      # how the agent should work with a room
├── web/                          # SOURCE for both built UI files
│   ├── package.json, package-lock.json, build.mjs, tsconfig.json
│   ├── src/editor/               # framework-free editor core (three.js)
│   ├── src/ui/                   # React panels shared by both shells
│   ├── src/desktop.tsx           # Desktop shell -> desktop/plugin.js
│   ├── src/dashboard.tsx         # Dashboard shell -> dashboard/dist/index.js
│   └── dev/                      # local harness page + mock backend for fast iteration
├── tests/                        # pytest for rs_core and rs_agent; node tests for editor math
├── fixtures/                     # recorded model drafts, sample scenes (photos git-ignored)
├── docs/                         # banner (1200x600), screenshots, demo script
├── .github/workflows/validate.yml  # Hermes's own plugin-validate action + tests + build check
├── README.md  LICENSE  CHANGELOG.md  THIRD_PARTY_NOTICES.md
└── ROOMSMITH_PLAN.md           # this file (moves to docs/ when the repo is initialised)
```

Rules for this layout:

- **`rs_core` never imports Hermes.** It takes the database path as an argument. That keeps it testable with plain Python and identical in both processes.
- **Built files are committed.** A catalog install clones the repo at a pinned commit and runs no build. CI rebuilds from `web/` and fails if the committed files differ, so reviewers can trust that the bundle matches the source.
- **Size limits from Hermes's install scanner** (**verified** in `tools/plugin_guard.py` on main): at most 400 files, 10 MB total, 1 MB per file. A file over 1 MB is a "medium" finding. The built editor must stay under 1 MB per file; test fixtures and screenshots must stay small.
- **No binaries, no `.pyc`, no archives** in the repo (catalog rule 17). Images in `docs/` are fine.

---

## 6. The scene

One JSON document per revision. Units are meters and radians. Right-handed, +Y up, floor at Y = 0, an object's front faces −Z (the glTF and three.js convention, kept from the v2 brief).

```jsonc
{
  "schema_version": 1,
  "project": { "id": "uuid", "name": "Living room", "units": "m" },
  "calibration": {
    "status": "uncalibrated",            // or "calibrated"
    "reference": null                     // e.g. {"kind":"wall_length","id":"w2","real_m":4.2}
  },
  "room": {
    "height_m": 2.5,
    "vertices": [                         // ordered counter-clockwise seen from above
      { "id": "v1", "x": 0.0, "z": 0.0 }, { "id": "v2", "x": 4.2, "z": 0.0 },
      { "id": "v3", "x": 4.2, "z": 5.1 }, { "id": "v4", "x": 0.0, "z": 5.1 }
    ],
    "walls": [                            // wall i joins vertex i to vertex i+1
      { "id": "w1", "a": "v1", "b": "v2", "color": "#f2efe9", "label": "back" }
    ],
    "floor":   { "color": "#b08d62" },
    "ceiling": { "color": "#ffffff" },
    "openings": [
      { "id": "o1", "wall_id": "w1", "kind": "door",    // door | window | opening
        "offset_m": 0.4, "width_m": 0.8, "height_m": 2.03, "sill_m": 0.0,
        "swing": "in", "hinge": "left",
        "dims_source": "estimated" }
    ]
  },
  "objects": [
    { "id": "ob1", "name": "Sofa", "category": "sofa",
      "shape": "box",                     // box | cylinder
      "dimensions_m": [2.1, 0.8, 0.9],    // width (x), height (y), depth (z)
      "position_m": [1.2, 0.0, 4.6],      // center of the footprint, at the base
      "yaw_rad": 3.14159,
      "mount": "floor",                   // floor | wall | surface
      "color": "#6b7a8f",
      "locked": false,
      "provenance": {
        "class": "generated_approximation",  // or dimensioned_placeholder | user_supplied
        "dims_source": "estimated",          // estimated | stated | measured
        "confidence": 0.6
      },
      "product": null                     // or {title, url, image_url, price, dimensions_text}
    }
  ],
  "photos": [ { "id": "p1", "file": "photos/p1.jpg", "sha256": "…" } ]
}
```

Decisions:

- **Rotation is yaw only in 0.1.** Furniture stands upright. Export converts to quaternions. This removes a whole class of invalid states.
- **Rooms are polygons in the data model, rectangles in the 0.1 editor.** The engine and the agent tools handle any simple polygon. Dragging individual corners in the editor is a stretch goal.
- **Walls are straight and vertical; floor and ceiling are flat.** Sloped ceilings and curved walls are out.
- **Stable IDs.** Short, readable, never reused within a project (`w1`, `o3`, `ob12`), so the agent can refer to things across turns.
- **Lights are out of 0.1.** The editor uses fixed, pleasant lighting.

---

## 7. Edits: commands, revisions, undo

Every change, from the editor or from Hermes, is a **command**:

```json
{
  "project_id": "2ef86fc3-…",
  "expected_revision": 7,
  "command_id": "5f325d2b-…",
  "actor": "agent",
  "operations": [
    { "op": "move_object", "id": "ob1", "place": { "against_wall": "w3", "align": "center" } },
    { "op": "set_dimensions", "id": "ob4", "dimensions_m": [1.2, 0.75, 0.6] }
  ]
}
```

Guarantees:

- **Atomic.** All operations apply or none do.
- **Revision check.** If `expected_revision` is not the current one, the command is rejected with `revision_conflict` and the current revision number. The caller re-reads and retries. This is what stops the agent and the user from silently overwriting each other.
- **Idempotent.** A repeated `command_id` returns the first result and changes nothing.
- **Undo and redo are new forward revisions.** History is never rewritten. A new edit after an undo clears redo.
- **Full snapshot per revision.** Scenes are small (tens of kilobytes), so each revision stores the whole scene. Simple, robust, and it makes undo trivial. History is capped at 200 revisions per project.
- **Every revision records** the actor (`user`, `agent`, `system`), a one-line human summary ("Hermes moved Sofa to the window wall"), and the IDs it changed. The editor uses these for toasts and animation; the awareness hook uses them to brief the agent.

### Operations in 0.1

| Group | Operations |
|---|---|
| Room | `set_room_rectangle` (width, depth), `set_room_height`, `set_wall_length` (keeps right angles in a rectangle), `move_vertex`, `set_surface_color` (wall, floor, ceiling) |
| Openings | `add_opening`, `update_opening`, `remove_opening` |
| Objects | `add_object`, `update_object` (name, category, color, locked), `set_dimensions`, `move_object`, `rotate_object`, `duplicate_object`, `remove_object`, `swap_objects` |
| Scale | `calibrate` (one known real length rescales the whole scene and marks it calibrated) |

### Relational placement

Models are poor at coordinates and good at relations. `move_object` and `add_object` accept either absolute `position_m` or a `place` instruction that code resolves:

- `{ "against_wall": "w3", "align": "center" | "left" | "right", "offset_m": 0.3, "gap_m": 0.02 }` — flush to the wall, facing into the room.
- `{ "next_to": "ob2", "side": "left" | "right" | "front" | "behind", "gap_m": 0.1 }`
- `{ "in_corner": ["w1", "w2"] }`
- `{ "centered_in_room": true }`
- `{ "by": [dx, dz] }` — nudge relative to the current position.

The result reports the final coordinates and any issues the move caused.

### Storage

SQLite at `~/.hermes/plugin-data/roomsmith/data.db`, opened through Hermes's `plugin_db` (WAL mode). Tables: `projects`, `revisions` (scene JSON, actor, summary, changed IDs), `commands` (receipts for idempotency), `history` (undo and redo stacks), `photos`, `meta` (schema version, active project). Writes use `BEGIN IMMEDIATE` and compare the revision inside the transaction. Photos are files under `photos/` in the same data folder.

---

## 8. Validation and the fit check

**Hard rules — the command is rejected:**

- Non-finite numbers; non-positive dimensions; dimensions outside sane ranges (objects 1 cm – 20 m, room height 1.8 – 6 m).
- Fewer than three vertices, or a self-intersecting room outline.
- An opening that extends past its wall, overlaps another opening, or is taller than the room.
- Unknown IDs; editing a locked object without unlocking it.

**Soft issues — the command applies and the issues are returned and shown:**

| Issue | Rule in 0.1 |
|---|---|
| `overlap` | Two floor objects' footprints intersect by more than 1 cm (oriented rectangles) |
| `outside_room` | Any footprint corner lies outside the room outline |
| `blocks_door` | A footprint intersects the door's swing arc, or the 0.8 m deep zone in front of a doorway |
| `blocks_window` | An object taller than the sill stands within 10 cm of a window |
| `tight_walkway` | Less than 0.6 m between an object and a wall or another object along a path from a door to the room's centre (simple grid search) |
| `too_tall` | Object height exceeds room height |
| `uncalibrated` | The scene has no real measurement yet; sizes are estimates |

**"Will it fit" questions** answered by `fitcheck`:

- Does an object of given size fit at a named spot (against wall X, between A and B), and with how much to spare?
- Where could it fit? Up to three candidate placements along walls, ranked by free clearance.
- Will it pass through a door? Conservative rule: the two smallest dimensions must fit within the door's width and height. Reported as a simple rule, not a guarantee.

All numbers are computed by code and returned with units, so the agent quotes them instead of estimating.

---

## 9. Photo to draft room

### Route A — the plugin reads the photo (primary)

1. **Input.** One to four local image files (JPEG, PNG or WebP), given as paths or as IDs of photos uploaded through the editor. File type is checked by content, size is capped at 15 MB, and the file is copied into the plugin's data folder.
2. **Normalise.** With Pillow: apply the EXIF rotation, downscale the long side to 1,568 px, re-encode as JPEG. Photos uploaded through the editor are normalised in the browser before upload.
3. **Ask the model.** One `ctx.llm.complete_structured` call with the images and a JSON schema. The schema asks for things a vision model estimates well, and avoids things it does badly:
   - Room: assumed rectangle; estimated width, depth and height; which walls are visible (back, left, right, relative to the camera).
   - Openings: which wall, kind, position as a fraction along that wall, width, height, sill height.
   - Objects: label, category, estimated width / height / depth, which wall it stands against or "free", position as fractions across and into the room, which way it faces, main colour.
   - Surface colours for walls and floor.
   - Scale anchors it used (a standard door is about 0.8 m × 2.03 m, a kitchen counter about 0.9 m high), and a confidence per item.
4. **Build the scene in code** (`layout.py`): make the rectangle, convert fractions to coordinates, snap wall-side objects flush to their wall, clamp sizes to typical ranges per category, nudge apart overlaps, keep everything inside the room. Everything is marked `estimated`.
5. **Save as revision 1** and return a short summary: what was found, what is uncertain, and one suggested next step ("tell me one real measurement to set the scale").

### Route B — Hermes itself reads the photo

If the user attaches the photo in chat and the active model sees it directly, the agent can call `roomsmith_new_room` with a `layout` argument in the same fraction format. Same builder, same result, no second model call. This also covers hosts where the plugin cannot reach the image file.

### The fallback ladder

| If | Then |
|---|---|
| The model returns invalid JSON | One retry with a smaller schema (room size and object list only) |
| Still nothing usable | A default 4.0 × 5.0 × 2.5 m room, with any objects the model named lined up along a wall |
| The model cannot see images at all | The tool says so plainly, creates the default room, and suggests giving dimensions |
| The file is HEIC or unreadable | Clear message naming the accepted formats. HEIC conversion is a known gap in 0.1 (section 19) |

The tool returns an error without a room only when no project could be created at all.

### What to expect

A single photo shows two or three walls. The fourth wall and anything behind the camera are guesses. Door and window positions are approximate. Sizes are plausible, not measured, until calibrated. The editor shows a visible "Draft — estimated sizes" badge until the user calibrates.

**Unverified, settled in M0:** how good the draft is on real photos (spike S3), and how a photo attached in chat reaches a tool as a file path in the CLI and in Desktop (spike S6).

---

## 10. Products

The plugin makes **no network requests of its own**. Hermes already has web tools, with the user's configured backend, approvals and safety checks.

Flow when the user pastes a product link:

1. The skill tells the agent to read the page with its own web tools and pull out the title, the dimensions text, the price and a product image address.
2. The agent calls `roomsmith_add_product` with those fields. The plugin parses the dimensions text in code (`dims.py`): centimetres, millimetres, metres, inches, feet-and-inches; "W × D × H", "L × W × H", labelled or unlabelled; decimal commas.
3. The plugin adds a stand-in box at true size, labelled with the product name, marked `dimensioned_placeholder` with `dims_source: stated`, and runs the fit check.
4. If the page could not be read or has no dimensions, the agent asks the user for them. Typed dimensions always work.

The editor's side panel shows the product card: title, sizes, price, link, and the product image when the host allows it to load (not yet exercised with a real product URL in Desktop). The image is never required.

Out of 0.1: real 3D product models, retailer accounts or APIs, price tracking.

---

## 11. Agent tools

Toolset `roomsmith`. Nine tools, each with a description written for the model. All return JSON strings and never raise.

| Tool | Purpose | Key arguments |
|---|---|---|
| `roomsmith_projects` | List rooms, show or switch the active one, say how to open the editor | `action`: list / activate / rename / delete, `project_id` |
| `roomsmith_new_room` | Create a room from dimensions, or from a `layout` draft (Route B) | `name`, `width_m`, `depth_m`, `height_m`, or `layout` |
| `roomsmith_from_photo` | Read photos and build a draft room (Route A) | `images` (paths or photo IDs), `name`, `notes` |
| `roomsmith_inspect` | The current room in compact form: walls with lengths, openings, objects with IDs, sizes and positions, revision, open issues | `project_id`, `detail`: summary / full |
| `roomsmith_apply` | Apply one atomic batch of operations (section 7) | `project_id`, `expected_revision`, `operations` |
| `roomsmith_check` | Fit check: all issues, or a specific question | `project_id`, `question`: issues / fits_at / where_fits / passes_door, plus sizes and targets |
| `roomsmith_add_product` | Add a product as a true-size stand-in | `title`, `dimensions_text` or `dimensions_m`, `url`, `image_url`, `price`, `place` |
| `roomsmith_history` | Undo, redo, or list recent revisions | `project_id`, `action`: undo / redo / list, `steps` |
| `roomsmith_export` | Write the room to a file and return its path | `project_id`, `format`: json / glb / summary |

Also registered:

- **`/room`** — shows the active room, its revision and issue count, and how to open the editor.
- **Skill `roomsmith:room-design`** — the working loop (inspect → apply → check → report), unit and direction conventions, how to add a product from a link, when to ask for a measurement.
- **Hook `pre_llm_call`** — only in sessions that have already used a Roomsmith tool, and only when the user has changed the room in the editor since the agent last saw it. It adds two or three lines to the current turn: "Since revision 12 the user moved Armchair and resized Desk. Current revision 14." Nothing is injected otherwise. It is added to the user message for that turn only, so the cached system prompt is untouched.

Registration rule learned from the catalog validator: its probe calls `register()` against a stub that has methods but not properties. `register()` must therefore not touch `ctx.llm` or `ctx.state`; handlers read them lazily at call time.

---

## 12. Backend routes

Mounted by Hermes at `/api/plugins/roomsmith/`, behind the dashboard's auth. Thin wrappers over the same `rs_core.service` the tools use.

| Route | Purpose |
|---|---|
| `GET /projects` | List rooms and the active one |
| `POST /projects` | New room from dimensions |
| `GET /projects/{id}/head` | `{revision, updated_at, actor, summary}` — the cheap call the editor polls |
| `GET /projects/{id}/scene` | Full scene at the current (or a given) revision, with issues |
| `POST /projects/{id}/commands` | Apply a command; same envelope and results as the tool |
| `POST /projects/{id}/undo`, `/redo` | History |
| `GET /projects/{id}/history` | Recent revisions with summaries |
| `POST /projects/{id}/check` | Fit-check questions from the editor |
| `POST /photos` | Upload a normalised photo; returns a photo ID the agent can use |
| `GET /projects/{id}/export?format=glb|json` | Download |
| `GET /health` | Version, schema version, data path readable |

Live updates: the editor polls `head` once a second while visible and fetches the scene when the revision changes. The Desktop socket is an optional accelerator later; the Desktop docs say it is a no-op on some remote setups, so polling is the baseline.

---

## 13. The editor

One editor core, two thin shells.

**Core** (`web/src/editor`, three.js, no React): takes a canvas, a scene, and callbacks. Draws the room, handles picking and dragging, animates between revisions.

**Features in 0.1:**

- **Two views.** A 3D orbit view where walls facing the camera fade so you can see in, and a top-down plan view with wall lengths labelled. Dragging is most precise in plan view.
- **Select** by click or from the object list. **Move** by dragging on the floor, with snapping to walls, to other objects' edges, and to a 5 cm grid; overlapping objects tint as you drag. **Rotate** with a handle or the R key in 15° steps. **Resize** with numeric fields. **Duplicate**, **delete**, **lock**.
- **Room.** Drag a wall in plan view to resize a rectangular room; set height numerically; recolour walls and floor. Select an opening to slide it along its wall and edit its sizes.
- **Calibrate.** Pick a wall, door or object, type its real size, and the room rescales.
- **Side panel.** Object list, properties, issues (click one to focus it), history with undo and redo, project switcher, new room (dimensions or photo upload), product card, export.
- **Live with Hermes.** When a revision arrives from the agent, objects glide to their new places and a toast says what changed. Local edits apply at once, then are confirmed by the backend; on a revision conflict the editor refetches and reapplies.
- **Keyboard.** Undo, redo, delete, duplicate, rotate, toggle view, focus selection.
- **A sample room** on first open, so the editor is never empty.

**Desktop shell** (`desktop/plugin.js`): registers a pane beside the chat, a full page with a sidebar entry, a command-palette entry, and a status-bar chip showing the active room and issue count. Uses the SDK's components and theme variables only, and a `ResizeObserver` on the canvas.

**Dashboard shell** (`dashboard/dist/index.js`): the same editor as a tab in `hermes dashboard`, using the dashboard's own React and components. This is also the surface I can drive and screenshot in Chrome during development, which makes it the main test bed.

**Build constraints (verified in the Desktop docs and the catalog's desktop lint):**

- The Desktop file is loaded uncompiled. Only three imports resolve: `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`. Everything else, including three.js, must be bundled into the one file. JSX is compiled away at build time.
- The catalog lint refuses, in Desktop files: `eval(`, `new Function(`, dynamic `import()` outside the SDK, URL imports, `<script` or `createElement('script')`, selecting the app's own markup, observing `document.body`, and reaching for `webview`. The lint's own comments name bundled three.js as an expected case. The build runs this same lint and fails on any hit.
- No hardcoded colours; theme variables only.

**Settled 8 Nov (spike S4):** the bundled three.js editor loads in Hermes Desktop 0.21.0 as a right pane, passes the authoritative lint (0.23 `validate`), and is 593 KB. The full-page route (`#/roomsmith`, sidebar entry) mounts too, but only after a cold start — the Desktop hot-reloads panes and chips, not routes. The pane is the live-beside-chat surface; the page is the big-canvas surface for editing by hand.

---

## 14. Export

- **JSON** — the native, lossless project file. Re-importable.
- **GLB** — walls, floor, openings as gaps, objects as coloured boxes and cylinders, with names. Opens in Blender, macOS Quick Look and most 3D tools. Written directly with the standard library; no dependency. Lossy by nature.
- **Summary** — a text list of everything with sizes and positions, for sharing or shopping.

Out of 0.1: Blender scene export, USDZ, dimensioned floor-plan PDF.

---

## 15. Privacy and safety

To state in the README and the catalog PR (catalog rule 13 requires disclosure):

- **Network.** The plugin makes no network requests of its own. Photos you choose are sent to your active Hermes model provider through Hermes's own model access. Product pages are read by Hermes's web tools, not by the plugin. The editor may load a product image from the address the agent supplied.
- **Files.** Reads only image files you name or upload. Writes only inside `~/.hermes/plugin-data/roomsmith/` and to export paths you ask for.
- **No** shell commands, background processes, telemetry, credentials, or self-update.
- **Cost.** Each photo read is one call to your model with one to four images.

---

## 16. Catalog submission

### Checklist against the catalog's rules (**verified** from `plugin-catalog/README.md` and the submission guide on main)

| Rule | Our position |
|---|---|
| Public `https://` repo, loadable at the pinned commit | `https://github.com/devSebb/roomsmith`; root `plugin.yaml` + `__init__.py` + `desktop/plugin.js` + `dashboard/manifest.json` |
| Full 40-character SHA; quoted `version`; SHA bumps are new PRs | Pin once, late, after the clean-install test. Every later fix costs a new PR, so freeze before pinning |
| Submitter is the repo owner | PR from `devSebb`. On this Mac `gh` is logged in as both `click-dev1` (active) and `devSebb`; switch before publishing |
| Declared capabilities match what `register()` registers | A test asserts the tool and hook lists in `plugin.yaml` equal what a recording context sees |
| Security scan: nothing "dangerous" | No shell, no eval, no secrets, no binaries; run the scanner locally before pinning |
| Desktop plugins stay inside the SDK | Build-time lint, same rules as admission |
| No core overrides; public surfaces only | Only `ctx.*`, `plugins.plugin_storage`, and the documented SDKs |
| Dependencies within Hermes's constraints | None declared |
| Credentials only through Hermes | None used |
| Approvals respected | No auto-approval, no child processes |
| Risks disclosed | Section 15, copied into the PR and README |
| Truthful `requires_hermes` (SemVer floor, not newer than the current release), same in `plugin.yaml` and the entry | Set from what we actually tested |
| No unscannable payloads | Text only; built JS is reproducible from `web/` |
| Tool names must not collide with built-ins | All prefixed `roomsmith_` |

### The catalog entry (draft)

```yaml
name: roomsmith
title: Roomsmith
repo: https://github.com/devSebb/roomsmith
sha: "<40-character commit>"
description: "Turn a room photo into an editable 3D room that you and Hermes edit together: drag furniture in a live editor inside Hermes Desktop, or tell Hermes what to change, against one saved room with undo. Add products from a link as true-size stand-ins and ask whether they fit. Disclosure — …"
maintainer: devSebb
tier: community
category: desktop
requires_hermes: ">=0.21.0"
version: "0.1.0"
platforms: [macos, linux]
docs_url: https://github.com/devSebb/roomsmith#readme
image: "https://raw.githubusercontent.com/devSebb/roomsmith/<sha>/docs/banner.png"
screenshots:
  - "https://raw.githubusercontent.com/devSebb/roomsmith/<sha>/docs/editor.png"
readme: true
known_issues:
  - "Sizes from a photo are estimates until you set one real measurement."
  - "iPhone HEIC photos must be exported as JPEG first."
capabilities:
  provides_tools: [roomsmith_projects, roomsmith_new_room, roomsmith_from_photo, roomsmith_inspect, roomsmith_apply, roomsmith_check, roomsmith_add_product, roomsmith_history, roomsmith_export]
  provides_hooks: [pre_llm_call]
  provides_middleware: []
  requires_env: []
```

Windows is left out of `platforms` unless someone tests it.

### The PR

One file. The description says what the plugin does, which Hermes surfaces it uses, the disclosures, and includes screenshots. The catalog's CI clones the repo at the pin and runs `hermes plugins validate`; a maintainer starts those checks.

---

## 17. Testing

| Layer | What | When it must pass |
|---|---|---|
| Engine unit tests | Every operation, hard rule, soft issue, placement mode, undo/redo path, conflict, idempotent replay, dimension parsing, layout building from recorded drafts. Plain Python, no Hermes | Every commit |
| Two-process test | One process writes through the tool path while another reads through the backend path; no lost or torn revisions | M1 |
| Registration contract | `register()` against a recording context: registered tools and hooks equal `plugin.yaml`; no property access on `ctx` during registration | Every commit |
| `hermes plugins doctor . --ci` | Hermes's own load check, in the isolated Mini test home (and on the MacBook v0.21.0 as the lower bound) | Every milestone |
| `hermes plugins validate` | The catalog's admission checks, on Hermes v0.23.0 in a separate throwaway copy | M0 (skeleton), M6, before pinning |
| Backend API tests | FastAPI test client over every route | M3 |
| Editor math tests | Snapping, coordinate conversion, hit-testing as pure functions | M3 |
| Editor in Chrome | Dev harness and dashboard tab driven and screenshotted in Chrome | M3 onward |
| Editor in Hermes Desktop | Manual checklist run with Sebb watching the real app | M3, M6 |
| Photo scorecard | Five or more real photos: did a room appear, share of main furniture found, door and window found, sizes within ±25 % after calibrating one wall | M0 (three photos), M4 |
| Conversation script | Twelve fixed prompts against real Hermes, each with an expected change in the scene | M2, M5, M6 |
| Clean install | Fresh machine or profile: install from the public repo at the pin, enable, run the demo script | M7, by Harvey on the Mini if available |
| Catalog lints on built files | Desktop surface lint and file-size limits | Every build |

### Development environment and machine roles

These rules come from Sebb and Harvey (7 November) and override anything earlier in this document that reads differently.

| Machine | Role | Allowed | Not allowed |
|---|---|---|---|
| MacBook (this machine) | **All implementation and all project Git writes.** Engine tests in a repo-local virtual environment. Editor dev harness in Chrome. | Everything in the repo; the unused local Hermes v0.21.0 as a lower-bound runtime check | Pushing without Sebb's go |
| Mac mini (over Tailscale SSH as `jessica`) | **Runtime testing only, in an explicitly approved isolated Hermes home** with its own config, plugin-data, dependencies/venv and model sign-in. Later, Harvey's clean-install test. | Reading versions and docs; running the plugin inside the isolated home once approved | Installing into or copying code into the live `~/.hermes` or `~/.hermes/plugins/`; touching production profiles, shared dependencies, gateways, Mission Control or Tailscale; changing SSH config or keys without instruction |
| GitHub `devSebb/roomsmith` | Distribution. Final installs happen from a pinned commit with `hermes plugins install devSebb/roomsmith --ref <sha>` | Public repo once Sebb says so | Self-updating; force-pushes to pinned history |

Code reaches the mini only through Git (clone of a pushed commit into the isolated home), never by copying a working tree.

**Desktop against a remote backend (verified in the Desktop SDK docs, 7 Nov):** the Desktop app only scans the *local* machine's `~/.hermes/plugins` and `~/.hermes/desktop-plugins` for a `desktop/plugin.js`; the remote box's plugin folder is not reachable as a filesystem. So for a demo with Desktop on the MacBook talking to the Mini, the Desktop half is installed on the MacBook (or the whole package in the MacBook's `~/.hermes/plugins/roomsmith`, desktop half enabled in Settings → Plugins) while `ctx.rest` reaches the Mini's `/api/plugins/roomsmith/`. Alternatively Desktop runs on the Mini itself. Both are supported arrangements; which one we use is Sebb's call.

**Local lower-bound runtime (set up 7 Nov):** `.scratch/hermes-home/` is an isolated `HERMES_HOME` on the MacBook with `plugins/roomsmith -> <repo>` and `plugins.enabled: [roomsmith]`; `HERMES_HOME=<that> hermes dashboard --port 9119 --no-open` serves the tab from the MacBook's unused 0.21.0 install without touching its real `~/.hermes`. Harvey reviews immutable commits; C1/C2/C3 handoffs are kept substantial. Ordinary testing work is batched; only genuine access, safety, budget or scope blockers are escalated.

---

## 18. Milestones

Each milestone has a goal, deliverables, and exit criteria that are yes-or-no. Times are targets, in EST.

### M0 — Proof (Friday 6 November)

**Goal:** remove every unverified item the plan depends on before writing real code.

| Spike | Question | Pass |
|---|---|---|
| S0 | Can the Mini be reached read-only, and what Hermes version and model does it run? | **Passed 7 Nov:** `jessica`, Hermes v0.21.5 (git, dirty tree), Python 3.14.7. Model (GPT astra) per Sebb, not yet read from config |
| S1 | Does a skeleton plugin load in the approved isolated Mini test home (and in the MacBook v0.21.0 as lower bound)? | **Passed 7 Nov on 0.21.0 (MacBook, isolated home):** `hermes plugins doctor --ci` OK (9 tools, 1 hook); the dashboard tab and backend run inside the real `hermes dashboard`. **Mini 8 Nov:** pinned install at 0bf14fc + doctor passed in the test home (0.23.0+689); a chat turn is blocked until Sebb signs the test home into Codex |
| S2 | Does `ctx.llm.complete_structured` accept an image through the plugin LLM door on the Mini's model (GPT astra, subscription)? This is a different door from chat and may use Hermes's vision-fallback routing | Pending (Mini test home). Code path implemented with a fallback ladder; tested with a fake `ctx.llm` |
| S3 | Is a photo-read draft good enough to be worth editing? | In progress: one real photo (narrow room, French doors, futon) in `fixtures/photos/` with a reference draft; the pipeline builds a plausible room from it offline — door centred on the back wall, futon along the right wall, warnings for the futon clipping the door's clear zone (true in the photo). Model-read quality is measured on the Mini (S2); more photos widen the scorecard |
| S4 | Does a Desktop pane with bundled three.js load, pass the lint, and stay under 1 MB? | **Passed 8 Nov:** Hermes Desktop 0.21.0 (+37159) on the MacBook, launched fully isolated; Roomsmith discovered under Settings → Plugins, pane renders the WebGL room, `ctx.rest` works behind auth; 593 KB; the authoritative desktop-surface lint passed on the Mini. Full page verified after a cold relaunch (routes are registered at app start, not hot-reloaded). Live follow verified: a room created by the agent (photo pipeline) opens in the running editor within a second with a toast |
| S5 | Does a tool write in chat reach the pane through the backend? | **Passed 7 Nov (dashboard) and 8 Nov (Desktop):** an agent-actor command appears in the editor within ~1–2 s (long-poll) with a toast and a flash |
| S6 | How does a photo attached in chat reach a tool? | Pending on the Mini. Route B (`new_room` with `layout`) is implemented and tested as the path that needs nothing from the host |
| S7 | Can we run `hermes plugins validate` without touching any live install? | **Passed 8 Nov** on the Mini test checkout (0.23.0+689) at 0bf14fc, run by Harvey through `run-isolated.py`: all 16 checks ✓. Note `validate` takes a directory; it also reports that on 0.23 the plugin runs in the plugin host and the dashboard API is proxied with buffered responses |

**Exit:** a filled-in results table. Any failed spike has its fallback chosen (section 19) before M1 starts.

### M1 — Room engine (Saturday morning) — **done Friday 7 Nov** (73 tests; commit 1091695)

**Goal:** the room exists as data, with edits, rules and history, independent of Hermes.

**Deliverables:** `rs_core` complete for model, ops, placement, geometry, validate, store, service; the test suite.

**Exit:** all engine tests pass; the two-process test passes; a script creates a room, applies twenty mixed commands, undoes ten, redoes five, and the final scene matches a stored expected file.

### M2 — Hermes can edit a room (Saturday afternoon) — **done Friday 7 Nov** (doctor passes; commit 2338cef)

**Goal:** a complete chat-only experience.

**Deliverables:** nine tools, `/room`, the skill, `plugin.yaml`.

**Exit:** in a real Hermes chat, with no editor: create a 4 × 5 m room, add five objects, "swap the sofa and the desk", "put the bookshelf against the north wall", ask "does anything overlap?", undo twice. Each step changes the saved scene as expected. Doctor passes.

### M3 — The editor (Sunday) — **core done Friday 7 Nov** (commit 3fd350b); Desktop-app run and polish remain

**Goal:** see and edit the room by hand, live with Hermes.

**Deliverables:** backend routes; editor core; dashboard tab; Desktop pane and page; build pipeline with lint.

**Exit:** in Chrome (dashboard) and in Hermes Desktop: the room renders in both views; select, move with snapping, rotate, resize, delete, undo and redo work; an edit made by Hermes in chat animates in the editor within two seconds; an edit made by hand is visible to `roomsmith_inspect` at once.

### M4 — Photo to draft, and calibration (Monday morning)

**Goal:** the opening moment of the demo works on real photos.

**Deliverables:** `roomsmith_from_photo`, Route B in `new_room`, the layout builder with the fallback ladder, photo upload in the editor, the calibrate tool and operation, the draft badge.

**Exit:** the photo scorecard passes on five photos; every fallback rung is exercised by a test; calibrating one wall rescales everything.

### M5 — Products, fit check, awareness (Monday afternoon)

**Goal:** the plugin answers "will it fit?" and notices manual edits.

**Deliverables:** `dims.py`, `roomsmith_add_product`, `fitcheck` questions, issue markers in the editor, the `pre_llm_call` hook, GLB and JSON export.

**Exit:** thirty real-world dimension strings parse correctly; pasting a product link in chat yields a true-size stand-in and a fit verdict with numbers; after dragging an object by hand, Hermes mentions the change unprompted in its next relevant answer and stays silent in unrelated sessions.

### M6 — Polish and hardening (Tuesday morning)

**Goal:** it feels finished and survives a stranger.

**Deliverables:** sample room, empty and error states, toasts, keyboard shortcuts, performance pass (60 objects stay smooth), README with install and enable steps, screenshots and banner, changelog, licence, notices, CI workflow, known issues.

**Exit:** the twelve-prompt conversation script passes end to end; `hermes plugins validate` passes on v0.23.0 with no failures and every warning read; the Desktop checklist passes with Sebb watching; no file over 1 MB.

### M7 — Ship (Tuesday afternoon to Wednesday noon)

**Goal:** entered, with buffer.

**Steps, each needing Sebb's explicit approval because they are public:**

1. Create the public repo under `devSebb`, push, confirm CI is green.
2. Clean-install test from the public repo on another machine or profile.
3. Freeze. Pin the SHA. Open the catalog PR.
4. Record the demo (section 18a). Sebb posts it on X tagging @NousResearch.
5. Submit the form with both links.

**Exit:** PR open, video posted, form submitted, by Wednesday 12:00 noon EST.

### If we fall behind

Cut in this order, decided now so it is not argued at midnight: GLB export → product images → multi-photo input → non-rectangular rooms → the awareness hook → the dashboard tab's polish (keep it working for testing).

Never cut: the engine and its tests, the tools, move/rotate/resize with undo in the editor, the photo draft with its fallbacks, the fit check, the README, the catalog checks, the demo.

### 18a. Demo script (under 90 seconds)

| Time | On screen | Shows |
|---|---|---|
| 0–8 s | A room photo dropped into Hermes Desktop: "Build this room." | The hook |
| 8–22 s | The 3D room appears beside the chat with a "Draft" badge. "The back wall is 4.2 m." The room rescales | Photo → editable room; honest labels |
| 22–40 s | "Swap the sofa and the desk, and put the bookshelf against the window wall." Furniture glides into place | Talking to the same room |
| 40–52 s | The armchair is dragged by hand. "Does anything block the door now?" Hermes: "The armchair is 30 cm inside the door swing." | Two-way awareness; real geometry |
| 52–70 s | A product link pasted: "Would this sofa fit instead?" A true-size stand-in appears; Hermes gives the clearance in centimetres | Usefulness |
| 70–82 s | Undo twice. Plan view with measurements. Export | Reliability and polish |
| 82–90 s | "Roomsmith — a Hermes plugin. No extra accounts." and the install line | The close |

---

## 19. Risks and fallbacks

| Risk | Likelihood | Fallback |
|---|---|---|
| Photo drafts are poor (S3) | Medium | Lead the demo with Route B or a photo that works well; keep "draft" framing; lean the pitch on editing and fit checks. The plugin still works from typed dimensions |
| `ctx.llm` image input fails on some models (S2) | Low–medium | Route B; clear message; default room |
| Bundled three.js fails the Desktop lint or the 1 MB limit (S4) | Low–medium | Strip unused three.js modules; if still failing, draw the room with the 2D canvas in plan view plus a simple isometric view, as `office-3d` does without three.js |
| The Desktop pane cannot be made reliable in time | Low | The dashboard tab becomes the main editor; the Desktop half ships as a status chip and a link |
| An attached photo does not reach a tool as a path (S6) | Medium | Route B for attached photos; upload through the editor; typed path |
| Hermes v0.23.0 behaves differently from v0.21.0 | Medium | Test on both from M0; Sebb decides whether to update the main install on Monday; Harvey's clean install as a second check |
| HEIC photos from iPhones | High for real users | Clear message in 0.1 and a known issue; conversion in 0.2 |
| The model picks the wrong tool or bad coordinates | Medium | Relational placement; precise tool descriptions; the skill; issues returned after every edit so it can self-correct |
| Catalog check finds something late | Medium | Run `validate` from M0; run it in CI on every push; pin only after a clean pass |
| A fix is needed after pinning | Medium | Each re-pin is a new PR. Freeze and clean-install before pinning |
| GitHub identity mix-up at publish | Low | Switch `gh` to `devSebb` and confirm before the first push |
| Time | High | The cut list above; the internal noon deadline |

---

## 20. Beyond the hackathon — the ideal

Each stage keeps the same scene and command model, so nothing built now is thrown away.

| Version | Theme | What it adds |
|---|---|---|
| 0.2 | **Measured rooms** | Several photos or a short video → metric depth → walls fitted as planes, so shape and size come from geometry, not a guess. Research so far points at Depth Anything 3 or MapAnything for depth, and plane fitting for walls; none has been run on this Mac. Import of phone room scans is worth investigating. Non-rectangular rooms in the editor. HEIC support |
| 0.3 | **Real objects** | Optional mesh providers behind one interface, off by default (for example SAM 3D Objects on fal.ai, about $0.02 per object in earlier research). Matching stand-ins to free CC0 furniture models from Poly Haven. Materials, textures, lighting presets. "Render this view" through Hermes's image-generation provider |
| 0.4 | **Products** | Structured product reading (JSON-LD) through the user's own browser; real 3D models where a retailer's page publishes one; a shopping list with totals; "find me alternatives that fit" |
| 0.5 | **Interchange** | Dimensioned floor-plan PDF and SVG; USDZ; a one-way Blender export, handing off to the official Blender plugin when it is installed |
| 1.0 | **Home** | Several rooms and floors; use from Telegram or other messaging apps (send a photo, get a snapshot back); project sharing; a request for `verified` tier |

Deferred from the v2 brief on purpose: the MacBook-to-Mini remote setup, payment and budget machinery, required retailer connectors, and the three-checkpoint review process. One independent clean-install test replaces the last of these for now.

---

## 21. Decisions needed from Sebb

1. **Go to start M0.** Model calls run on the Mini's subscription (GPT astra), so cost is not a factor there; the handful of MacBook-side calls, if any, go through the local OpenRouter key and are small.
2. **SSH to the Mini.** This MacBook's public key (`~/.ssh/id_ed25519.pub`) must be added to `/Users/jessica/.ssh/authorized_keys` on the Mini by Sebb or Harvey. I will not change SSH config or keys myself.
3. **The isolated Mini test home.** Approval for one directory on the Mini (proposed `/Users/jessica/roomsmith-test/`) holding its own `HERMES_HOME`, config, plugin-data, Hermes copy/venv and model sign-in, used only for this plugin's runtime tests. Nothing in the live `~/.hermes` is read or written by it. Separately, a throwaway Hermes v0.23.0 (MacBook or that same test directory) for `hermes plugins validate`.
4. **Photos.** Three to five photos of real rooms as JPEG. They stay out of git unless you say otherwise. One will appear in the demo video.
5. **Repo name and licence.** Proposed: `devSebb/roomsmith`, MIT. Public from Tuesday.
6. **Harvey.** Can Harvey do a clean-install test on the Mini on Tuesday?
7. **The demo.** You record and post; I prepare the script, the room and the prompts.

---

## 22. Sources for what is marked verified

| Fact | Source |
|---|---|
| Plugin structure, `register(ctx)`, tools, hooks, commands, skills, storage, compatibility contract | `~/.hermes/hermes-agent/website/docs/developer-guide/plugins/index.md` (v0.21.0) |
| Desktop plugin contract, unified package, backend mount, import limits, enable switches | `…/developer-guide/desktop-plugin-sdk.md` (v0.21.0) |
| Dashboard plugin contract and backend routes | `…/user-guide/features/extending-the-dashboard.md` (v0.21.0) |
| `ctx.llm` API, image input, trust gate, vision fallback | `…/developer-guide/plugin-llm-access.md` and `agent/plugin_llm.py` (v0.21.0) |
| Backend imported standalone and gated on `plugins.enabled` | `hermes_cli/web_server.py`, `_mount_plugin_api_routes` (v0.21.0) |
| `plugin_data_dir`, `plugin_db` | `plugins/plugin_storage.py` (v0.21.0) |
| Catalog entry fields and admission rules | `plugin-catalog/README.md` and `website/docs/developer-guide/plugins/catalog-submission.md` on `main`, fetched 6 November 2026 |
| What `hermes plugins validate` checks; probe stub behaviour | `hermes_cli/plugin_validate.py` on `main` |
| Desktop lint rules | `hermes_cli/plugin_validate_desktop.py` on `main` |
| File-count and size limits | `tools/plugin_guard.py` on `main` |
| Public plugin API list (includes `plugins.plugin_storage`, `agent.plugin_llm`) | `hermes_cli/data/plugin_api.json` on `main` |
| 1,065 catalog entries, none for rooms or interiors | GitHub tree listing of `plugin-catalog/` on `main`, searched by name |
| Reference package shape | `oslook/hermes-desktop-plugin-office-3d` file listing and its catalog entry |
| Latest release v0.23.0 | GitHub releases API |
| Installed version, Python 3.11.15, Pillow / FastAPI / jsonschema / numpy available, `gh` accounts, Node 26 | Commands run on this MacBook, 6 November 2026 |
| MacBook's unused Hermes install uses `anthropic/claude-opus-4.6` through OpenRouter | The `model:` block of the MacBook's `~/.hermes/config.yaml`. Not the Mini: the Mini runs GPT astra on a subscription (Sebb, 7 November; not yet read from the Mini) |
