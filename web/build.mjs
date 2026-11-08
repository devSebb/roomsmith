// Builds the three bundles from one source tree:
//   desktop/plugin.js        ESM, externals: @hermes/plugin-sdk, react, react/jsx-runtime
//   dashboard/dist/index.js  IIFE, React via window.__HERMES_PLUGIN_SDK__ (shims)
//   web/dev/dev.js           IIFE with real React, for the local harness (not shipped)
// Then runs the same checks the Hermes catalog validator runs on Desktop files.
import * as esbuild from 'esbuild'
import { readFileSync, statSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const watch = process.argv.includes('--watch')
const devOnly = process.argv.includes('--dev')
const version = JSON.parse(readFileSync(resolve(here, 'package.json'), 'utf8')).version

const banner = (what) => `/* Roomsmith ${version} — ${what}. Built from web/ with esbuild; do not edit by hand. Bundles three.js (MIT, see THIRD_PARTY_NOTICES.md). */`

const common = {
  bundle: true,
  minify: true,
  sourcemap: false,
  target: ['es2022', 'chrome120', 'safari17'],
  legalComments: 'none',
  logLevel: 'info',
  define: { 'process.env.NODE_ENV': '"production"' },
  jsx: 'automatic',
  treeShaking: true,
}

const builds = [
  {
    name: 'desktop',
    entryPoints: [resolve(here, 'src/desktop.tsx')],
    outfile: resolve(root, 'desktop/plugin.js'),
    format: 'esm',
    external: ['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'],
    banner: { js: banner('Hermes Desktop plugin') },
  },
  {
    name: 'dashboard',
    entryPoints: [resolve(here, 'src/dashboard.tsx')],
    outfile: resolve(root, 'dashboard/dist/index.js'),
    format: 'iife',
    alias: { react: resolve(here, 'src/shims/react-dashboard.ts'), 'react/jsx-runtime': resolve(here, 'src/shims/jsx-runtime-dashboard.ts') },
    banner: { js: banner('Hermes dashboard tab') },
  },
  {
    name: 'dev',
    entryPoints: [resolve(here, 'src/dev.tsx')],
    outfile: resolve(here, 'dev/dev.js'),
    format: 'iife',
    minify: false,
    sourcemap: 'inline',
  },
]

// --- the catalog's desktop lint (mirrors hermes_cli/plugin_validate_desktop.py) ---
const FORBIDDEN = [
  ['dynamic code evaluation', /(?<![\w$.])eval\(|\bnew\s+Function\(/],
  ['dynamic import outside the SDK', /\bimport\(\s*(?!['"](?:@hermes\/plugin-sdk|react)(?:\/[\w\/-]*)?['"]\s*\))/],
  ['remote import outside the SDK', /\bimport\s+(?:[^;'"]*?\bfrom\s*)?['"][a-zA-Z][\w+.-]*:/],
  ['script injection', /createElement\(\s*['"]script['"]\s*\)|<script\b/],
  ['app DOM reach', /\bdocument\.(?:querySelector(?:All)?|getElementsBy\w+|getElementById)\(\s*[`'"][^`'"]*\[data-(?:slot|tour|sidebar|testid)\b/],
  ['app DOM reach', /\.observe\(\s*document\.body\s*,\s*\{[^}]*\b(?:childList|subtree)\b/],
  ['preview guest reach', /\b(?:querySelector(?:All)?|closest|getElementsByTagName|createElement)\(\s*[`'"]webview\b/],
]
const REVIEW = [
  ['raw bridge window.hermesDesktop', /\b(?:window|globalThis|self)\s*(?:\?\.|\.)\s*hermesDesktop\b/],
  ['app markup selector', /\[data-(?:slot|tour|sidebar|testid|tree-[\w-]+|pane-host|titlebar-cluster)\b/],
]
function stripComments(src) {
  return src.replace(/("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`)|\/\*[\s\S]*?\*\/|(?<![:\w])\/\/[^\n]*/g, (m, str) => str ?? '\n'.repeat((m.match(/\n/g) || []).length))
}
function lintDesktop(file) {
  const src = stripComments(readFileSync(file, 'utf8'))
  const bad = []
  for (const [rule, re] of FORBIDDEN) {
    const m = re.exec(src)
    if (m) bad.push(`${rule} at offset ${m.index}: …${src.slice(Math.max(0, m.index - 40), m.index + 60).replace(/\n/g, ' ')}…`)
  }
  const cues = REVIEW.filter(([, re]) => re.test(src)).map(([c]) => c)
  return { bad, cues }
}

function sizeCheck(file, limit = 1024 * 1024) {
  const bytes = statSync(file).size
  return { bytes, ok: bytes <= limit }
}

async function run() {
  mkdirSync(resolve(root, 'dashboard/dist'), { recursive: true })
  const selected = devOnly ? builds.filter(b => b.name === 'dev') : builds
  if (watch) {
    const ctxs = await Promise.all(selected.map(b => esbuild.context({ ...common, ...b, minify: b.minify ?? common.minify })))
    await Promise.all(ctxs.map(c => c.watch()))
    console.log('watching…')
    return
  }
  for (const b of selected) {
    const { name, ...opts } = b
    await esbuild.build({ ...common, ...opts, minify: opts.minify ?? common.minify })
  }
  let failed = false
  for (const b of selected) {
    if (b.name === 'dev') continue
    const { bytes, ok } = sizeCheck(b.outfile)
    console.log(`${b.name}: ${(bytes / 1024).toFixed(0)} KB ${ok ? '(under the 1 MB catalog limit)' : '!! OVER the 1 MB catalog limit'}`)
    if (!ok) failed = true
  }
  const lint = lintDesktop(resolve(root, 'desktop/plugin.js'))
  if (lint.bad.length) { failed = true; console.error('desktop lint FAILED:\n  ' + lint.bad.join('\n  ')) }
  else console.log('desktop lint: clean' + (lint.cues.length ? ` (review cues: ${lint.cues.join(', ')})` : ''))
  if (failed) process.exit(1)
}

run().catch(e => { console.error(e); process.exit(1) })
