---
name: room-design
description: Design and furnish a room with Roomsmith — read the room, edit it, check what fits, add real products, furnish to the user's budget, keep the user's editor in sync.
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
   A described placement (`against_wall`, `next_to`, `in_corner`,
   `centered_in_room`) that would land inside another floor piece or in front of a door is slid to
   the nearest clear spot automatically — the receipt says by how much
   ("slid 0.62 m along the wall to clear the bed"); repeat that to the user.
   Only things that sit *on* furniture (`mount: surface`, e.g. a lamp on a
   desk) may share a footprint; they move with their host. Never leave two
   floor pieces overlapping; if the receipt says "no clear spot nearby",
   offer to move or remove something.
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

1. The plugin reads the page itself: `roomsmith_read_product {url, category?}`
   returns title, price, image and the printed dimensions parsed to metres
   (schema.org Product data, Shopify stores, plain HTML). To add straight
   away, call `roomsmith_add_product {url, place?}` with nothing else — it
   reads the page, adds a true-size stand-in with the product's photo, name,
   price and link, and reports clearance and door passage.
2. If the reply says the page prints no readable dimensions, or the site
   blocked the request (`blocked`), say so and ask the user for the size
   printed on the page, then call `roomsmith_add_product` with `title`,
   `dimensions_text` exactly as the user wrote it (or `dimensions_m`), `url`.
   **Never state product dimensions from memory as if they came from the
   page.** If the user asks for an estimate, pass `dimensions_m` without
   `dimensions_text` and say it is estimated.
3. Pass `category` when the user said what it is (bed, sofa, desk…): a bed's
   "L" is its length, a sofa's "L" is its width.
4. Report `clearance_m` and `passes_door` in plain words, in centimetres.
5. "Would THIS fit where my X is?" → read the product, then `roomsmith_check`
   `fits_at` with `object_id` = X **and** the product's `dimensions_m`
   (replacement test); without `object_id` it will just overlap X and say no.

Never fetch anything on the plugin's behalf other than the pages the user
asked about.

## Furnishing to a budget

The budget is the user's. The plugin adds up exactly and tells you where the
room stands; it never blocks an add. Staying inside the budget is your job, and
going over is the user's decision.

1. **Get the amount from the user.** If they gave none ("furnish my room"),
   ask. Never assume an amount. Confirm the currency if it is unclear. Ask
   **once**: "Do you want to keep some of that back as a buffer?" An amount or
   a percentage → pass `reserve` or `reserve_percent`. "No", or no answer → no
   buffer. Then `roomsmith_apply` `{"op": "set_budget", "limit": 1500, "currency": "USD"}`.
2. `roomsmith_inspect`. Decide which pieces the room needs, largest first, and
   roughly what share of the money each can take. Tell the user the list in one
   short message, then start.
3. For each piece, find real products with your own web search tool. Collect
   3 to 6 **product-page** URLs (not category or search pages). **Use only URLs
   your search returned or the user gave. Never construct or guess a URL.**
   Shops whose pages read well (size and price): songmics.com (VASAGLE),
   nathanjames.com, brightech.com, simpli-home.com, walkeredison.com,
   branchfurniture.com, castlery.com, polyandbark.com. Big marketplaces
   (Amazon, IKEA, Wayfair, Article) refuse automated reads.
4. `roomsmith_shortlist {category, candidates: [{url}, …], place?}`. The plugin
   reads each page, tests the size in the room, checks the door and the budget,
   and ranks. Read the `why` of each row. Rows with `verified: false` are not
   page data; never present them as checked.
5. Add the one you chose with `roomsmith_add_product {url, category, place}`
   (use the row's `place`). If the reply has a `budget_note` (the room is now
   over, or into the user's buffer, or the price is unknown), **say so in that
   same reply and ask** what they want: keep it, swap it for a cheaper row, or
   raise the budget. Do not quietly continue.
6. When the pieces are in: `roomsmith_inspect`, then report a table (piece,
   size, price, link), the total, what is left, the buffer if there is one, and
   anything without a price. Say that prices are as read today and can change.
   The plugin does not buy anything.
7. Limits: at most 6 candidates per shortlist; keep to about 8 shortlists per
   request. A shop that answers `blocked` is left alone for the rest of the
   session. `rate_limited` means wait, or ask the user for the printed size and
   price.
8. No web search tool? Say so and ask the user to paste a few links per piece.
   Everything else works the same.
9. "Does it look good?" The stand-in has the product's true size, its colour
   and its photo, in the user's room. Say that. It is not a photoreal render.
10. The user tells you a price the page did not show →
    `{"op": "update_object", "id": "ob4", "product": {"price": "$120"}}`.

## When the user edits in the editor

A note at the start of your turn lists what they changed. Acknowledge it in
a few words and inspect before your next edit. Do not undo their changes
unless asked.

The note also says what they have **selected** ("the user has 'Armchair' (ob4)
selected"). When they then say "this", "it" or "that one", they mean it:
"would this fit by the window?" → `roomsmith_check` `fits_at` with
`object_id: "ob4"`. `roomsmith_inspect` returns `selected` too. If nothing is
selected and "this" is unclear, ask which piece.

## Finishing

- `roomsmith_export` with `glb` for a 3D file, `summary` for a shopping
  list with prices, a total and links, `json` to save the project.
- Keep replies short: what you did, the issues if any, one next step.
