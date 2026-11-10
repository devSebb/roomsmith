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
- **Procedural furniture** (`web/src/editor/shapes.ts`): a dozen shape families built
  from the measured size — beds (frame, mattress, pillows, headboard), seating
  (seat, cushions, back, arms, legs), chairs, tables and desks, drawers and
  doors with handles, shelving, floor/table lamps, pendants and ceiling fans,
  plants, TVs, mirrors/pictures, tubs, rugs; unknown categories stay boxes.
  Plank floor from a procedural texture at real scale, skirting boards, warmer
  light; walls no longer shade the interior. The picked/dragged volume is still
  the object's bounding box. Bundle 606 KB.
- **Products from links, read by the plugin** (`rs_core/product_fetch.py`): schema.org
  Product JSON-LD, Shopify product JSON, OpenGraph and visible text, stdlib only,
  one request to the pasted URL; bot-check pages and refusals come back as
  `blocked`, pages without printed sizes as `dimensions_not_found` — never a
  guess. New tool `roomsmith_read_product`; `roomsmith_add_product` accepts a
  URL alone and adds a true-size stand-in wearing the product's photo (thumbnail
  cached in plugin data, composited on white), name, price and link. Live on
  castlery.com. Dimension parser reads glued labels (`W88.6" x D39.4"`).
- `roomsmith_check fits_at`: `object_id` + `dimensions_m` now tests a replacement
  (new size where the old object stands, hugging the same wall, old object
  ignored) and the result names what it replaces; an overlap without
  `object_id` hints at the replacement form. From the Mini product run, where
  the old semantics said a longer bed fits because it measured the old bed.
  Skill/tool text: how to read a page without an extraction backend (curl),
  never present remembered sizes as page data, pass `category` for beds.
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
- 2026-11-10: **no more desks inside beds.** A described placement or move
  (`against_wall`, `next_to`, `in_corner`, `centered_in_room`) that would land a
  floor piece inside another slides it to the nearest clear spot — along the same
  wall first — and the receipt says so ("slid 0.62 m along the wall to clear the
  bed"); exact `position_m` (editor drags) and `allow_overlap: true` are honoured
  as given; when nothing nearby is free the receipt says that instead of hiding
  it. Things sitting on furniture (`mount: surface`) now move, rotate and fall to
  the floor with their host. Seen in the Desktop dry run: Hermes put a 1.2 m desk
  "where the bed was", 60 cm inside the bed, and reported it rather than fixing it.
- 2026-11-10: product pages: dimensions buried in inline scripts (Shopify section
  JSON, Next.js payloads) are read; shipping-box lines ("Package: 29 x 25 x 15 |
  44 lbs", "(1 of 2) - 83” x 13” x 5”") lose to the product's own; the size
  variant the user asked about wins ("Queen: 68” W x 93” D" for `bed_queen`);
  a page that prints only the footprint (desk tops: "48 inches x 27 inches") gets
  the category's usual height, with a note; a Shopify JSON without sizes falls
  through to the page. Read correctly live from the MacBook: Castlery (Hamilton
  sofa, Casa dining table), Sixpenny (Neva sofa, Neva chair), Albany Park (Kova
  sofas), Thuma (Classic Bed, queen), Branch (Tria desk, Ergonomic chair).
- 2026-11-10 (later): editor toolbar **Labels on/off** (also the `L` key) hides every
  name tag at once; the selected or hovered object keeps its tag so you never lose
  what you are pointing at. Asked for by Sebb during the Desktop dry run — the old
  "Aa" button did this but nobody found it.
- 2026-11-10 (evening): the editor's **GLB** button exports what the editor shows —
  furniture shapes, plank floor, skirting, openings, product tags, walls made solid
  — via three's GLTFExporter in the browser, instead of the engine's box-per-object
  file (Sebb opened one in Quick Look: a ceiling fan as a floating black box). The
  engine export (`roomsmith_export` tool, dashboard URL) is unchanged and stays
  the box version; the editor falls back to it if the browser export fails.
  Verified by reloading the file with GLTFLoader: 97 nodes, 275 KB for the
  15-object showroom, ~4 s to produce.
