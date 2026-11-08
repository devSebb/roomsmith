// Smoke scenario for the dev harness: load, render, select, drag, rotate, undo,
// plan view, agent edit shows up, conflict recovery. Screenshots in .scratch/shots/.
import { mkdirSync } from 'node:fs'

const OUT = '.scratch/shots'
const API = 'http://127.0.0.1:8765/api/plugins/roomsmith'
const assert = (c, m) => { if (!c) throw new Error('ASSERT: ' + m) }
const head = async pid => (await (await fetch(`${API}/projects/${pid}/head`)).json())

export default async function (page) {
  mkdirSync(OUT, { recursive: true })
  for (let i = 0; i < 40; i++) { if (await page.eval(`!!window.__rs?.store.state.scene`)) break; await page.sleep(250) }
  await page.sleep(400)
  await page.shot(`${OUT}/01-load.png`)
  const state = async () => page.eval(`(() => ({ hasCanvas: !!document.querySelector('.rs-canvas canvas'), objects: window.__rs?.store.state.scene?.objects.length ?? document.querySelectorAll('.rs-item').length, rev: document.querySelector('.rs-toolbar .rs-faint')?.textContent, toasts: [...document.querySelectorAll('.rs-toast')].map(t => t.textContent), selected: window.__rs?.store.state.selectedId }))()`)
  let s = await state()
  console.log('after load', JSON.stringify(s))
  assert(s.hasCanvas, 'canvas mounted')
  assert(s.objects >= 6, 'object list shows the fixture objects')
  const pid = (await (await fetch(`${API}/projects`)).json()).projects[0].project_id
  const pos = async id => page.eval(`window.__rs.editor.screenPosition(${JSON.stringify(id)})`)

  // click the coffee table in 3D to select it, then drag it toward the camera
  let p = await pos('ob2')
  await page.click(p.x, p.y)
  await page.sleep(200)
  s = await state()
  assert(s.selected === 'ob2', 'click selects the coffee table, got ' + s.selected)
  const rev0 = (await head(pid)).revision
  await page.drag(p.x, p.y, p.x + 40, p.y + 90)
  await page.sleep(900)
  const h1 = await head(pid)
  console.log('drag:', rev0, '->', h1.revision, h1.summary)
  assert(h1.revision === rev0 + 1 && h1.actor === 'user', 'drag made a user revision')
  await page.shot(`${OUT}/02-after-drag.png`)

  // rotate with R (canvas has focus after the click)
  await page.key('r')
  await page.sleep(800)
  const h2 = await head(pid)
  assert(h2.revision === rev0 + 2 && /Rotated/.test(h2.summary), 'R rotated: ' + h2.summary)

  // undo via keyboard
  await page.key('z', 4) // meta
  await page.sleep(800)
  const h3 = await head(pid)
  assert(h3.revision === rev0 + 3 && /^Undo/.test(h3.summary), 'cmd+Z undid: ' + h3.summary)

  // plan view
  await page.key('v')
  await page.sleep(500)
  await page.shot(`${OUT}/03-plan.png`)
  const mode = await page.eval(`window.__rs.editor.mode`)
  assert(mode === 'plan', 'V switched to plan view')
  // drag in plan view snaps to a wall: drag the plant toward the right wall
  p = await pos('ob6')
  await page.drag(p.x, p.y, p.x + 60, p.y + 10)
  await page.sleep(900)
  const h4 = await head(pid)
  console.log('plan drag:', h4.summary)
  const plant = (await (await fetch(`${API}/projects/${pid}/scene`)).json()).scene.objects.find(o => o.id === 'ob6')
  assert(plant.position_m[0] <= 4.2 - 0.25 + 1e-6, 'plant kept inside the room: x=' + plant.position_m[0])
  await page.key('v')

  // an "agent" edit through the API must appear in the editor (long-poll) with a toast
  const r = await fetch(`${API}/projects/${pid}/commands`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor: 'agent', operations: [{ op: 'add_object', name: 'Reading chair', category: 'armchair', place: { in_corner: ['w1', 'w4'] } }] }) })
  const nBefore = (await state()).objects
  const rj = await r.json()
  assert(rj.ok, 'agent add ok ' + JSON.stringify(rj.error))
  await page.sleep(1800)
  s = await state()
  console.log('after agent edit', JSON.stringify(s))
  assert(s.toasts.some(t => t.includes('Hermes')), 'agent toast shown')
  assert(s.objects === nBefore + 1, 'object count grew by one')
  await page.shot(`${OUT}/04-agent-edit.png`)

  // conflict recovery: the editor holds revision N; the API moves on; a UI edit still lands
  await fetch(`${API}/projects/${pid}/commands`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor: 'agent', operations: [{ op: 'set_room_height', height_m: 2.7 }] }) })
  const before = await head(pid)
  await page.eval(`window.__rs.store.apply([{ op: 'update_object', id: 'ob1', name: 'Blue sofa' }])`)
  await page.sleep(600)
  const after = await head(pid)
  assert(after.revision >= before.revision + 1 && /Blue sofa/.test(after.summary), 'UI edit landed after an external change: ' + after.summary)

  // issues tab and history tab render
  await page.eval(`[...document.querySelectorAll('.rs-tabs button')].find(b => b.textContent.startsWith('Issues')).click()`)
  await page.sleep(300)
  await page.shot(`${OUT}/05-issues.png`)
  await page.eval(`[...document.querySelectorAll('.rs-tabs button')].find(b => b.textContent.startsWith('History')).click()`)
  await page.sleep(300)
  const hist = await page.eval(`document.querySelectorAll('.rs-hist').length`)
  assert(hist >= 5, 'history list populated')
  await page.shot(`${OUT}/06-history.png`)

  const errors = page.logs().filter(l => /exception|error/i.test(l) && !/favicon|status of (404|409|400)/i.test(l))
  console.log('console lines:', page.logs().length, 'errors:', errors.length)
  for (const e of errors.slice(0, 10)) console.log('  ', e.slice(0, 300))
  assert(errors.length === 0, 'no console errors')
  console.log('SMOKE OK')
}
