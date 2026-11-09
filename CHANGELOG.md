# Changelog

## 0.1.0 (in progress)

Built 2026-11-07, hackathon week.

- Engine (`rs_core`): scene model, 17 operations with relational placement,
  hard validation and soft issues, fit checks, SQLite store with full-snapshot
  revisions, undo/redo, idempotent commands, cross-process write transaction,
  product dimension parsing, draft→scene layout builder, GLB export.
- Agent half: nine `roomsmith_*` tools, `/room`, `room-design` skill,
  `pre_llm_call` awareness hook; photo reading through `ctx.llm` with a fallback
  ladder.
- Dashboard backend: FastAPI routes incl. long-poll `wait` and base64 export.
- Editor: three.js 3D/plan editor with snapping, live revisions, inspectors,
  calibration, products, fit questions, exports; Desktop and dashboard shells.
- Verified on Hermes 0.21.0: `hermes plugins doctor --ci`, dashboard tab live.
- 2026-11-08: verified in Hermes Desktop 0.21.0 (isolated launch): pane, sidebar
  entry, status chip, `ctx.rest`, live agent→pane sync. `hermes plugins validate`
  passed on a 0.23.0 checkout (Mini test home). `add_opening` accepts `wall`
  (id or label) and defaults `width_m` (door 0.9 m, window 1.2 m). Toasts and
  chips readable on dark hosts; narrow pane keeps a usable side panel; the
  long-poll window adapts to proxies that cut long requests.
- 2026-11-08 (later): the editor follows the agent — when Hermes creates or
  opens another room, the long-poll (`wait?active=`) wakes at once and the open
  editor switches to it with a toast. Fixed: switching rooms by hand left the
  previous room's long-poll in flight and never started one for the new room,
  so live sync stopped after a switch (covered by `web/tests/store.test.mjs`).
  Full-page route confirmed working in Desktop after a cold start (routes are
  not hot-reloaded). Photo pipeline exercised offline on the first real room
  photo (PNG/RGBA → JPEG normalisation, draft → scene, photo registration).
- Layout builder: a small plant/box/'other' whose footprint lands on a table,
  desk, dresser, shelf etc. is placed on top of it (surface mount) instead of
  overlapping it on the floor — the first real photo had a plant on a side table.
- CI (`validate.yml`) and the catalog entry draft (`catalog/roomsmith.yaml`).
- `tests/test_demo_script.py`: the §18a demo run beat by beat through the tool
  handlers (photo → calibrate → swap/move → manual drag → blocks-door check →
  product → undo → export); 86 tests.
- Editor: no right-button binding (Hermes Desktop owns right-click for its own
  menu); pan is ⇧-drag or middle-drag, shown in the hint. 60-object room measured
  at 60 fps in Desktop during orbit and drag.
- From the first live photo read on the Mini (gpt-6-astra, S2 passed): the draft
  schema gains `mount` and `elevation_m`; a new `lamp_ceiling` category (aliases
  pendant, chandelier, ceiling light…) and label-based detection when the model
  says 'other'; wall-mounted things get a height; fit checks are height-aware
  (anything whose underside is ≥ 1.9 m, or mounted on the ceiling, no longer
  blocks doors or walkways); draft notes clip at a word boundary (500 chars);
  `next_step` tells the agent to review draft issues with the user, not fix them
  blindly. S1 chat smoke passed on the Mini; `--image` is rejected by the gateway
  CLI (S6 blocked there; path route works).
- Dimension parser: when a page gives W and L (Floyd beds: `67" W x 86" L`), L is
  the depth for beds, cribs, rugs, benches, bathtubs and mattresses, and the width
  across the front for everything else (sofas, tables). `add_product` passes the
  category inferred from the title. Tested with strings copied from live pages.
- 2026-11-09: second live run on the Mini (bedroom, three photos, 562920b) passed
  every beat: one `roomsmith_from_photo` call with all three images, the agent
  chose `room_size` calibration from "the room is 2.82 by 4 metres", answered a
  wardrobe fit question with `fits_at` numbers (and a sensible 20 cm caveat),
  `/room`, full inspect. Scorecard in `docs/compat.md` (S3); scoring script
  `scripts/score-draft.py`. Fixed: `roomsmith_inspect detail=full` now includes
  the summary fields (calibration was null). Photo instructions: depth from
  side-wall furniture, no bias either way.
- Calibration rethought after the first ground truth (Sebb's room is 2.85 × 3.0 m;
  the photo read said 2.65 × 4.4 — width 7 % off, depth 47 % over, the wide-angle
  stretch): new `calibrate {kind: 'room_size', width_m, depth_m}` fits each axis
  separately, keeps furniture sizes, keeps things against their walls and nudges
  apart what the compression pushed together (the larger piece gives way when the
  smaller is already on a wall; things on tables ride along). Wall/height/opening
  references now also keep furniture sizes; object references still scale
  everything estimated. Editor Room tab: "Fit room" (width × depth) first, one
  wall length second. Photo instructions: estimate depth from furniture along the
  side walls, not from how far the back wall looks.
- Editor: when the shown room is deleted it moves to the active room instead of
  dead-ending; the 3D scene clears when none is open; the camera re-frames when
  the walls move (fit to the room's bounding sphere and the viewport's FOV);
  ceiling-mounted objects render translucent; layout mode decided before first
  paint; the editor instance is exposed on `.rs-root.__rs` for the smoke script.
- `web/dev/desktop-attach.mjs` + `web/dev/desktop-smoke.mjs`: the Desktop checklist
  as a script (sidebar entry, pane + WebGL, ctx.rest, status chip, full page, New
  room, editor follows an agent-created room, undo). `scripts/pin-catalog.py`
  fills the catalog entry from a green, pushed commit.
