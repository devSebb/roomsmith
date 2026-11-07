// Dashboard shell: registers the Room Studio tab with the dashboard's plugin SDK.
// Built as an IIFE; React comes from window.__HERMES_PLUGIN_SDK__ via shims.
import React from 'react'
import { Api, type Transport } from './api'
import { App } from './ui/App'

const SDK = (window as any).__HERMES_PLUGIN_SDK__
const NS = '/api/plugins/room-studio'
const TOKEN_HEADER = 'X-Hermes-Session-Token'

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = (window as any).__HERMES_SESSION_TOKEN__
  return token ? { ...extra, [TOKEN_HEADER]: token } : extra
}

function parseThrown(e: any): any | null {
  // SDK.fetchJSON throws Error("<status>: <body>") on non-2xx; our bodies are JSON envelopes
  const msg = String(e?.message || e)
  const m = msg.match(/\{[\s\S]*\}\s*$/)
  if (m) { try { const j = JSON.parse(m[0]); if (j && typeof j === 'object' && 'ok' in j) return j } catch { /* no */ } }
  return null
}

function transport(): Transport {
  return {
    async json(path, init) {
      try {
        return await SDK.fetchJSON(NS + path, {
          method: init?.method || 'GET',
          headers: init?.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
          body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
        })
      } catch (e: any) {
        const parsed = parseThrown(e)
        if (parsed) return parsed
        throw e
      }
    },
    async upload(path, bytes, contentType) {
      const res = await fetch(NS + path, { method: 'POST', headers: authHeaders({ 'Content-Type': contentType }), body: bytes, credentials: 'include' })
      return res.json()
    },
    url(path) { return NS + path },
    async download(path, filename) {
      const res = await fetch(NS + path, { headers: authHeaders(), credentials: 'include' })
      if (!res.ok) throw new Error(`Export failed: HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
    },
  }
}

const persist = {
  get: (k: string) => { try { return localStorage.getItem('room-studio.' + k) } catch { return null } },
  set: (k: string, v: string) => { try { localStorage.setItem('room-studio.' + k, v) } catch { /* ignore */ } },
}

function RoomStudioTab() {
  const api = React.useMemo(() => new Api(transport()), [])
  return React.createElement('div', { style: { height: 'calc(100vh - 110px)', minHeight: 480 } }, React.createElement(App, { api, shell: 'dashboard', persist }))
}

;(window as any).__HERMES_PLUGINS__.register('room-studio', RoomStudioTab)
