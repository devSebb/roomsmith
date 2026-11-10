# Demo script — Roomsmith in 90 seconds

**Setup:** Hermes Desktop on the MacBook (isolated launch, see `docs/compat.md`),
connected to the Mini test backend through an SSH tunnel and the Desktop's
**Remote gateway** setting — not the Desktop's SSH card, which writes into the
Mini's live `~/.hermes` (Harvey's finding, 9 Nov):

1. Mini (Harvey): `hermes serve` from the test home on `127.0.0.1:19119`.
2. MacBook: `ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:19119:127.0.0.1:19119 jessica@<mini>` in its own terminal (stays open, prints nothing).
3. Desktop → Settings → Gateways → Primary gateway → **Remote gateway** `http://127.0.0.1:19119` + the session token Sebb copies himself from the Mini (`cat …/desktop-session-token | pbcopy`). Status should read *Connected to 127.0.0.1:19119 · Hermes 0.23.0*.

Roomsmith pane open on the right, chat on the left. Window ~1600 × 1000 so the pane is wide enough for the 3D view and the
object list side by side. Dark theme. Hide the left sidebar (⌘-click the sidebar
toggle) so chat + pane fill the frame.

**Record** with QuickTime (⌘⇧5 → record selected portion → the Hermes window).
Record the whole run without stopping (3–5 minutes), then trim and speed up the
waits 3–4× in iMovie/QuickTime. Final cut ≤ 90 s. No voice-over needed; the chat
text is the narration. Add two title cards (start/end) in the editor.

Before recording: `/room` must answer "no room yet" — delete demo leftovers from the
test home first (Harvey, or the editor's Room → Delete). Keep the product links in a
text file to paste. Type ONE line per message — never paste the table or any
"(mouse)" instruction into the chat, or Hermes will try to do the mouse part
itself with the computer-use skill.

| # | You type (chat) | What the viewer sees | ≈ s in final cut |
|---|---|---|---|
| 1 | **Build my bedroom from the photos in `~/room-studio-test/fixtures/bedroom`** *(or drag the three photos into the chat if Desktop attachments reach the model — test in the dry run)* | Hermes calls `roomsmith_from_photo`; the pane switches to **Bedroom** with the toast *"Hermes opened Bedroom"*; window on the back wall, bed on the right, fan hanging, **Draft** badge | 0–15 |
| 2 | **The room is 2.82 by 4 metres.** | Room stretches to size; furniture keeps its size and stays on the walls; Draft badge disappears; Hermes: "calibrated… furniture sizes kept" | 15–25 |
| 3 | **Move the bed to the window wall, centred, and put a 1.2 m desk where the bed was.** | Bed glides to the back wall, a desk appears on the right wall, both highlighted for a second; Hermes reports any issue the move caused | 25–40 |
| 4 | *(mouse)* Drag the bedside table across the room into the doorway. Then type: **Does anything block the door now?** | The drag snaps and shows "Against wall"; Hermes answers from geometry: "the bedside table is in the door's 0.8 m clear zone" — it saw your manual edit | 40–52 |
| 5 | **Would this sofa fit against the wall opposite the bed? https://www.castlery.com/us/products/hamilton-sofa** — Hermes reads the page itself and answers from geometry: *2.25 m wide, fits physically, but blocks the door* (true: a 2.25 m sofa cannot sit beside a door on a 2.82 m wall). Then: **What about this armchair? https://www.castlery.com/us/products/owen-armchair** → *1.10 × 1.00 m, fits*. Then: **Put it there.** | `roomsmith_read_product` twice (no web tool needed), `roomsmith_check`, then a stand-in in the chair's own colour with the product photo as a tag lands beside the door ("slid … to clear the door"). The honest "no" and the "yes" back to back is the point. Verified links, 10 Nov: Castlery (Hamilton sofa, Owen/Madison armchair, Casa dining table), Sixpenny (Neva sofa 84, Neva chair — rate-limited the Mini once, keep as spare only), Albany Park (Kova sofa), Thuma (Classic Bed — say "queen"), Branch (Tria desk, Ergonomic chair). Avoid Floyd, Article, IKEA/Wayfair/Amazon. | 52–70 |
| 6 | Click **Labels on** (tags vanish). Press **⌘Z** twice in the pane. Click **Plan**. Click the **Room** tab → **Export → GLB**, then open the file in Finder (Quick Look). | Clean room; chair and the table move vanish in order; plan view with measurements; the GLB opens looking like the editor (shapes, floor, tag) | 70–82 |
| 7 | *(title card)* **Roomsmith — a Hermes Agent plugin. Photo → editable 3D room. No extra accounts.** `hermes plugins install devSebb/roomsmith` | | 82–90 |

## Fallbacks during the dry run

- Photo build gives a poor room → use the **futon room** (one photo, `fixtures/photos/room-01…`) instead, or lead with *"Make a 2.82 by 4 metre bedroom with a window on the back wall and a door on the front wall"* (typed-size route; everything after step 1 is identical).
- A product page fails to read on the day (site changed, rate limit) → paste the size: *"It's 88.6 by 39.4 by 32.3 inches"*; Hermes adds it with `roomsmith_add_product` and the beat continues.
- A turn goes wrong → say *"undo that"* on camera; the plugin's undo is part of the pitch.

## Dry-run checklist (with Sebb watching)

- [ ] Desktop connected to the test home; status chip shows a room after step 1
- [ ] Each prompt above once, note timings
- [ ] Castlery link reads on the Mini (it did on 9 Nov: 2.25 × 0.82 × 1.00 m); Sixpenny as the spare
- [ ] Record for real
