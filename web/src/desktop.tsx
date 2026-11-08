// Hermes Desktop shell: a pane beside the chat, a full page, a sidebar entry,
// a palette command and a status-bar chip. Built into desktop/plugin.js as one
// ESM file; only '@hermes/plugin-sdk', 'react' and 'react/jsx-runtime' are imported.
import { host, atom, useValue, PANES_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, PALETTE_AREA } from '@hermes/plugin-sdk'
import React from 'react'
import { Api, type Transport } from './api'
import { App } from './ui/App'
import type { State } from './store'

const ID = 'roomsmith'
const $status = atom<{ name: string; revision: number; issues: number; has: boolean }>({ name: '', revision: 0, issues: 0, has: false })

function parseThrown(e: any): any | null {
  const body = e?.body ?? e?.data ?? e?.response?.data
  if (body && typeof body === 'object' && 'ok' in body) return body
  const msg = String(e?.message || e)
  const m = msg.match(/\{[\s\S]*\}\s*$/)
  if (m) { try { const j = JSON.parse(m[0]); if (j && typeof j === 'object' && 'ok' in j) return j } catch { /* no */ } }
  return null
}

function transport(ctx: any): Transport {
  return {
    async json(path, init) {
      try {
        return await ctx.rest(path, { method: init?.method || 'GET', body: init?.body, timeoutMs: init?.timeoutMs })
      } catch (e: any) {
        const parsed = parseThrown(e)
        if (parsed) return parsed
        throw e
      }
    },
    async upload(path, bytes, contentType) {
      try {
        return await ctx.rest(path, { method: 'POST', upload: { filename: 'photo', contentType, bytes } })
      } catch (e: any) {
        const parsed = parseThrown(e)
        if (parsed) return parsed
        throw e
      }
    },
    url(path) { return `/api/plugins/${ID}${path}` },
    async download(path, filename) {
      const r: any = await ctx.rest(path + '&encoding=base64')
      if (!r?.ok) throw new Error(r?.error?.message || 'Export failed')
      const bin = atob(r.base64)
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      const blob = new Blob([bytes], { type: r.mime || 'application/octet-stream' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = r.filename || filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      host.notify({ kind: 'info', message: `Exported ${r.filename || filename}` })
    },
  }
}

function makePersist(ctx: any) {
  return {
    get: (k: string) => { try { const v = ctx.storage.get(k, null); return v == null ? null : String(v) } catch { return null } },
    set: (k: string, v: string) => { try { ctx.storage.set(k, v) } catch { /* ignore */ } },
  }
}

function onState(s: State) {
  $status.set({ name: s.scene?.project.name || '', revision: s.revision, issues: s.issues.filter(i => i.code !== 'uncalibrated').length, has: !!s.scene })
}

function Roomsmith({ ctx, full }: { ctx: any; full?: boolean }) {
  const api = React.useMemo(() => new Api(transport(ctx)), [ctx])
  const persist = React.useMemo(() => makePersist(ctx), [ctx])
  return React.createElement('div', { style: { height: '100%', minHeight: full ? '100%' : 360, display: 'flex', flexDirection: 'column' } },
    React.createElement(App, { api, shell: 'desktop', persist, onStateChange: onState, openExternal: (u: string) => { void ctx.os.openExternal(u) } }))
}

function StatusChip() {
  const s = useValue($status)
  if (!s.has) return null
  return React.createElement('button', {
    type: 'button',
    className: 'px-1.5 text-[0.6875rem] text-(--ui-text-tertiary)',
    title: `Roomsmith: ${s.name}, revision ${s.revision}`,
    onClick: () => host.navigate('/roomsmith'),
  }, `🛋 ${s.name}${s.issues ? ` · ${s.issues} issue${s.issues === 1 ? '' : 's'}` : ''}`)
}

export default {
  id: ID,
  name: 'Roomsmith',
  register(ctx: any) {
    ctx.registerMany([
      {
        id: 'pane',
        area: PANES_AREA,
        title: 'Roomsmith',
        data: { placement: 'right', width: '560px' },
        render: () => React.createElement(Roomsmith, { ctx }),
      },
      {
        id: 'page',
        area: ROUTES_AREA,
        title: 'Roomsmith',
        data: { path: '/roomsmith' },
        render: () => React.createElement(Roomsmith, { ctx, full: true }),
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/roomsmith', label: 'Roomsmith', codicon: 'home' },
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: { id: 'roomsmith.open', label: 'Open Roomsmith', keywords: ['room', 'furniture', '3d', 'studio'], run: () => host.navigate('/roomsmith') },
      },
      {
        id: 'chip',
        area: STATUSBAR_AREAS.right,
        order: 140,
        render: () => React.createElement(StatusChip, {}),
      },
    ])
  },
}
