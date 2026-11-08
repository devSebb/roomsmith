// Attach to a running Hermes Desktop (or any Chromium) over CDP and run a script.
// Desktop needs `desktop.electron_flags: ["--remote-debugging-port=9333"]` in the
// (isolated) Hermes home config.yaml. See docs/compat.md for the isolated launch recipe.
// Usage: node web/dev/desktop-attach.mjs <port> <script.mjs>   (same page API as cdp.mjs)
import { writeFileSync } from 'node:fs'

const [portArg, scriptPath] = process.argv.slice(2)
const port = Number(portArg || 9333)
const sleep = ms => new Promise(r => setTimeout(r, ms))

const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()
const target = list.find(t => t.type === 'page' && !t.url.startsWith('devtools://'))
if (!target) throw new Error('no page target: ' + JSON.stringify(list.map(t => [t.type, t.url])))
const ws = new WebSocket(target.webSocketDebuggerUrl)
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
const page = {
  logs: () => logs,
  async eval(expr) { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value },
  async shot(file) { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(file, Buffer.from(r.data, 'base64')); return file },
  async mouse(type, x, y, extra = {}) { await send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1, ...extra }) },
  async click(x, y, mods = 0) { await page.mouse('mouseMoved', x, y); await page.mouse('mousePressed', x, y, { modifiers: mods }); await page.mouse('mouseReleased', x, y, { modifiers: mods }); await sleep(150) },
  async drag(x0, y0, x1, y1, steps = 12) { await page.mouse('mouseMoved', x0, y0); await page.mouse('mousePressed', x0, y0); for (let i = 1; i <= steps; i++) { await page.mouse('mouseMoved', x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, { buttons: 1 }); await sleep(16) } await page.mouse('mouseReleased', x1, y1); await sleep(150) },
  async key(key, mods = 0) { const code = key.length === 1 ? 'Key' + key.toUpperCase() : key; await send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, modifiers: mods, windowsVirtualKeyCode: key.length === 1 ? key.toUpperCase().charCodeAt(0) : undefined }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, modifiers: mods }); await sleep(80) },
  async type(text) { for (const ch of text) await send('Input.insertText', { text: ch }); await sleep(50) },
  sleep,
}
try {
  const mod = await import(new URL(scriptPath, `file://${process.cwd()}/`).href)
  await mod.default(page)
} finally { ws.close() }
