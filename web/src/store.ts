// Editor state: the current room, polling for changes made by Hermes,
// optimistic commands with conflict recovery, undo/redo. Framework-free;
// React subscribes through `subscribe`.

import { Api, ApiError } from './api'
import type { Head, Issue, Op, ProjectRow, Revision, Scene } from './types'

export interface Toast { id: number; kind: 'info' | 'warn' | 'error' | 'agent'; text: string; ids?: string[] }

export interface State {
  projects: ProjectRow[]
  projectId: string | null
  scene: Scene | null
  revision: number
  issues: Issue[]
  canUndo: boolean
  canRedo: boolean
  head: Head | null
  history: Revision[]
  selectedId: string | null
  selectedOpeningId: string | null
  selectedWallId: string | null
  loading: boolean
  error: string | null
  toasts: Toast[]
  online: boolean
  lastAgentChange: { revision: number; summary: string; ids: string[] } | null
}

type Listener = (s: State) => void

let toastSeq = 1
const uuid = () => (typeof globalThis.crypto?.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`)

export class Store {
  state: State = {
    projects: [], projectId: null, scene: null, revision: 0, issues: [], canUndo: false, canRedo: false, head: null, history: [],
    selectedId: null, selectedOpeningId: null, selectedWallId: null, loading: false, error: null, toasts: [], online: true, lastAgentChange: null,
  }
  private listeners = new Set<Listener>()
  private polling = false
  private pollAbort = 0
  private pending = 0
  private disposed = false
  onFlash: ((ids: string[]) => void) | null = null

  constructor(public api: Api, private persist?: { get(k: string): string | null; set(k: string, v: string): void }) {}

  subscribe(fn: Listener) { this.listeners.add(fn); fn(this.state); return () => { this.listeners.delete(fn) } }
  private set(patch: Partial<State>) { this.state = { ...this.state, ...patch }; for (const l of this.listeners) l(this.state) }

  toast(kind: Toast['kind'], text: string, ids?: string[]) {
    const t = { id: toastSeq++, kind, text, ids }
    this.set({ toasts: [...this.state.toasts.slice(-3), t] })
    setTimeout(() => this.set({ toasts: this.state.toasts.filter(x => x.id !== t.id) }), kind === 'error' ? 7000 : 4500)
  }

  dispose() { this.disposed = true; this.polling = false; this.pollAbort++ }

  // ------------------------------------------------------------ loading

  async refreshProjects() {
    try {
      const r = await this.api.listProjects()
      this.knownActive = r.active_project_id
      this.set({ projects: r.projects, online: true, error: null })
      return r
    } catch (e: any) {
      this.set({ online: false, error: friendly(e) })
      return null
    }
  }

  async boot() {
    this.set({ loading: true })
    const r = await this.refreshProjects()
    const remembered = this.persist?.get('projectId') || null
    const pick = r?.projects.find(p => p.project_id === remembered)?.project_id || r?.active_project_id || r?.projects[0]?.project_id || null
    if (pick) await this.open(pick)
    else this.set({ loading: false })
  }

  async open(projectId: string) {
    this.pollAbort++
    this.polling = false // an in-flight long-poll for the previous room exits on its token; start a fresh one
    this.set({ loading: true, projectId, selectedId: null, selectedOpeningId: null, selectedWallId: null })
    this.persist?.set('projectId', projectId)
    try {
      const r = await this.api.scene(projectId)
      this.set({ scene: r.scene, revision: r.revision, issues: r.issues, canUndo: r.can_undo, canRedo: r.can_redo, head: r.head, loading: false, error: null, online: true })
      this.loadHistory()
      this.startPolling()
    } catch (e: any) {
      this.set({ loading: false, error: friendly(e), scene: null })
    }
  }

  async loadHistory() {
    if (!this.state.projectId) return
    try { const h = await this.api.history(this.state.projectId, 30); this.set({ history: h.revisions, canUndo: h.can_undo, canRedo: h.can_redo }) } catch { /* ignore */ }
  }

  /** Long-poll window in seconds; adapts downward when the transport cuts long requests. */
  private waitSeconds = 20
  /** The active room id the server last told us about; the editor follows when Hermes changes it. */
  private knownActive: string | null = null

  private async startPolling() {
    if (this.polling) return
    this.polling = true
    const token = ++this.pollAbort
    let backoff = 1000
    let failures = 0
    while (!this.disposed && token === this.pollAbort && this.state.projectId) {
      const pid = this.state.projectId
      try {
        const h = await this.api.wait(pid, this.state.revision, this.waitSeconds, this.knownActive)
        if (token !== this.pollAbort) break
        backoff = 1000; failures = 0
        if (!this.state.online) this.set({ online: true, error: null })
        if (h.active_changed && h.active_project_id && h.active_project_id !== pid && this.pending === 0) {
          // Hermes created or opened another room: follow it, like a tab switch the agent made.
          this.knownActive = h.active_project_id
          const r = await this.refreshProjects()
          const name = r?.projects.find(p => p.project_id === h.active_project_id)?.name || 'another room'
          this.toast('agent', `Hermes opened ${name}`)
          await this.open(h.active_project_id)
          return
        }
        if (h.active_project_id !== undefined) this.knownActive = h.active_project_id
        if (h.changed && h.revision > this.state.revision && this.pending === 0) await this.pull(h)
        else if (!h.changed) void this.refreshProjects() // idle tick: keep the room list current (renames/deletes elsewhere)
      } catch (e: any) {
        if (token !== this.pollAbort) break
        if (e instanceof ApiError && e.code === 'not_found') { this.set({ error: 'This room was deleted.', scene: null, projectId: null }); break }
        // A proxy that buffers or times out long requests (the Hermes plugin host, an SSH
        // forward) shows up as repeated failures: shorten the wait window so we stay live.
        this.waitSeconds = Math.max(4, Math.floor(this.waitSeconds / 2))
        if (++failures >= 2) this.set({ online: false })
        await sleep(backoff)
        backoff = Math.min(backoff * 2, 15000)
      }
    }
    if (token === this.pollAbort) this.polling = false
  }

  /** Fetch the latest scene after someone else changed it. */
  private async pull(h?: Head) {
    const pid = this.state.projectId
    if (!pid) return
    const r = await this.api.scene(pid)
    const prevRev = this.state.revision
    const head = r.head
    this.set({ scene: r.scene, revision: r.revision, issues: r.issues, canUndo: r.can_undo, canRedo: r.can_redo, head })
    if (head.revision > prevRev && head.actor === 'agent') {
      const summary = head.summary.replace(/^Hermes: /, '')
      this.set({ lastAgentChange: { revision: head.revision, summary, ids: head.changed_ids } })
      this.toast('agent', `Hermes: ${summary}`, head.changed_ids)
      this.onFlash?.(head.changed_ids)
    } else if (head.revision > prevRev && head.actor !== 'user') {
      this.toast('info', head.summary)
    }
    this.loadHistory()
    if (head.revision !== prevRev) this.refreshProjects()
  }

  // ------------------------------------------------------------ editing

  select(id: string | null) { if (id !== this.state.selectedId) this.set({ selectedId: id, selectedOpeningId: id ? null : this.state.selectedOpeningId }) }
  selectOpening(id: string | null) { this.set({ selectedOpeningId: id, selectedId: id ? null : this.state.selectedId }) }
  selectWall(id: string | null) { this.set({ selectedWallId: id }) }

  /** Apply operations. Optimistic: `optimistic(scene)` mutates a copy that is shown at once. */
  async apply(ops: Op[], optimistic?: (scene: Scene) => void, opts: { silent?: boolean } = {}) {
    const pid = this.state.projectId
    if (!pid || !this.state.scene) return null
    const base = this.state.revision
    if (optimistic) {
      const copy = JSON.parse(JSON.stringify(this.state.scene)) as Scene
      optimistic(copy)
      this.set({ scene: copy })
    }
    this.pending++
    try {
      let r = await this.api.apply(pid, ops, base, uuid())
      if (!r.ok && r.error?.code === 'revision_conflict') {
        // someone else wrote first: refetch and reapply on top
        await this.pull()
        r = await this.api.apply(pid, ops, this.state.revision, uuid())
      }
      if (!r.ok) {
        this.toast('error', r.error?.message || 'Edit rejected')
        await this.pull()
        return r
      }
      await this.pull()
      const warn = (r.issues || []).filter(i => i.code !== 'uncalibrated')
      if (warn.length && !opts.silent) this.toast('warn', warn.map(i => i.message).join(' · '), warn.flatMap(i => i.ids))
      return r
    } catch (e: any) {
      this.toast('error', friendly(e))
      this.set({ online: false })
      try { await this.pull() } catch { /* offline */ }
      return null
    } finally {
      this.pending--
    }
  }

  moveObject(id: string, position: [number, number, number], yaw: number) {
    return this.apply([{ op: 'move_object', id, place: { position_m: position, yaw_rad: yaw } }], s => {
      const o = s.objects.find(x => x.id === id); if (o) { o.position_m = position; o.yaw_rad = yaw }
    }, { silent: false })
  }
  rotateObject(id: string, yaw: number) {
    return this.apply([{ op: 'rotate_object', id, yaw_rad: yaw }], s => { const o = s.objects.find(x => x.id === id); if (o) o.yaw_rad = yaw })
  }
  deleteObject(id: string) {
    return this.apply([{ op: 'remove_object', id }], s => { s.objects = s.objects.filter(o => o.id !== id) })
  }
  duplicateObject(id: string) { return this.apply([{ op: 'duplicate_object', id }]) }

  async undo() {
    const pid = this.state.projectId; if (!pid) return
    this.pending++
    try { const r = await this.api.undo(pid); if (!r.ok) this.toast('info', r.error?.message || 'Nothing to undo'); await this.pull() } catch (e: any) { this.toast('error', friendly(e)) } finally { this.pending-- }
  }
  async redo() {
    const pid = this.state.projectId; if (!pid) return
    this.pending++
    try { const r = await this.api.redo(pid); if (!r.ok) this.toast('info', r.error?.message || 'Nothing to redo'); await this.pull() } catch (e: any) { this.toast('error', friendly(e)) } finally { this.pending-- }
  }

  // ------------------------------------------------------------ projects

  async createRoom(body: { name?: string; width_m?: number; depth_m?: number; height_m?: number; layout?: unknown; import?: unknown }) {
    try {
      const r = await this.api.createProject(body)
      await this.refreshProjects()
      await this.open(r.project_id)
      this.toast('info', `Created ${r.name}`)
      return r
    } catch (e: any) { this.toast('error', friendly(e)); return null }
  }
  async switchRoom(id: string) {
    try { await this.api.activate(id) } catch { /* ignore */ }
    await this.refreshProjects()
    await this.open(id)
  }
  async renameRoom(name: string) {
    const pid = this.state.projectId; if (!pid) return
    try { await this.api.rename(pid, name); await this.refreshProjects(); await this.pull() } catch (e: any) { this.toast('error', friendly(e)) }
  }
  async deleteRoom() {
    const pid = this.state.projectId; if (!pid) return
    try {
      await this.api.delete(pid)
      this.pollAbort++; this.polling = false
      const r = await this.refreshProjects()
      const next = r?.active_project_id || r?.projects[0]?.project_id || null
      if (next) await this.open(next); else this.set({ projectId: null, scene: null, revision: 0, issues: [], history: [] })
    } catch (e: any) { this.toast('error', friendly(e)) }
  }

  async addProduct(body: Record<string, unknown>) {
    const pid = this.state.projectId; if (!pid) return null
    this.pending++
    try {
      const r = await this.api.addProduct(pid, { ...body, expected_revision: this.state.revision })
      if (!r.ok) { this.toast('error', r.error?.message || 'Could not add product'); return r }
      await this.pull()
      if (r.note) this.toast('info', r.note)
      return r
    } catch (e: any) { this.toast('error', friendly(e)); return null } finally { this.pending-- }
  }

  async check(body: Record<string, unknown>) {
    const pid = this.state.projectId; if (!pid) return null
    try { return await this.api.check(pid, body) } catch (e: any) { this.toast('error', friendly(e)); return null }
  }
}

export function friendly(e: any): string {
  if (e instanceof ApiError) return e.message
  if (e?.name === 'AbortError') return 'The request timed out.'
  if (typeof e?.message === 'string') {
    if (/Failed to fetch|NetworkError|ECONNREFUSED/.test(e.message)) return 'Cannot reach the Roomsmith backend. Is the plugin enabled and the dashboard/gateway running?'
    return e.message
  }
  return String(e)
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
