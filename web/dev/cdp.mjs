// Headless-Chrome smoke harness over the DevTools protocol (no extra deps).
// Usage: node web/dev/cdp.mjs <url> <script.mjs>
// The script default-exports async (page) => {...} with page.eval(js), page.shot(file),
// page.click(x,y), page.drag(x0,y0,x1,y1), page.key(key, mods), page.type(text), page.logs()
import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const [url, scriptPath] = process.argv.slice(2)
if (!url || !scriptPath) { console.error('usage: node cdp.mjs <url> <script.mjs>'); process.exit(2) }

const port = 9333 + Math.floor(Math.random() * 500)
const profile = mkdtempSync(join(tmpdir(), 'rs-chrome-'))
const chrome = spawn(CHROME, [`--headless=new`, `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--window-size=1400,900', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--disable-gpu-vsync', 'about:blank'], { stdio: 'ignore' })

const sleep = ms => new Promise(r => setTimeout(r, ms))
async function waitFor(fn, ms = 10000) { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v } catch {} await sleep(150) } throw new Error('timeout') }

try {
  const targets = await waitFor(async () => { const r = await fetch(`http://127.0.0.1:${port}/json`); const j = await r.json(); return j.find(t => t.type === 'page') })
  const ws = new WebSocket(targets.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
  let id = 0
  const pending = new Map()
  const logs = []
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data)
    if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(m.error.message)) : res(m.result) }
    if (m.method === 'Runtime.consoleAPICalled') logs.push(`[${m.params.type}] ` + m.params.args.map(a => a.value ?? a.description ?? JSON.stringify(a)).join(' '))
    if (m.method === 'Runtime.exceptionThrown') logs.push('[exception] ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text))
    if (m.method === 'Log.entryAdded') logs.push(`[${m.params.entry.level}] ${m.params.entry.text}`)
  }
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })) })
  await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false })
  const page = {
    logs: () => logs,
    async goto(u) { await send('Page.navigate', { url: u }); await sleep(800) },
    async eval(expr) { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value },
    async shot(file) { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(file, Buffer.from(r.data, 'base64')); return file },
    async mouse(type, x, y, extra = {}) { await send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1, ...extra }) },
    async click(x, y, mods = 0) { await page.mouse('mouseMoved', x, y); await page.mouse('mousePressed', x, y, { modifiers: mods }); await page.mouse('mouseReleased', x, y, { modifiers: mods }); await sleep(120) },
    async dblclick(x, y) { await page.mouse('mouseMoved', x, y); await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 2 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 2 }); await sleep(120) },
    async drag(x0, y0, x1, y1, steps = 12) { await page.mouse('mouseMoved', x0, y0); await page.mouse('mousePressed', x0, y0); for (let i = 1; i <= steps; i++) { await page.mouse('mouseMoved', x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, { buttons: 1 }); await sleep(16) } await page.mouse('mouseReleased', x1, y1); await sleep(150) },
    async key(key, mods = 0) { const code = key.length === 1 ? 'Key' + key.toUpperCase() : key; await send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, modifiers: mods, windowsVirtualKeyCode: key.length === 1 ? key.toUpperCase().charCodeAt(0) : undefined }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, modifiers: mods }); await sleep(80) },
    async type(text) { for (const ch of text) await send('Input.insertText', { text: ch }); await sleep(50) },
    sleep,
  }
  await page.goto(url)
  const mod = await import(new URL(scriptPath, `file://${process.cwd()}/`).href)
  await mod.default(page)
  ws.close()
} finally {
  chrome.kill('SIGKILL')
}
