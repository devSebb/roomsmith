// node --test: editor math, compiled on the fly with esbuild (no TS runtime needed)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import * as esbuild from 'esbuild'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'

const here = dirname(fileURLToPath(import.meta.url))
const out = resolve(mkdtempSync(resolve(tmpdir(), 'rs-math-')), 'math.mjs')
await esbuild.build({ entryPoints: [resolve(here, '../src/editor/math.ts')], bundle: true, format: 'esm', outfile: out, logLevel: 'silent' })
const m = await import(out)

const room = (w = 4, d = 5) => ({
  schema_version: 1, project: { id: 'p', name: 'r', units: 'm' }, calibration: { status: 'calibrated', reference: null },
  room: { height_m: 2.5, vertices: [{ id: 'v1', x: 0, z: 0 }, { id: 'v2', x: w, z: 0 }, { id: 'v3', x: w, z: d }, { id: 'v4', x: 0, z: d }],
    walls: [{ id: 'w1', a: 'v1', b: 'v2', color: '#fff' }, { id: 'w2', a: 'v2', b: 'v3', color: '#fff' }, { id: 'w3', a: 'v3', b: 'v4', color: '#fff' }, { id: 'w4', a: 'v4', b: 'v1', color: '#fff' }],
    floor: { color: '#000' }, ceiling: { color: '#fff' }, openings: [] },
  objects: [], photos: [],
})
const obj = (id, w, h, d, x, z, yaw = 0) => ({ id, name: id, category: 'other', shape: 'box', dimensions_m: [w, h, d], position_m: [x, 0, z], yaw_rad: yaw, mount: 'floor', color: '#000', locked: false })

test('vectors match the engine conventions', () => {
  assert.deepEqual(m.front(0).map(v => +v.toFixed(6)), [0, -1])
  assert.deepEqual(m.right(0).map(v => +v.toFixed(6)), [1, 0])
  assert.ok(Math.abs(m.yawFacing([0, 1]) - Math.PI) < 1e-9)
  assert.ok(Math.abs(m.normalizeYaw(3 * Math.PI) - Math.PI) < 1e-9)
  assert.deepEqual(m.inwardNormal([0, 0], [4, 0]).map(v => +v.toFixed(6)), [0, 1])
})

test('footprint and overlap', () => {
  const a = m.footprint(obj('a', 2, 1, 1, 0, 0))
  const b = m.footprint(obj('b', 2, 1, 1, 1.5, 0))
  assert.ok(Math.abs(m.overlapDepth(a, b) - 0.5) < 1e-9)
  assert.equal(m.overlapDepth(a, m.footprint(obj('c', 2, 1, 1, 2, 0))), 0)
})

test('snap to grid and to a wall, facing in', () => {
  const s = room()
  const o = obj('a', 1, 1, 0.5, 2, 2)
  const r = m.snapObject(s, o, [2.013, 0.27], 0, true, [])
  assert.equal(r.snapped, 'wall')
  assert.ok(Math.abs(r.centre[1] - 0.27) < 1e-9, 'flush to the back wall: ' + r.centre)
  assert.ok(Math.abs(r.yaw - Math.PI) < 1e-9, 'faces into the room')
  const g = m.snapObject(s, o, [2.013, 2.52], 0, true, [])
  assert.equal(g.snapped, 'grid')
  assert.deepEqual(g.centre.map(v => +v.toFixed(3)), [2, 2.5])
})

test('without wall alignment the yaw is kept and only a back face near a wall snaps', () => {
  const s = room()
  const facingIn = m.snapObject(s, obj('a', 1, 1, 0.5, 2, 2, Math.PI), [2.0, 0.28], Math.PI, false, [])
  assert.equal(facingIn.snapped, 'wall')
  assert.equal(facingIn.yaw, Math.PI)
  const facingWall = m.snapObject(s, obj('a', 1, 1, 0.5, 2, 2, 0), [2.0, 0.28], 0, false, [])
  assert.equal(facingWall.snapped, 'grid', 'front toward the wall: no wall snap without alignment')
  assert.equal(facingWall.yaw, 0)
})

test('edge alignment with a neighbour', () => {
  const s = room()
  const other = obj('b', 1, 1, 1, 1, 2.5)
  const r = m.snapObject(s, obj('a', 1, 1, 1, 2, 2.5), [2.06, 2.5], 0, true, [other])
  assert.equal(r.snapped, 'object')
  assert.ok(Math.abs(r.centre[0] - 2.0) < 1e-9, 'edges meet: ' + r.centre)
})

test('objects are kept inside the room while dragging', () => {
  const s = room()
  const c = m.keepInside(s, obj('a', 1, 1, 0.5, 0, 0), [4.3, 5.4], 0)
  assert.deepEqual(c.map(v => +v.toFixed(3)), [3.5, 4.75])
  const rot = m.keepInside(s, obj('a', 2, 1, 0.5, 0, 0), [0, 2.5], Math.PI / 2)
  assert.ok(rot[0] >= 0.25 - 1e-9, 'rotated footprint respected')
})

test('overlapsAny flags the room boundary and other objects', () => {
  const s = room()
  s.objects.push(obj('b', 1, 1, 1, 2, 2))
  assert.deepEqual(m.overlapsAny(s, obj('a', 1, 1, 1, 0, 0), [2.4, 2], 0), ['b'])
  assert.deepEqual(m.overlapsAny(s, obj('a', 1, 1, 1, 0, 0), [3.9, 2], 0), ['__room__'])
})

test('formatting helpers', () => {
  assert.equal(m.fmt(2.5), '2.5')
  assert.equal(m.fmt(2), '2')
  assert.equal(m.cm(0.123), '12 cm')
  assert.equal(m.deg(Math.PI), 180)
})

test('money prints like the backend', () => {
  assert.equal(m.money(1899, 'USD'), 'USD 1,899')
  assert.equal(m.money(249.5, 'USD'), 'USD 249.50')
  assert.equal(m.money(0.1 + 0.2), '0.30')
})

test('budget bar: share spent, where the buffer starts, and the three states', () => {
  let b = m.budgetBar({ limit: 1000, currency: 'USD', reserve: 0, spent: 250 })
  assert.deepEqual([b.fill, b.tick, b.state, b.text, b.left], [0.25, null, 'ok', 'USD 250 of 1,000', '750 left'])
  b = m.budgetBar({ limit: 1000, currency: 'USD', reserve: 100, spent: 950 })
  assert.deepEqual([b.fill, b.tick, b.state], [0.95, 0.9, 'reserve'])
  b = m.budgetBar({ limit: 1000, currency: 'USD', reserve: 0, spent: 1000 })
  assert.equal(b.state, 'ok') // exactly on the limit is not over
  b = m.budgetBar({ limit: 1000, currency: 'USD', reserve: 0, spent: 1140 })
  assert.deepEqual([b.fill, b.state, b.left], [1, 'over', 'USD 140 over'])
})
