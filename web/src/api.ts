// One tiny client; each shell supplies a transport (SDK.fetchJSON, ctx.rest, or fetch).

import type { ApplyResult, BudgetStatus, Head, Issue, Op, ProjectRow, Revision, Scene } from './types'

export interface Transport {
  // path is namespace-relative: "/projects", "/projects/x/head", ...
  json<T = unknown>(path: string, init?: { method?: string; body?: unknown; timeoutMs?: number }): Promise<T>
  upload<T = unknown>(path: string, bytes: Uint8Array, contentType: string): Promise<T>
  // absolute URL for a GET the browser performs itself (download link, <img src>)
  url(path: string): string
  // optional: fetch bytes with auth and hand them to the user (hosts whose GETs need headers)
  download?(path: string, filename: string): Promise<void>
}

export class ApiError extends Error {
  constructor(public code: string, message: string, public payload?: any) { super(message) }
}

function check<T extends { ok?: boolean; error?: any }>(r: T): T {
  if (r && r.ok === false) throw new ApiError(r.error?.code || 'error', r.error?.message || 'Request failed', r)
  return r
}

export class Api {
  constructor(private t: Transport) {}

  health() { return this.t.json<any>('/health') }
  listProjects() { return this.t.json<{ ok: boolean; active_project_id: string | null; projects: ProjectRow[] }>('/projects').then(check) }
  createProject(body: { name?: string; width_m?: number; depth_m?: number; height_m?: number; layout?: unknown; import?: unknown }) {
    return this.t.json<any>('/projects', { method: 'POST', body }).then(check)
  }
  activate(id: string) { return this.t.json<any>(`/projects/${id}/activate`, { method: 'POST', body: {} }).then(check) }
  rename(id: string, name: string) { return this.t.json<any>(`/projects/${id}`, { method: 'PATCH', body: { name } }).then(check) }
  delete(id: string) { return this.t.json<any>(`/projects/${id}`, { method: 'DELETE' }).then(check) }
  head(id: string) { return this.t.json<Head & { ok: boolean }>(`/projects/${id}/head`).then(check) }
  wait(id: string, after: number, timeout = 25, active?: string | null) {
    const q = `after=${after}&timeout=${timeout}` + (active ? `&active=${encodeURIComponent(active)}` : '')
    return this.t.json<Head & { ok: boolean; changed: boolean; active_project_id?: string | null; active_changed?: boolean }>(`/projects/${id}/wait?${q}`, { timeoutMs: (timeout + 10) * 1000 }).then(check)
  }
  scene(id: string) { return this.t.json<{ ok: boolean; revision: number; scene: Scene; issues: Issue[]; budget?: BudgetStatus | null; can_undo: boolean; can_redo: boolean; head: Head }>(`/projects/${id}/scene`).then(check) }
  history(id: string, limit = 30) { return this.t.json<{ ok: boolean; revisions: Revision[]; can_undo: boolean; can_redo: boolean }>(`/projects/${id}/history?limit=${limit}`).then(check) }
  apply(id: string, operations: Op[], expectedRevision?: number, commandId?: string) {
    return this.t.json<ApplyResult>(`/projects/${id}/commands`, { method: 'POST', body: { operations, expected_revision: expectedRevision, command_id: commandId, actor: 'user' } })
  }
  undo(id: string) { return this.t.json<any>(`/projects/${id}/undo`, { method: 'POST', body: {} }) }
  redo(id: string) { return this.t.json<any>(`/projects/${id}/redo`, { method: 'POST', body: {} }) }
  check(id: string, body: Record<string, unknown>) { return this.t.json<any>(`/projects/${id}/check`, { method: 'POST', body }).then(check) }
  addProduct(id: string, body: Record<string, unknown>) { return this.t.json<any>(`/projects/${id}/products`, { method: 'POST', body }) }
  /** Tell the backend what is selected, so Hermes knows what "this" means. A hint: failures are ignored. */
  setSelection(id: string, kind: 'object' | 'opening' | 'wall' | null, selected: string | null) {
    return this.t.json<any>(`/projects/${id}/selection`, { method: 'POST', body: { kind, id: selected } })
  }
  shortlist(id: string, body: Record<string, unknown>) { return this.t.json<any>(`/projects/${id}/shortlist`, { method: 'POST', body, timeoutMs: 60000 }) }
  uploadPhoto(bytes: Uint8Array, contentType: string, projectId?: string) {
    return this.t.upload<{ ok: boolean; photo_id: string }>(`/photos${projectId ? `?project_id=${projectId}` : ''}`, bytes, contentType).then(check)
  }
  exportUrl(id: string, format: 'glb' | 'json' | 'summary') { return this.t.url(`/projects/${id}/export?format=${format}`) }
  /** Download an export; returns false when the host has no download hook (use the URL). */
  async download(id: string, format: 'glb' | 'json' | 'summary', name: string) {
    if (!this.t.download) return false
    await this.t.download(`/projects/${id}/export?format=${format}`, `${name}.${format === 'summary' ? 'txt' : format === 'json' ? 'room.json' : 'glb'}`)
    return true
  }
  photoUrl(photoId: string) { return this.t.url(`/photos/${photoId}`) }
}

/** Transport over plain fetch with a base URL (dev harness and tests). */
export function fetchTransport(base: string, headers: Record<string, string> = {}): Transport {
  return {
    async json(path, init) {
      const ctrl = new AbortController()
      const timer = setTimeout(() => ctrl.abort(), init?.timeoutMs ?? 20000)
      try {
        const res = await fetch(base + path, {
          method: init?.method || 'GET',
          headers: { ...headers, ...(init?.body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
          body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
          signal: ctrl.signal,
        })
        const text = await res.text()
        try { return JSON.parse(text) } catch { throw new ApiError('bad_response', `HTTP ${res.status}: ${text.slice(0, 200)}`) }
      } finally { clearTimeout(timer) }
    },
    async upload(path, bytes, contentType) {
      const res = await fetch(base + path, { method: 'POST', headers: { ...headers, 'Content-Type': contentType }, body: bytes })
      return res.json()
    },
    url(path) { return base + path },
  }
}
