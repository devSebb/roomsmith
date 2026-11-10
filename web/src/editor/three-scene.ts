// Builds and updates three.js meshes from a Roomsmith scene.
// Objects are kept as a map so revisions can animate instead of rebuilding.

import * as THREE from 'three'
import type { Opening, Scene, SceneObject, Wall } from '../types'
import { inwardNormal, wallSegment, type P } from './math'
import { buildShape } from './shapes'

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
  /** Invisible bounding box: what the mouse picks and drags. The visible parts are `parts`. */
  mesh: THREE.Mesh
  parts: THREE.Mesh[] = []
  edges: THREE.LineSegments
  label: THREE.Sprite | null = null
  target = { x: 0, y: 0, z: 0, yaw: 0 }
  constructor(public obj: SceneObject, theme: Theme, showLabels: boolean) {
    const [w, h, d] = obj.dimensions_m
    const geo = obj.shape === 'cylinder' ? new THREE.CylinderGeometry(Math.min(w, d) / 2, Math.min(w, d) / 2, h, 32) : new THREE.BoxGeometry(w, h, d)
    geo.translate(0, h / 2, 0)
    this.mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }))
    this.mesh.userData.objectId = obj.id
    const shape = buildShape(obj)
    this.parts = shape.meshes
    this.edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.12 }))
    this.edges.visible = this.parts.length <= 1 // outline only for plain boxes; shaped objects speak for themselves
    this.group.add(this.mesh, shape.group, this.edges)
    this.applyOpacity()
    if (obj.product?.image_data) this.addProductCard(obj.product.image_data, w, h, d)
    if (showLabels) this.setLabel(theme)
    this.group.userData.objectId = obj.id
    this.snapTo(obj)
  }
  /** The product's photo on the stand-in, as a hang-tag on its front and back faces
   *  (the stand-in itself wears the photo's colour), or on top for flat things (rugs). */
  private addProductCard(dataUrl: string, w: number, h: number, d: number) {
    const flat = h < 0.15
    const faces: { faceW: number; faceH: number; pos: [number, number, number]; rotY: number; rotX: number }[] = flat
      ? [{ faceW: w, faceH: d, pos: [0, h + 0.003, 0], rotY: 0, rotX: -Math.PI / 2 }]
      : [
          { faceW: w, faceH: h, pos: [0, h / 2, -d / 2 - 0.004], rotY: Math.PI, rotX: 0 }, // front (-Z), faces outward
          { faceW: w, faceH: h, pos: [0, h / 2, d / 2 + 0.004], rotY: 0, rotX: 0 }, // back (+Z)
        ]
    const planes = faces.map(f => {
      const plane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.98, depthWrite: false }))
      plane.userData.objectId = this.obj.id
      plane.position.set(...f.pos)
      plane.rotation.set(f.rotX, f.rotY, 0)
      plane.renderOrder = 2
      plane.visible = false
      this.group.add(plane)
      return plane
    })
    new THREE.TextureLoader().load(dataUrl, t => {
      const img = t.image as { width: number; height: number }
      if (!img?.width || !img?.height) return
      t.colorSpace = THREE.SRGBColorSpace
      t.needsUpdate = true
      const ar = img.width / img.height
      faces.forEach((f, i) => {
        const fill = flat ? 0.96 : 0.62 // a tag, not a wrap
        let pw = f.faceW * fill, ph = pw / ar
        if (ph > f.faceH * fill) { ph = f.faceH * fill; pw = ph * ar }
        const plane = planes[i]
        ;(plane.material as THREE.MeshBasicMaterial).map = t
        ;(plane.material as THREE.MeshBasicMaterial).needsUpdate = true
        plane.scale.set(pw, ph, 1)
        plane.visible = true
      })
    })
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
    return a.shape === b.shape && a.color === b.color && a.name === b.name && a.category === b.category && a.mount === b.mount && a.locked === b.locked && (a.product?.image_data || null) === (b.product?.image_data || null) && a.dimensions_m.every((v, i) => Math.abs(v - b.dimensions_m[i]) < 1e-6)
  }
  private applyOpacity() {
    const o = this.obj.mount === 'ceiling' ? 0.45 : this.obj.locked ? 0.95 : 1 // hanging things must not hide the room under them
    for (const p of this.parts) { const m = p.material as THREE.MeshStandardMaterial; m.transparent = true; m.opacity = o }
  }
  setHighlight(mode: 'none' | 'selected' | 'hover' | 'bad' | 'flash', theme: Theme) {
    let emissive = new THREE.Color(0x000000), k = 0
    if (mode === 'selected') { emissive = col(theme.accent); k = 0.35 }
    else if (mode === 'hover') { emissive = col(theme.accent); k = 0.15 }
    else if (mode === 'bad') { emissive = col(theme.warn); k = 0.6 }
    else if (mode === 'flash') { emissive = col(theme.accent); k = 0.8 }
    for (const p of this.parts) { const m = p.material as THREE.MeshStandardMaterial; if ('emissive' in m) { m.emissive = emissive; m.emissiveIntensity = k } }
    this.applyOpacity()
  }
  dispose() {
    this.mesh.geometry.dispose()
    ;(this.mesh.material as THREE.Material).dispose()
    for (const p of this.parts) { p.geometry.dispose(); (p.material as THREE.Material).dispose() }
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
  const floorMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, side: THREE.DoubleSide, map: plankTexture(col(scene.room.floor.color, '#b08d62')) }) // the map carries the colour
  // planar UVs in metres so the planks repeat at real size
  const uv = floorGeo.attributes.position
  const uvs = new Float32Array(uv.count * 2)
  for (let i = 0; i < uv.count; i++) { uvs[i * 2] = uv.getX(i); uvs[i * 2 + 1] = uv.getZ(i) }
  floorGeo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2))
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
      mesh.castShadow = false // walls would shade the whole interior from the outside sun; furniture still casts
      list.push(mesh)
      group.add(mesh)
      if (y0 < 1e-6) { // skirting board along floor-touching pieces
        const sk = new THREE.Mesh(new THREE.BoxGeometry(len, 0.09, 0.012), new THREE.MeshStandardMaterial({ color: 0xf6f4ef, roughness: 0.8 }))
        sk.position.set(a[0] + dir[0] * (s + len / 2) + n[0] * 0.006, 0.045, a[1] + dir[1] * (s + len / 2) + n[1] * 0.006)
        sk.rotation.y = yaw
        group.add(sk)
      }
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

/** Procedural plank texture tinted with the floor colour; 1 texture unit = 1 m. */
function plankTexture(base: THREE.Color): THREE.Texture {
  const c = document.createElement('canvas'); c.width = 512; c.height = 512
  const ctx = c.getContext('2d')!
  const hsl = { h: 0, s: 0, l: 0 }; base.getHSL(hsl, THREE.SRGBColorSpace) // in sRGB, not the linear working space, or the planks come out dark
  const plankW = 512 / 6 // 6 planks per metre across (≈17 cm boards)
  for (let i = 0; i < 6; i++) {
    const seg = 2 + (i % 2)          // 2–3 boards per metre along
    const offset = (i * 97) % 512
    for (let j = 0; j < seg; j++) {
      const l = Math.max(0.08, Math.min(0.9, hsl.l + (((i * 7 + j * 13) % 9) - 4) * 0.011))
      ctx.fillStyle = `hsl(${hsl.h * 360}, ${hsl.s * 100}%, ${l * 100}%)`
      const y0 = ((offset + (j * 512) / seg) % 512)
      ctx.fillRect(i * plankW, y0, plankW, 512 / seg)
      if (y0 + 512 / seg > 512) ctx.fillRect(i * plankW, 0, plankW, y0 + 512 / seg - 512)
    }
    // grain lines
    ctx.strokeStyle = `hsla(${hsl.h * 360}, ${hsl.s * 100}%, ${Math.max(0, hsl.l - 0.12) * 100}%, 0.35)`
    ctx.lineWidth = 1
    for (let g = 0; g < 7; g++) { ctx.beginPath(); const x = i * plankW + ((g * 29 + i * 11) % plankW); ctx.moveTo(x, 0); ctx.lineTo(x + ((g % 3) - 1) * 6, 512); ctx.stroke() }
    ctx.fillStyle = 'rgba(0,0,0,0.28)'; ctx.fillRect(i * plankW, 0, 1.5, 512) // board gap
  }
  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
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
