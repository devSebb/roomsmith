// Desktop checklist, automated. Run against a Hermes Desktop that has Roomsmith
// enabled (isolated home recommended; see docs/compat.md):
//
//   node web/dev/desktop-attach.mjs 9333 web/dev/desktop-smoke.mjs
//
// Checks: sidebar entry → pane renders a WebGL canvas → status chip → full page at
// #/roomsmith (after a cold start) → 'New room' from measurements through ctx.rest →
// the editor follows an agent-created room (done out-of-process by the caller when
// SMOKE_AGENT_CMD is set) → undo. Prints PASS/FAIL per step and exits non-zero on a FAIL.
import { execSync } from 'node:child_process'

const results = []
const step = async (name, fn) => {
  try { const v = await fn(); results.push([name, true, v]); console.log(`PASS  ${name}${v ? ' — ' + v : ''}`) }
  catch (e) { results.push([name, false, String(e.message || e)]); console.log(`FAIL  ${name} — ${e.message || e}`) }
}
const norm = s => (s || '').trim().replace(/\s+/g, ' ')
const findClick = (page, text) => page.eval(`(() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 }
  const els = [...document.querySelectorAll('button,a,[role=button],[role=tab],[role=menuitem],[role=switch],option,div[tabindex],span')].filter(vis)
  const norm = s => (s || '').trim().replace(/\\s+/g, ' ')
  const t = ${JSON.stringify(text)}
  const el = els.find(e => norm(e.getAttribute('aria-label')) === t || norm(e.textContent) === t) || els.find(e => norm(e.textContent).includes(t) && norm(e.textContent).length < t.length + 40)
  if (!el) return null
  const r = el.getBoundingClientRect(); return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }
})()`)
const click = async (page, text) => { const hit = await findClick(page, text); if (!hit) throw new Error(`not found: ${text}`); await page.click(hit.x, hit.y); await page.sleep(500) }
const bodyText = page => page.eval('document.body.innerText')
const roots = page => page.eval(`[...document.querySelectorAll('.rs-root')].filter(e => e.getBoundingClientRect().width > 0).length`)

export default async function (page) {
  await page.eval(`location.hash = '#/'`); await page.sleep(800)

  await step('sidebar has a Roomsmith entry', async () => { if (!(await findClick(page, 'Roomsmith'))) throw new Error('no sidebar entry (plugin enabled in Settings → Plugins?)') })
  await step('pane opens and renders WebGL', async () => {
    if ((await roots(page)) === 0) await click(page, 'Roomsmith').catch(() => {})
    await page.sleep(1500)
    const n = await page.eval(`[...document.querySelectorAll('.rs-root canvas')].filter(c => c.getBoundingClientRect().width > 100).length`)
    if (n < 1) throw new Error('no visible editor canvas')
    const gl = await page.eval(`(() => { const c = document.querySelector('.rs-root canvas'); try { return !!(c.getContext('webgl2') || c.getContext('webgl')) } catch { return false } })()`)
    return `canvases: ${n}, webgl: ${gl}`
  })
  await step('backend reachable through ctx.rest (projects listed or empty state)', async () => {
    const t = norm(await bodyText(page))
    if (/offline|could not reach|unavailable to the editor/i.test(t)) throw new Error('editor reports offline')
    return /New room/.test(t) ? 'ok' : 'ok (no New room control visible)'
  })
  await step('status chip shows the active room', async () => {
    const t = norm(await bodyText(page))
    const m = t.match(/🛋 .{1,60}?(?= v\d|$)/)
    if (!m) throw new Error('no 🛋 chip in the status bar; text tail: ' + t.slice(-120))
    return m[0].trim()
  })
  await step('full page mounts at #/roomsmith (cold start required)', async () => {
    const before = await roots(page)
    await page.eval(`location.hash = '#/roomsmith'`); await page.sleep(1500)
    const after = await roots(page)
    await page.eval(`location.hash = '#/'`); await page.sleep(500)
    if (after <= before) throw new Error(`roots before ${before}, after ${after} — restart Desktop after enabling`)
    return `editor instances: ${before} → ${after}`
  })
  await step('create a room from measurements', async () => {
    const t0 = norm(await bodyText(page))
    // the room selector is a <select>: choose "+ New room…" programmatically (React listens for 'change')
    const opened = await page.eval(`(() => { const sel = document.querySelector('.rs-root select.rs-sel'); if (!sel) return false
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; setter.call(sel, '__new'); sel.dispatchEvent(new Event('change', { bubbles: true })); return true })()`)
    if (!opened) throw new Error('no room selector')
    await page.sleep(500)
    const create = await findClick(page, 'Create from measurements')
    if (!create) throw new Error('New room form did not open')
    await page.click(create.x, create.y); await page.sleep(1500)
    const t1 = norm(await bodyText(page))
    if (!/· r1\b/.test(t1)) throw new Error('room selector did not switch to a fresh room (r1)')
    return 'new room is active at r1' + (t0 === t1 ? ' (text unchanged?)' : '')
  })
  if (process.env.SMOKE_AGENT_CMD) {
    await step('editor follows an agent-created room (SMOKE_AGENT_CMD)', async () => {
      const before = norm(await bodyText(page)).match(/🛋 .{1,60}?(?= v\d|$)/)?.[0]
      execSync(process.env.SMOKE_AGENT_CMD, { stdio: 'inherit' })
      await page.sleep(2500)
      const toasts = await page.eval(`[...document.querySelectorAll('.rs-toast')].map(t => t.textContent)`)
      const after = norm(await bodyText(page)).match(/🛋 .{1,60}?(?= v\d|$)/)?.[0]
      if (!toasts.some(t => /Hermes/.test(t))) throw new Error('no Hermes toast; toasts: ' + JSON.stringify(toasts))
      return `${before} → ${after}; toast: ${toasts.find(t => /Hermes/.test(t))}`
    })
  }
  await step('undo button present and enabled or disabled coherently', async () => {
    const st = await page.eval(`(() => { const b = [...document.querySelectorAll('button')].find(b => /Undo/.test(b.textContent)); return b ? { found: true, disabled: b.disabled } : { found: false } })()`)
    if (!st.found) throw new Error('no Undo button')
    return `disabled=${st.disabled}`
  })

  const failed = results.filter(r => !r[1])
  console.log(`\n${results.length - failed.length}/${results.length} passed`)
  const logs = page.logs().filter(l => /roomsmith|exception/i.test(l) && !/favicon/i.test(l))
  if (logs.length) console.log('console (roomsmith/exception):\n' + logs.slice(-20).join('\n'))
  if (failed.length) process.exitCode = 1
}
