# Demo script — Roomsmith in 90 seconds

**Setup:** Hermes Desktop on the MacBook, connected over SSH to the Mini test home
(Roomsmith installed there, gpt-6-astra). Roomsmith pane open on the right, chat on
the left. Window ~1600 × 1000 so the pane is wide enough for the 3D view and the
object list side by side. Dark theme. Hide the left sidebar (⌘-click the sidebar
toggle) so chat + pane fill the frame.

**Record** with QuickTime (⌘⇧5 → record selected portion → the Hermes window).
Record the whole run without stopping (3–5 minutes), then trim and speed up the
waits 3–4× in iMovie/QuickTime. Final cut ≤ 90 s. No voice-over needed; the chat
text is the narration. Add two title cards (start/end) in the editor.

Before recording: `/room` must answer "no room yet" — delete demo leftovers from the
test home first (Harvey, or the editor's Room → Delete). Keep the Floyd links in a
text file to paste.

| # | You type (chat) | What the viewer sees | ≈ s in final cut |
|---|---|---|---|
| 1 | **Build my bedroom from the photos in `~/room-studio-test/fixtures/bedroom`** *(or drag the three photos into the chat if Desktop attachments reach the model — test in the dry run)* | Hermes calls `roomsmith_from_photo`; the pane switches to **Bedroom** with the toast *"Hermes opened Bedroom"*; window on the back wall, bed on the right, fan hanging, **Draft** badge | 0–15 |
| 2 | **The room is 2.82 by 4 metres.** | Room stretches to size; furniture keeps its size and stays on the walls; Draft badge disappears; Hermes: "calibrated… furniture sizes kept" | 15–25 |
| 3 | **Move the bed to the window wall, centred, and put a 1.2 m desk where the bed was.** | Bed glides to the back wall, a desk appears on the right wall, both highlighted for a second; Hermes reports any issue the move caused | 25–40 |
| 4 | *(mouse)* Drag the bedside table across the room into the doorway. Then type: **Does anything block the door now?** | The drag snaps and shows "Against wall"; Hermes answers from geometry: "the bedside table is in the door's 0.8 m clear zone" — it saw your manual edit | 40–52 |
| 5 | **Would this Floyd sofa fit against the wall opposite the bed? It's 86 by 34 by 32 inches. https://floydhome.com/products/the-sofa-2-0** | A **2.18 × 0.86 m** stand-in labelled with the product and link appears; answer with clearance in centimetres and whether it passes the door. *(The size is in the prompt on purpose: the Mini's Hermes has a search-only web backend and Floyd rate-limits curl, so page retrieval is not demo-safe.)* | 52–70 |
| 6 | Press **⌘Z** twice in the pane (or type **undo the last two changes**). Click **Plan**. Click **Export → GLB**. | Sofa and the table move vanish in order; plan view with measurements; export toast | 70–82 |
| 7 | *(title card)* **Roomsmith — a Hermes Agent plugin. Photo → editable 3D room. No extra accounts.** `hermes plugins install devSebb/roomsmith` | | 82–90 |

## Fallbacks during the dry run

- Photo build gives a poor room → use the **futon room** (one photo, `fixtures/photos/room-01…`) instead, or lead with *"Make a 2.82 by 4 metre bedroom with a window on the back wall and a door on the front wall"* (typed-size route; everything after step 1 is identical).
- If you want to try live page reading anyway, do it in the dry run only; the recorded take uses the size-in-prompt form.
- A turn goes wrong → say *"undo that"* on camera; the plugin's undo is part of the pitch.

## Dry-run checklist (with Sebb watching)

- [ ] Desktop connected to the test home; status chip shows a room after step 1
- [ ] Each prompt above once, note timings
- [ ] Product link read works, or switch to the typed-size fallback
- [ ] Record for real
