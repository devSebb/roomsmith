// Pure editor math (no three.js) so it can be unit-tested in node.
// Same conventions as rs_core/geometry.py.

import type { Scene, SceneObject, Wall } from '../types'

export type P = [number, number] // (x, z)

export const GRID = 0.05
export const SNAP_DIST = 0.12

export const sub = (a: P, b: P): P => [a[0] - b[0], a[1] - b[1]]
export const add = (a: P, b: P): P => [a[0] + b[0], a[1] + b[1]]
export const mul = (a: P, k: number): P => [a[0] * k, a[1] * k]
export const dot = (a: P, b: P) => a[0] * b[0] + a[1] * b[1]
export const len = (a: P) => Math.hypot(a[0], a[1])
export const norm = (a: P): P => { const l = len(a); return l < 1e-9 ? [0, 0] : [a[0] / l, a[1] / l] }
export const dist = (a: P, b: P) => Math.hypot(a[0] - b[0], a[1] - b[1])

export function rotate(p: P, yaw: number): P {
  const c = Math.cos(yaw), s = Math.sin(yaw)
  return [p[0] * c + p[1] * s, -p[0] * s + p[1] * c]
}
export const front = (yaw: number): P => [-Math.sin(yaw), -Math.cos(yaw)]
export const right = (yaw: number): P => [Math.cos(yaw), -Math.sin(yaw)]
export const yawFacing = (d: P) => normalizeYaw(Math.atan2(-d[0], -d[1]))
export function normalizeYaw(y: number) {
  let r = ((y + Math.PI) % (2 * Math.PI))
  if (r <= 0) r += 2 * Math.PI
  return r - Math.PI
}
export const inwardNormal = (a: P, b: P): P => { const d = norm(sub(b, a)); return [-d[1], d[0]] }

export function outline(scene: Scene): P[] { return scene.room.vertices.map(v => [v.x, v.z]) }
export function wallSegment(scene: Scene, w: Wall): [P, P] {
  const vm = new Map(scene.room.vertices.map(v => [v.id, v]))
  const a = vm.get(w.a)!, b = vm.get(w.b)!
  return [[a.x, a.z], [b.x, b.z]]
}
export function wallLength(scene: Scene, w: Wall) { const [a, b] = wallSegment(scene, w); return dist(a, b) }

export function footprint(o: SceneObject): P[] {
  const [w, , d] = o.dimensions_m
  const c: P = [o.position_m[0], o.position_m[2]]
  const hw = w / 2, hd = d / 2
  return ([[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]] as P[]).map(p => add(c, rotate(p, o.yaw_rad)))
}

export function bounds(pts: P[]) {
  let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity
  for (const [x, z] of pts) { x0 = Math.min(x0, x); z0 = Math.min(z0, z); x1 = Math.max(x1, x); z1 = Math.max(z1, z) }
  return { x0, z0, x1, z1 }
}

export function pointSegDist(p: P, a: P, b: P) {
  const ab = sub(b, a), ab2 = dot(ab, ab)
  if (ab2 < 1e-12) return dist(p, a)
  const t = Math.max(0, Math.min(1, dot(sub(p, a), ab) / ab2))
  return dist(p, add(a, mul(ab, t)))
}

export function pointInPoly(p: P, poly: P[]) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, zi] = poly[i], [xj, zj] = poly[j]
    if ((zi > p[1]) !== (zj > p[1]) && p[0] < xi + (p[1] - zi) * (xj - xi) / (zj - zi)) inside = !inside
  }
  return inside
}

function axes(poly: P[]): P[] {
  const out: P[] = []
  for (let i = 0; i < poly.length; i++) {
    const e = sub(poly[(i + 1) % poly.length], poly[i])
    if (len(e) > 1e-9) out.push(norm([-e[1], e[0]]))
  }
  return out
}
function project(poly: P[], axis: P): [number, number] {
  let lo = Infinity, hi = -Infinity
  for (const p of poly) { const v = dot(p, axis); lo = Math.min(lo, v); hi = Math.max(hi, v) }
  return [lo, hi]
}
/** Minimum translation distance separating two convex polygons; 0 if apart. */
export function overlapDepth(a: P[], b: P[]) {
  let best = Infinity
  for (const ax of [...axes(a), ...axes(b)]) {
    const [a0, a1] = project(a, ax), [b0, b1] = project(b, ax)
    const o = Math.min(a1, b1) - Math.max(a0, b0)
    if (o <= 1e-9) return 0
    best = Math.min(best, o)
  }
  return best === Infinity ? 0 : best
}

export const snapGrid = (v: number, grid = GRID) => Math.round(v / grid) * grid

/**
 * Snap a dragged object's centre: to the grid, then flush against a wall when
 * one of its sides is within SNAP_DIST of it, then to another object's edge.
 * Returns the snapped centre and the yaw to use (objects snap their back to a
 * wall and face into the room when `alignToWall` is on).
 */
export function snapObject(scene: Scene, o: SceneObject, centre: P, yaw: number, alignToWall: boolean, others: SceneObject[]): { centre: P; yaw: number; snapped: 'wall' | 'object' | 'grid' | null } {
  let c: P = [snapGrid(centre[0]), snapGrid(centre[1])]
  let y = yaw
  let snapped: 'wall' | 'object' | 'grid' | null = 'grid'
  const [w, , d] = o.dimensions_m
  // walls: distance from the object's back face to each wall
  let bestWall: { dist: number; n: P; a: P; b: P } | null = null
  for (const wall of scene.room.walls) {
    const [a, b] = wallSegment(scene, wall)
    const n = inwardNormal(a, b)
    // candidate yaw facing into the room from this wall
    const candYaw = alignToWall ? yawFacing(n) : y
    const back = add(c, mul(front(candYaw), -d / 2))
    const dd = pointSegDist(back, a, b)
    const t = dot(sub(c, a), norm(sub(b, a)))
    const L = dist(a, b)
    if (dd < SNAP_DIST && t > -w && t < L + w && (!bestWall || dd < bestWall.dist)) bestWall = { dist: dd, n, a, b }
  }
  if (bestWall) {
    if (alignToWall) y = yawFacing(bestWall.n)
    // move so the back face sits 2 cm off the wall line
    const backOff = d / 2 + 0.02
    const along = dot(sub(c, bestWall.a), norm(sub(bestWall.b, bestWall.a)))
    const onWall = add(bestWall.a, mul(norm(sub(bestWall.b, bestWall.a)), along))
    c = add(onWall, mul(bestWall.n, backOff))
    snapped = 'wall'
  }
  // other objects: align edges when close (axis-aligned approximation on bounding boxes)
  const mine = bounds(footprint({ ...o, position_m: [c[0], 0, c[1]], yaw_rad: y }))
  let shiftX = 0, shiftZ = 0, bestDx = SNAP_DIST, bestDz = SNAP_DIST
  for (const ot of others) {
    if (ot.id === o.id || ot.mount !== 'floor') continue
    const ob = bounds(footprint(ot))
    for (const [m, t] of [[mine.x0, ob.x1], [mine.x1, ob.x0], [mine.x0, ob.x0], [mine.x1, ob.x1]]) {
      const dx = t - m
      if (Math.abs(dx) < bestDx && Math.abs(dx) > 1e-6 && !(mine.z1 < ob.z0 - 1 || mine.z0 > ob.z1 + 1)) { bestDx = Math.abs(dx); shiftX = dx }
    }
    for (const [m, t] of [[mine.z0, ob.z1], [mine.z1, ob.z0], [mine.z0, ob.z0], [mine.z1, ob.z1]]) {
      const dz = t - m
      if (Math.abs(dz) < bestDz && Math.abs(dz) > 1e-6 && !(mine.x1 < ob.x0 - 1 || mine.x0 > ob.x1 + 1)) { bestDz = Math.abs(dz); shiftZ = dz }
    }
  }
  if (snapped !== 'wall' && (shiftX !== 0 || shiftZ !== 0)) {
    c = [c[0] + shiftX, c[1] + shiftZ]
    snapped = 'object'
  } else if (snapped === 'wall' && (shiftX !== 0)) {
    // keep flush to the wall but slide along it to meet a neighbour's edge
    const n = bestWall!.n
    if (Math.abs(n[0]) < 0.5) c = [c[0] + shiftX, c[1]]
    else if (shiftZ !== 0) c = [c[0], c[1] + shiftZ]
  }
  c = keepInside(scene, o, c, y)
  return { centre: c, yaw: y, snapped }
}

/** Push a centre back so the footprint stays within the room's bounding box. */
export function keepInside(scene: Scene, o: SceneObject, centre: P, yaw: number): P {
  if (o.mount === 'wall') return centre
  const room = bounds(outline(scene))
  let c: P = [centre[0], centre[1]]
  for (let i = 0; i < 2; i++) {
    const fp = bounds(footprint({ ...o, position_m: [c[0], 0, c[1]], yaw_rad: yaw }))
    let dx = 0, dz = 0
    if (fp.x0 < room.x0) dx = room.x0 - fp.x0
    else if (fp.x1 > room.x1) dx = room.x1 - fp.x1
    if (fp.z0 < room.z0) dz = room.z0 - fp.z0
    else if (fp.z1 > room.z1) dz = room.z1 - fp.z1
    if (!dx && !dz) break
    c = [c[0] + dx, c[1] + dz]
  }
  return c
}

/** Wall overlap check used to tint a dragged object. */
export function overlapsAny(scene: Scene, o: SceneObject, centre: P, yaw: number): string[] {
  const fp = footprint({ ...o, position_m: [centre[0], 0, centre[1]], yaw_rad: yaw })
  const out: string[] = []
  for (const ot of scene.objects) {
    if (ot.id === o.id || ot.mount !== 'floor' || ot.category === 'rug' || o.mount !== 'floor') continue
    if (overlapDepth(fp, footprint(ot)) > 0.01) out.push(ot.id)
  }
  const poly = outline(scene)
  if (fp.some(p => !pointInPoly(p, poly) && Math.min(...poly.map((_, i) => pointSegDist(p, poly[i], poly[(i + 1) % poly.length]))) > 0.005)) out.push('__room__')
  return out
}

export const fmt = (v: number, digits = 2) => {
  const s = v.toFixed(digits)
  return s.replace(/\.?0+$/, '')
}
export const cm = (v: number) => `${Math.round(v * 100)} cm`
export const deg = (r: number) => Math.round((r * 180) / Math.PI)
export const rad = (d: number) => (d * Math.PI) / 180

/** "USD 1,899" / "USD 249.50" — the same form the backend prints. */
export const money = (amount: number, currency?: string | null) => {
  const cents = Math.round(amount * 100)
  const whole = cents % 100 === 0
  const body = (cents / 100).toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2 })
  return currency ? `${currency} ${body}` : body
}

/** Geometry and wording of the budget bar. `fill` and `tick` are 0..1 of the bar's width;
 *  `tick` (where the kept-back part starts) is null when the user set no buffer. */
export function budgetBar(b: { limit: number; currency: string | null; reserve: number; spent: number }) {
  const limit = Math.max(b.limit, 0.01)
  const over = b.spent > b.limit + 1e-9
  const state: 'ok' | 'reserve' | 'over' = over ? 'over' : b.reserve > 0 && b.spent > b.limit - b.reserve + 1e-9 ? 'reserve' : 'ok'
  const left = b.limit - b.spent
  return {
    fill: Math.min(1, Math.max(0, b.spent / limit)),
    tick: b.reserve > 0 ? Math.min(1, Math.max(0, (b.limit - b.reserve) / limit)) : null,
    state,
    text: `${money(b.spent, b.currency)} of ${money(b.limit)}`,
    left: over ? `${money(-left, b.currency)} over` : `${money(left)} left`,
  }
}
