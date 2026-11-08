// Opens the real Hermes dashboard, finds the Roomsmith tab, exercises it.
import { mkdirSync } from 'node:fs'
const OUT = '.scratch/shots'
const assert = (c, m) => { if (!c) throw new Error('ASSERT: ' + m) }

export default async function (page) {
  mkdirSync(OUT, { recursive: true })
  await page.sleep(2500)
  await page.shot(`${OUT}/d1-dashboard.png`)
  const nav = await page.eval(`[...document.querySelectorAll('a, button')].map(a => (a.textContent || '').trim()).filter(t => t && t.length < 30)`)
  console.log('nav:', JSON.stringify(nav.slice(0, 40)))
  const href = await page.eval(`([...document.querySelectorAll('a')].find(a => /roomsmith/i.test(a.textContent)) || {}).getAttribute?.('href')`)
  console.log('tab href:', href)
  assert(href, 'Roomsmith tab present in the nav')
  await page.eval(`[...document.querySelectorAll('a')].find(a => /roomsmith/i.test(a.textContent)).click()`)
  for (let i = 0; i < 40; i++) { if (await page.eval(`!!document.querySelector('.rs-root')`)) break; await page.sleep(250) }
  await page.sleep(1500)
  await page.shot(`${OUT}/d2-roomsmith-tab.png`)
  const mounted = await page.eval(`!!document.querySelector('.rs-root canvas')`)
  assert(mounted, 'editor mounted inside the dashboard')
  const empty = await page.eval(`!!document.querySelector('.rs-empty')`)
  console.log('empty state shown:', empty)
  if (empty) {
    // create a room through the UI
    await page.eval(`[...document.querySelectorAll('.rs-empty button')].find(b => /Create from measurements/.test(b.textContent)).click()`)
    for (let i = 0; i < 40; i++) { if (await page.eval(`!document.querySelector('.rs-empty')`)) break; await page.sleep(250) }
    await page.sleep(800)
  }
  await page.shot(`${OUT}/d3-room-created.png`)
  const rev = await page.eval(`document.querySelector('.rs-toolbar .rs-faint')?.textContent`)
  console.log('revision badge:', rev)
  assert(/r\d+/.test(rev || ''), 'room loaded')
  // add a sofa from the Add tab
  await page.eval(`[...document.querySelectorAll('.rs-tabs button')].find(b => b.textContent.startsWith('Add')).click()`)
  await page.sleep(300)
  await page.eval(`[...document.querySelectorAll('.rs-body button')].find(b => /^Add sofa/.test(b.textContent)).click()`)
  await page.sleep(1200)
  const objs = await page.eval(`document.querySelectorAll('.rs-tabs .rs-count')[0]?.textContent`)
  console.log('objects count badge:', objs)
  await page.shot(`${OUT}/d4-added-sofa.png`)
  const errors = page.logs().filter(l => /exception|error/i.test(l) && !/favicon|status of (404|409|400|401)/i.test(l))
  for (const e of errors.slice(0, 10)) console.log('  ', e.slice(0, 300))
  assert(errors.length === 0, 'no console errors')
  console.log('DASHBOARD SMOKE OK')
}
