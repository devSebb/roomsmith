---
name: room-design
description: Design and furnish a room with Roomsmith — read the room, edit it, check what fits, add real products, keep the user's editor in sync.
---

# Room design with Roomsmith

Roomsmith keeps one editable 3D room per project. You and the user edit the
same room: you through the `roomsmith_*` tools, the user by hand in the
Roomsmith editor (Hermes Desktop pane or dashboard tab). Every edit is a
numbered revision with undo.

## The loop

1. **Inspect first.** `roomsmith_inspect` gives wall ids and labels, every
   object's id, size and position, the revision number, and open issues.
   Never guess an id; never edit from memory of an older turn.
2. **Edit in one batch.** `roomsmith_apply` with `expected_revision` and a
   list of operations. All apply or none. On `revision_conflict`, inspect
   again and retry — the user changed something in the editor.
3. **Read the result.** The reply lists what changed and any issues the
   change caused (`overlap`, `outside_room`, `blocks_door`, `blocks_window`,
   `tight_walkway`, `too_tall`). Fix them or tell the user, in one sentence.
4. **Quote numbers from tools**, with units. Do not estimate clearances or
   whether something fits — ask `roomsmith_check`.

## Conventions

- Metres and degrees. `dimensions_m` is `[width, height, depth]`: width across
  the front, depth front to back.
- Walls: `w1` back, `w2` right, `w3` front, `w4` left (as seen from the
  camera that took the photo, or from the front wall for a typed room).
  You can use the labels `back`, `right`, `front`, `left` in place of ids.
- `left` / `right` on a wall are as seen from inside the room facing that
  wall. `left` / `right` / `front` / `behind` of an object are relative to
  that object's own facing.
- Prefer relational placement over coordinates: `{"against_wall": "w1",
  "align": "center"}`, `{"next_to": "ob2", "side": "left"}`,
  `{"in_corner": ["w1", "w2"]}`, `{"centered_in_room": true}`,
  `{"on": "ob3"}` (rest on top), `{"by": [0.3, 0]}` (nudge).
- Objects placed against a wall automatically face into the room.

## Starting a room

- **The user gives sizes** → `roomsmith_new_room` with `width_m`,
  `depth_m`, `height_m`. The room is calibrated.
- **The user attaches a photo and you can see it** → estimate the room and
  furniture yourself and call `roomsmith_new_room` with `layout`. Use real
  anchors: a door is about 0.8 x 2.03 m, a counter 0.9 m high, a sofa seat
  0.45 m high. Name walls from the camera: back / left / right / front.
- **The user gives a file path** → `roomsmith_from_photo` with the path.
- Either photo route produces **estimated** sizes. Then ask for the room's real
  floor size (best) or ONE real length, and apply
  `{"op": "calibrate", "reference": {"kind": "room_size", "width_m": 2.85, "depth_m": 3.0}}`
  (fits width and depth separately — phone photos stretch depth; furniture keeps
  its size and stays against its walls) or
  `{"op": "calibrate", "reference": {"kind": "wall_length", "id": "w1", "real_m": 4.2}}`.
  Until then every reply should say sizes are estimates. Draft issues (blocked
  door etc.) come from estimated positions — mention them, ask before moving things.

## Products from links

1. Read the page. Use a page-reading tool if you have one (`web_extract`,
   `fetch`, browser). If the only web tool is search-only, fetch the HTML from
   the terminal instead — `curl -sL <url> | sed 's/<[^>]*>/ /g' | grep -i -E
   'overall|dimensions|[0-9]+ ?(cm|in|") ?[WwDdHhLl]'` — and read the
   dimensions out of that. Extract: title, the dimensions text exactly as
   written, price, and the main product image URL.
2. `roomsmith_add_product` with `dimensions_text` (the plugin parses cm,
   mm, m, inches, feet; labelled or unlabelled) and `category` when the title
   makes it obvious (bed, sofa…). If the reply says `assumed_order`, tell the
   user the sizes were read as width x depth x height and ask if that matches.
3. Report the reply's `clearance_m` and `passes_door` in plain words.
4. Could not read the page at all → say so and ask the user for the sizes
   printed on it, then pass `dimensions_m`. **Never state product dimensions
   from memory as if they came from the page**; if you must estimate, say
   "estimated, not from the page" and mark the object `dims_source`
   estimated by passing `dimensions_m` without `dimensions_text`.
5. "Would THIS fit where my X is?" → `roomsmith_check` `fits_at` with
   `object_id` = X **and** `dimensions_m` of the new item (replacement test);
   without `object_id` it will just overlap X and say no.

Never fetch anything on the plugin's behalf other than the pages the user
asked about.

## When the user edits in the editor

A note at the start of your turn lists what they changed. Acknowledge it in
a few words and inspect before your next edit. Do not undo their changes
unless asked.

## Finishing

- `roomsmith_export` with `glb` for a 3D file, `summary` for a shopping
  list with links, `json` to save the project.
- Keep replies short: what you did, the issues if any, one next step.
