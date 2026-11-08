// Builds and updates three.js meshes from a Roomsmith scene.
// Objects are kept as a map so revisions can animate instead of rebuilding.

import * as THREE from 'three'
import type { Opening, Scene, SceneObject, Wall } from '../types'
import { inwardNormal, wallSegment, type P } from './math'

export const WALL_T = 0.08
const LABEL_SCALE = 0.0035

export interface Theme { accent: string; text: string; muted: string; warn: string; bg: string }

function col(hex: string | undefined, fallback = '#9aa0a6') {
  try { return new THREE.Color(hex || fallback) } catch { return new THREE.Color(fallback) }
}

function makeLabel(text: string, theme: Theme, sub?: string): THREE.Sprite {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  const font = '600 28px system-ui, -apple-system, Segoe UI, sans-serif'
  const subFont = '400 22px system-ui, -apple-system, Segoe UI, sans-serif'
  ctx.font = font
  const w1 = ctx.measureText(text).width
  ctx.font = subFont
  const w2 = sub ? ctx.measureText(sub).width : 0
  const pad = 14
  canvas.width = Math.ceil(Math.max(w1, w2) + pad * 2)
  canvas.height = sub ? 76 : 48
  const c2 = canvas.getContext('2d')!
  c2.fillStyle = 'rgba(20,22,26,0.78)'
  const r = 12
  c2.beginPath()
  c2.roundRect(0, 0, canvas.width, canvas.height, r)
  c2.fill()
  c2.fillStyle = '#ffffff'
  c2.font = font
  c2.textBaseline = 'top'
  c2.fillText(text, pad, 10)
  if (sub) { c2.fillStyle = 'rgba(255,255,255,0.75)'; c2.font = subFont; c2.fillText(sub, pad, 44) }
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  const mat = new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(canvas.width * LABEL_SCALE, canvas.height * LABEL_SCALE, 1)
  sprite.renderOrder = 10
  return sprite
}

export class ObjectView {
  group = new THREE.Group()
  mesh: THREE.Mesh
  edges: THREE.LineSegments
  label: THREE.Sprite | null = null
  target = { x: 0, y: 0, z: 0, yaw: 0 }
  constructor(public obj: SceneObject, theme: Theme, showLabels: boolean) {
    const [w, h, d] = obj.dimensions_m
    const geo = obj.shape === 'cylinder' ? new THREE.CylinderGeometry(Math.min(w, d) / 2, Math.min(w, d) / 2, h, 32) : new THREE.BoxGeometry(w, h, d)
    geo.translate(0, h / 2, 0)
    const mat = new THREE.MeshStandardMaterial({ color: col(obj.color), roughness: 0.85, metalness: 0.0, transparent: true, opacity: 1 })
    this.mesh = new THREE.Mesh(geo, mat)
    this.mesh.castShadow = true
    this.mesh.receiveShadow = true
    this.mesh.userData.objectId = obj.id
    this.edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.18 }))
    this.group.add(this.mesh, this.edges)
    if (showLabels) this.setLabel(theme)
    this.group.userData.objectId = obj.id
    this.snapTo(obj)
  }
  setLabel(theme: Theme) {
    if (this.label) this.group.remove(this.label)
    const [w, h, d] = this.obj.dimensions_m
    this.label = makeLabel(this.obj.name, theme, `${w.toFixed(2)} × ${h.toFixed(2)} × ${d.toFixed(2)} m`)
    this.label.position.set(0, h + 0.25, 0)
    this.group.add(this.label)
  }
  snapTo(o: SceneObject) {
    this.obj = o
    this.target = { x: o.position_m[0], y: o.position_m[1], z: o.position_m[2], yaw: o.yaw_rad }
    this.group.position.set(o.position_m[0], o.position_m[1], o.position_m[2])
    this.group.rotation.y = o.yaw_rad
  }
  /** Set the animation target; `tick` moves toward it. */
  animateTo(o: SceneObject) {
    this.obj = o
    this.target = { x: o.position_m[0], y: o.position_m[1], z: o.position_m[2], yaw: o.yaw_rad }
  }
  tick(k: number) {
    const p = this.group.position
    p.x += (this.target.x - p.x) * k
    p.y += (this.target.y - p.y) * k
    p.z += (this.target.z - p.z) * k
    let dy = this.target.yaw - this.group.rotation.y
    while (dy > Math.PI) dy -= 2 * Math.PI
    while (dy < -Math.PI) dy += 2 * Math.PI
    this.group.rotation.y += dy * k
    return Math.abs(this.target.x - p.x) + Math.abs(this.target.z - p.z) + Math.abs(dy) > 1e-3
  }
  sameShape(o: SceneObject) {
    const a = this.obj, b = o
    return a.shape === b.shape && a.color === b.color && a.name === b.name && a.dimensions_m.every((v, i) => Math.abs(v - b.dimensions_m[i]) < 1e-6)
  }
  setHighlight(mode: 'none' | 'selected' | 'hover' | 'bad' | 'flash', theme: Theme) {
    const m = this.mesh.material as THREE.MeshStandardMaterial
    m.emissive = new THREE.Color(0x000000)
    m.emissiveIntensity = 0
    m.opacity = 1
    if (mode === 'selected') { m.emissive = col(theme.accent); m.emissiveIntensity = 0.35 }
    else if (mode === 'hover') { m.emissive = col(theme.accent); m.emissiveIntensity = 0.15 }
    else if (mode === 'bad') { m.emissive = col(theme.warn); m.emissiveIntensity = 0.6 }
    else if (mode === 'flash') { m.emissive = col(theme.accent); m.emissiveIntensity = 0.8 }
    if (this.obj.locked) m.opacity = 0.95
  }
  dispose() {
    this.mesh.geometry.dispose()
    ;(this.mesh.material as THREE.Material).dispose()
    this.edges.geometry.dispose()
    if (this.label) { (this.label.material as THREE.SpriteMaterial).map?.dispose(); this.label.material.dispose() }
  }
}

export interface RoomViews { group: THREE.Group; wallMeshes: Map<string, THREE.Mesh[]>; openingMeshes: Map<string, THREE.Mesh>; floor: THREE.Mesh; planLines: THREE.Group }

function wallPieces(scene: Scene, wall: Wall) {
  const [a, b] = wallSegment(scene, wall)
  const L = Math.hypot(b[0] - a[0], b[1] - a[1])
  const H = scene.room.height_m
  const ops = scene.room.openings.filter(o => o.wall_id === wall.id).sort((p, q) => p.offset_m - q.offset_m)
  const pieces: [number, number, number, number][] = []
  let t = 0
  for (const o of ops) {
    const s = o.offset_m, e = o.offset_m + o.width_m, sill = o.sill_m, top = o.sill_m + o.height_m
    if (s > t) pieces.push([t, s, 0, H])
    if (sill > 0) pieces.push([s, e, 0, sill])
    if (top < H) pieces.push([s, e, top, H])
    t = Math.max(t, e)
  }
  if (t < L) pieces.push([t, L, 0, H])
  return { a, b, L, pieces }
}

export function buildRoom(scene: Scene, theme: Theme): RoomViews {
  const group = new THREE.Group()
  const wallMeshes = new Map<string, THREE.Mesh[]>()
  const openingMeshes = new Map<string, THREE.Mesh>()
  // Floor: the outline as a flat polygon. Shape points are (x, -z) so that
  // rotateX(-90°) maps (x, -z, 0) -> (x, 0, z) with the normal pointing up.
  const pts = scene.room.vertices.map(v => new THREE.Vector2(v.x, -v.z))
  const shape = new THREE.Shape(pts)
  const floorGeo = new THREE.ShapeGeometry(shape)
  floorGeo.rotateX(-Math.PI / 2)
  floorGeo.computeVertexNormals()
  const floorMat = new THREE.MeshStandardMaterial({ color: col(scene.room.floor.color, '#b08d62'), roughness: 0.95, side: THREE.DoubleSide })
  const floor = new THREE.Mesh(floorGeo, floorMat)
  floor.receiveShadow = true
  floor.userData.floor = true
  group.add(floor)

  const planLines = new THREE.Group()
  for (const wall of scene.room.walls) {
    const { a, b, L, pieces } = wallPieces(scene, wall)
    const n = inwardNormal(a, b)
    const dir: P = [(b[0] - a[0]) / L, (b[1] - a[1]) / L]
    const yaw = -Math.atan2(dir[1], dir[0])
    const mat = new THREE.MeshStandardMaterial({ color: col(wall.color, '#f2efe9'), roughness: 0.9, transparent: true, opacity: 1, side: THREE.DoubleSide })
    const list: THREE.Mesh[] = []
    for (const [s, e, y0, y1] of pieces) {
      const len = e - s
      if (len <= 1e-6 || y1 - y0 <= 1e-6) continue
      const geo = new THREE.BoxGeometry(len, y1 - y0, WALL_T)
      geo.translate(0, (y1 - y0) / 2, 0)
      const mesh = new THREE.Mesh(geo, mat)
      const cx = a[0] + dir[0] * (s + len / 2) - n[0] * WALL_T / 2
      const cz = a[1] + dir[1] * (s + len / 2) - n[1] * WALL_T / 2
      mesh.position.set(cx, y0, cz)
      mesh.rotation.y = yaw
      mesh.userData.wallId = wall.id
      mesh.receiveShadow = true
      mesh.castShadow = true
      list.push(mesh)
      group.add(mesh)
    }
    wallMeshes.set(wall.id, list)
    // plan-view line with label
    const lineGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(a[0], 0.01, a[1]), new THREE.Vector3(b[0], 0.01, b[1])])
    const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: col(theme.text) }))
    planLines.add(line)
    const lbl = makeLabel(`${wall.id}${wall.label ? ' ' + wall.label : ''} · ${L.toFixed(2)} m`, theme)
    lbl.position.set((a[0] + b[0]) / 2 - n[0] * 0.35, 0.02, (a[1] + b[1]) / 2 - n[1] * 0.35)
    lbl.scale.multiplyScalar(0.8)
    planLines.add(lbl)
    // openings: a translucent panel in the gap, plus door swing arc in plan
    for (const o of scene.room.openings.filter(x => x.wall_id === wall.id)) {
      const panel = openingPanel(o, a, dir, n, yaw, theme)
      panel.userData.openingId = o.id
      openingMeshes.set(o.id, panel)
      group.add(panel)
      if (o.kind === 'door') {
        const arc = doorArc(o, a, dir, n, theme)
        planLines.add(arc)
      }
    }
  }
  group.add(planLines)
  return { group, wallMeshes, openingMeshes, floor, planLines }
}

function openingPanel(o: Opening, a: P, dir: P, n: P, yaw: number, theme: Theme) {
  const isWin = o.kind === 'window'
  const geo = new THREE.BoxGeometry(o.width_m, o.height_m, WALL_T * 0.6)
  geo.translate(0, o.height_m / 2, 0)
  const mat = new THREE.MeshStandardMaterial({
    color: isWin ? new THREE.Color('#9ec5e8') : new THREE.Color('#c9b08a'),
    transparent: true, opacity: isWin ? 0.45 : 0.55, roughness: 0.4, side: THREE.DoubleSide,
  })
  const mesh = new THREE.Mesh(geo, mat)
  const cx = a[0] + dir[0] * (o.offset_m + o.width_m / 2) - n[0] * WALL_T / 2
  const cz = a[1] + dir[1] * (o.offset_m + o.width_m / 2) - n[1] * WALL_T / 2
  mesh.position.set(cx, o.sill_m, cz)
  mesh.rotation.y = yaw
  return mesh
}

function doorArc(o: Opening, a: P, dir: P, n: P, theme: Theme) {
  const hingeAtStart = (o.hinge || 'left') === 'left'
  const hx = a[0] + dir[0] * (hingeAtStart ? o.offset_m : o.offset_m + o.width_m)
  const hz = a[1] + dir[1] * (hingeAtStart ? o.offset_m : o.offset_m + o.width_m)
  const sign = (o.swing || 'in') === 'out' ? -1 : 1
  const pts: THREE.Vector3[] = []
  const steps = 16
  const open: P = hingeAtStart ? [dir[0], dir[1]] : [-dir[0], -dir[1]]
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * (Math.PI / 2)
    const x = hx + (open[0] * Math.cos(t) + n[0] * sign * Math.sin(t)) * o.width_m
    const z = hz + (open[1] * Math.cos(t) + n[1] * sign * Math.sin(t)) * o.width_m
    pts.push(new THREE.Vector3(x, 0.012, z))
  }
  pts.push(new THREE.Vector3(hx, 0.012, hz))
  const geo = new THREE.BufferGeometry().setFromPoints(pts)
  return new THREE.Line(geo, new THREE.LineDashedMaterial({ color: col(theme.muted), dashSize: 0.08, gapSize: 0.05 }))
}

export function disposeGroup(g: THREE.Object3D) {
  g.traverse(obj => {
    const m = obj as THREE.Mesh
    if (m.geometry) m.geometry.dispose()
    const mat = (m as any).material as THREE.Material | THREE.Material[] | undefined
    if (Array.isArray(mat)) mat.forEach(x => x.dispose())
    else if (mat) { (mat as any).map?.dispose?.(); mat.dispose() }
  })
}
