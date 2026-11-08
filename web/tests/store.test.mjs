// node --test: Store live-sync behaviour against a scripted fake Api (no DOM, no network).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import * as esbuild from 'esbuild'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'

const here = dirname(fileURLToPath(import.meta.url))
const out = resolve(mkdtempSync(resolve(tmpdir(), 'rs-store-')), 'store.mjs')
await esbuild.build({ entryPoints: [resolve(here, '../src/store.ts')], bundle: true, format: 'esm', outfile: out, logLevel: 'silent' })
const { Store } = await import(out)

const scene = (id, name) => ({
  schema_version: 1, project: { id, name, units: 'm' }, calibration: { status: 'calibrated', reference: null },
  room: { height_m: 2.5, vertices: [], walls: [], floor: { color: '#000' }, ceiling: { color: '#fff' }, openings: [] }, objects: [], photos: [],
})
const head = (id, name, revision, actor = 'user') => ({ project_id: id, name, revision, updated_at: 0, actor, summary: `${actor} change`, changed_ids: [] })

/** A fake backend with two rooms; `active` can be flipped by the "agent". */
function fakeApi() {
  const rooms = { a: { name: 'Living room', revision: 3 }, b: { name: 'Room from photo', revision: 1 } }
  const st = { active: 'a', waits: [] }
  const api = {
    listProjects: async () => ({ ok: true, active_project_id: st.active, projects: Object.entries(rooms).map(([id, r]) => ({ project_id: id, name: r.name, revision: r.revision, active: id === st.active })) }),
    scene: async (id) => ({ ok: true, revision: rooms[id].revision, scene: scene(id, rooms[id].name), issues: [], can_undo: false, can_redo: false, head: head(id, rooms[id].name, rooms[id].revision) }),
    history: async () => ({ ok: true, revisions: [], can_undo: false, can_redo: false }),
    activate: async (id) => { st.active = id; return { ok: true } },
    wait: (id, after, timeout, active) => new Promise(res => {
      const w = { id, after, active, resolve: (patch = {}) => res({ ok: true, ...head(id, rooms[id].name, rooms[id].revision), changed: false, active_project_id: st.active, active_changed: active != null && active !== st.active, ...patch }) }
      st.waits.push(w)
    }),
  }
  return { api, st, rooms }
}

const tick = () => new Promise(r => setTimeout(r, 5))

test('editor follows when the agent activates another room, and keeps polling the new one', async () => {
  const { api, st } = fakeApi()
  const store = new Store(api)
  await store.boot(); await tick()
  assert.equal(store.state.projectId, 'a')
  assert.equal(st.waits.length, 1, 'one long-poll in flight')
  assert.equal(st.waits[0].active, 'a', 'poll carries the active id the client knows')

  // the agent creates room b (becomes active): the server wakes the poll
  st.active = 'b'; st.waits[0].resolve(); await tick(); await tick()
  assert.equal(store.state.projectId, 'b')
  assert.ok(store.state.toasts.some(t => /Hermes opened Room from photo/.test(t.text)))
  assert.equal(st.waits.length, 2, 'a fresh long-poll started for room b')
  assert.deepEqual([st.waits[1].id, st.waits[1].active], ['b', 'b'])
  store.dispose()
})

test('switching rooms by hand restarts the long-poll for the new room', async () => {
  const { api, st } = fakeApi()
  const store = new Store(api)
  await store.boot(); await tick()
  assert.equal(st.waits.length, 1)
  await store.switchRoom('b'); await tick()
  assert.equal(store.state.projectId, 'b')
  assert.equal(st.waits.length, 2, 'poll for b started while the poll for a was still in flight')
  assert.equal(st.waits[1].id, 'b')
  // the stale poll for a returning must not disturb room b
  st.waits[0].resolve({ changed: true, revision: 9 }); await tick()
  assert.equal(store.state.projectId, 'b')
  assert.equal(store.state.revision, 1)
  store.dispose()
})
