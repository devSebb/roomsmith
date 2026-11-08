// Dev harness: the editor against a local FastAPI server (web/dev/server.py),
// with real React bundled. Not shipped.
import React from 'react'
import { createRoot } from 'react-dom/client'
import { Api, fetchTransport } from './api'
import { App } from './ui/App'

const base = (window as any).__RS_API_BASE__ || '/api/plugins/roomsmith'
const api = new Api(fetchTransport(base))
const persist = { get: (k: string) => localStorage.getItem('rs-dev.' + k), set: (k: string, v: string) => localStorage.setItem('rs-dev.' + k, v) }
createRoot(document.getElementById('root')!).render(React.createElement(App, { api, shell: 'dev', persist }))
