// The editor core: a canvas, a scene, and callbacks. No React, no network.

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import type { Issue, Scene, SceneObject } from '../types'
import { normalizeYaw, overlapsAny, snapObject, type P } from './math'
import { ObjectView, buildRoom, disposeGroup, type RoomViews, type Theme } from './three-scene'

export type ViewMode = '3d' | 'plan'

export interface EditorCallbacks {
  onSelect?: (id: string | null) => void
  onHover?: (id: string | null) => void
  onMove?: (id: string, position: [number, number, number], yaw: number) => void
  onRotate?: (id: string, yaw: number) => void
  onDelete?: (id: string) => void
  onDuplicate?: (id: string) => void
  onUndo?: () => void
  onRedo?: () => void
  onViewChange?: (mode: ViewMode) => void
  onSelectOpening?: (id: string | null) => void
  onSelectWall?: (id: string | null) => void
  onDragState?: (dragging: boolean, snapped: string | null, bad: boolean) => void
}

export interface EditorOptions {
  theme: Theme
  showLabels?: boolean
  alignToWall?: boolean
}

export class Editor {
  readonly renderer: THREE.WebGLRenderer
  readonly scene3 = new THREE.Scene()
  readonly persp: THREE.PerspectiveCamera
  readonly ortho: THREE.OrthographicCamera
  camera: THREE.Camera
  controls: OrbitControls
  mode: ViewMode = '3d'
  theme: Theme
  showLabels: boolean
  alignToWall: boolean
  private room: RoomViews | null = null
  private roomKey = ''
  private sizeKey = ''
  private objects = new Map<string, ObjectView>()
  private scene: Scene | null = null
  private issues: Issue[] = []
  private selected: string | null = null
  private hovered: string | null = null
  private flashing = new Map<string, number>()
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private drag: { id: string; plane: THREE.Plane; offset: THREE.Vector3; startPos: THREE.Vector3; startYaw: number; yaw: number; moved: boolean; bad: boolean } | null = null
  private ro: ResizeObserver
  private raf = 0
  private disposed = false
  private lastT = 0
  private animating = false
  private lights = new THREE.Group()

  constructor(public container: HTMLElement, private cb: EditorCallbacks, opts: EditorOptions) {
    this.theme = opts.theme
    this.showLabels = opts.showLabels ?? true
    this.alignToWall = opts.alignToWall ?? true
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    const el = this.renderer.domElement
    el.style.display = 'block'
    el.style.width = '100%'
    el.style.height = '100%'
    el.style.touchAction = 'none'
    el.tabIndex = 0
    el.setAttribute('aria-label', 'Roomsmith 3D editor')
    container.appendChild(el)

    this.persp = new THREE.PerspectiveCamera(50, 1, 0.05, 200)
    this.ortho = new THREE.OrthographicCamera(-5, 5, 5, -5, 0.01, 100)
    this.camera = this.persp
    this.controls = new OrbitControls(this.persp, el)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.12
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02
    this.controls.minDistance = 1
    this.controls.maxDistance = 60
    // No right-button binding: Hermes Desktop opens its own context menu on right-click from the
    // main process (no renderer listener can stop it), so a right-drag pan would end in that menu.
    // Pan = shift-drag (OrbitControls' modifier rule on LEFT) or middle-drag; dolly = wheel.
    this.controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: null as any }

    this.buildLights()
    this.scene3.add(this.lights)
    const grid = new THREE.GridHelper(40, 40, 0x888888, 0x888888)
    ;(grid.material as THREE.Material).transparent = true
    ;(grid.material as THREE.Material).opacity = 0.12
    grid.position.y = -0.002
    this.scene3.add(grid)

    el.addEventListener('pointerdown', this.onPointerDown)
    el.addEventListener('pointermove', this.onPointerMove)
    el.addEventListener('pointerup', this.onPointerUp)
    el.addEventListener('pointercancel', this.onPointerUp)
    el.addEventListener('dblclick', this.onDblClick)
    el.addEventListener('keydown', this.onKeyDown)
    // stopPropagation too: Hermes Desktop opens its own menu on contextmenu events that reach its root
    el.addEventListener('contextmenu', e => { e.preventDefault(); e.stopPropagation() })
    this.ro = new ResizeObserver(() => this.resize())
    this.ro.observe(container)
    this.resize()
    this.loop(0)
  }

  // ------------------------------------------------------------ lifecycle

  private buildLights() {
    const hemi = new THREE.HemisphereLight(0xfff4e6, 0x6b7a8a, 1.0)
    const sun = new THREE.DirectionalLight(0xfff1dd, 1.25)
    sun.position.set(6, 10, 4)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.radius = 4
    sun.shadow.camera.near = 0.5
    sun.shadow.camera.far = 50
    sun.shadow.camera.left = sun.shadow.camera.bottom = -14
    sun.shadow.camera.right = sun.shadow.camera.top = 14
    sun.shadow.bias = -0.0005
    const fill = new THREE.DirectionalLight(0xffffff, 0.35)
    fill.position.set(-5, 6, -6)
    this.lights.add(hemi, sun, fill)
  }

  resize() {
    const w = Math.max(1, this.container.clientWidth)
    const h = Math.max(1, this.container.clientHeight)
    this.renderer.setSize(w, h, false)
    this.persp.aspect = w / h
    this.persp.updateProjectionMatrix()
    this.fitOrtho(w / h)
    this.render()
  }

  private fitOrtho(aspect: number) {
    if (!this.scene) return
    const xs = this.scene.room.vertices.map(v => v.x), zs = this.scene.room.vertices.map(v => v.z)
    const w = Math.max(...xs) - Math.min(...xs) + 1.2, d = Math.max(...zs) - Math.min(...zs) + 1.2
    let half = Math.max(w / 2, d / 2 * aspect) * 1.02
    half = half / (this.orthoZoom || 1)
    this.ortho.left = -half
    this.ortho.right = half
    this.ortho.top = half / aspect
    this.ortho.bottom = -half / aspect
    this.ortho.updateProjectionMatrix()
  }
  private orthoZoom = 1

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    this.ro.disconnect()
    const el = this.renderer.domElement
    el.removeEventListener('pointerdown', this.onPointerDown)
    el.removeEventListener('pointermove', this.onPointerMove)
    el.removeEventListener('pointerup', this.onPointerUp)
    el.removeEventListener('pointercancel', this.onPointerUp)
    el.removeEventListener('dblclick', this.onDblClick)
    el.removeEventListener('keydown', this.onKeyDown)
    this.controls.dispose()
    for (const v of this.objects.values()) v.dispose()
    if (this.room) disposeGroup(this.room.group)
    this.renderer.dispose()
    el.remove()
  }

  private loop = (t: number) => {
    if (this.disposed) return
    this.raf = requestAnimationFrame(this.loop)
    const dt = Math.min(0.05, (t - this.lastT) / 1000 || 0.016)
    this.lastT = t
    let moving = false
    const k = 1 - Math.pow(0.001, dt) // smooth exponential approach (~0.3 s)
    for (const v of this.objects.values()) if (v.tick(k)) moving = true
    for (const [id, until] of this.flashing) {
      if (t > until) { this.flashing.delete(id); this.applyHighlight(id) }
      else moving = true
    }
    if (this.mode === '3d') this.controls.update()
    this.fadeWalls()
    this.render()
    this.animating = moving
  }

  render() { this.renderer.render(this.scene3, this.camera) }

  // ------------------------------------------------------------ data in

  setTheme(theme: Theme) {
    this.theme = theme
    if (this.scene) { this.roomKey = ''; this.setScene(this.scene, this.issues, false) }
  }

  /** Remove the room and every object (the room was deleted or none is open). */
  clear() {
    if (this.room) { this.scene3.remove(this.room.group); disposeGroup(this.room.group); this.room = null; this.roomKey = '' }
    for (const [, v] of this.objects) { this.scene3.remove(v.group); v.dispose() }
    this.objects.clear()
    this.scene = null
    this.render()
  }

  setScene(scene: Scene, issues: Issue[], animate = true) {
    const first = !this.scene
    this.scene = scene
    this.issues = issues
    const key = JSON.stringify(scene.room) + this.theme.text
    const sizeKey = JSON.stringify(scene.room.vertices) + '|' + (scene.project?.id ?? '')
    const outlineChanged = sizeKey !== this.sizeKey
    this.sizeKey = sizeKey
    if (key !== this.roomKey) {
      if (this.room) { this.scene3.remove(this.room.group); disposeGroup(this.room.group) }
      this.room = buildRoom(scene, this.theme)
      this.room.planLines.visible = this.mode === 'plan'
      this.scene3.add(this.room.group)
      this.roomKey = key
      this.fitOrtho(this.persp.aspect)
    }
    const seen = new Set<string>()
    for (const o of scene.objects) {
      seen.add(o.id)
      const v = this.objects.get(o.id)
      if (v && v.sameShape(o)) {
        if (this.drag?.id !== o.id) { animate ? v.animateTo(o) : v.snapTo(o) }
        else v.obj = o
      } else {
        if (v) { this.scene3.remove(v.group); v.dispose() }
        const nv = new ObjectView(o, this.theme, this.showLabels)
        if (v && animate) { nv.group.position.copy(v.group.position); nv.group.rotation.y = v.group.rotation.y; nv.animateTo(o) }
        this.objects.set(o.id, nv)
        this.scene3.add(nv.group)
      }
    }
    for (const [id, v] of this.objects) if (!seen.has(id)) { this.scene3.remove(v.group); v.dispose(); this.objects.delete(id) }
    if (this.selected && !seen.has(this.selected)) this.select(null)
    for (const id of this.objects.keys()) this.applyHighlight(id)
    if (first || (outlineChanged && !this.drag)) this.frameRoom() // new room, or its walls moved (calibration, resize): re-frame
  }

  setLabels(on: boolean) {
    this.showLabels = on
    for (const v of this.objects.values()) {
      if (on && !v.label) v.setLabel(this.theme)
      if (!on && v.label) { v.group.remove(v.label); v.label = null }
    }
  }

  flash(ids: string[]) {
    const until = performance.now() + 900
    for (const id of ids) if (this.objects.has(id)) { this.flashing.set(id, until); this.objects.get(id)!.setHighlight('flash', this.theme) }
  }

  // ------------------------------------------------------------ camera

  frameRoom() {
    if (!this.scene) return
    const xs = this.scene.room.vertices.map(v => v.x), zs = this.scene.room.vertices.map(v => v.z)
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cz = (Math.min(...zs) + Math.max(...zs)) / 2
    // fit the room's bounding sphere to the camera's field of view (whichever of the
    // vertical/horizontal FOV is tighter for this viewport), looking from the front
    // wall (+z) side and slightly to the right, like the camera that took the photo
    const w = Math.max(...xs) - Math.min(...xs), d = Math.max(...zs) - Math.min(...zs), h = this.scene.room.height_m
    const radius = 0.5 * Math.hypot(w, h, d)
    const vfov = (this.persp.fov * Math.PI) / 180
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.persp.aspect)
    const dist = (radius / Math.sin(Math.min(vfov, hfov) / 2)) * 1.08
    const dir = new THREE.Vector3(0.55, 0.75, 1.25).normalize()
    this.controls.target.set(cx, h * 0.35, cz)
    this.persp.position.set(cx + dir.x * dist, h * 0.35 + dir.y * dist, cz + dir.z * dist)
    this.ortho.position.set(cx, 20, cz)
    this.ortho.lookAt(cx, 0, cz)
    this.ortho.up.set(0, 0, -1)
    this.ortho.lookAt(cx, 0, cz)
    this.controls.update()
    this.fitOrtho(this.persp.aspect)
  }

  setMode(mode: ViewMode) {
    if (mode === this.mode) return
    this.mode = mode
    if (mode === 'plan') {
      this.camera = this.ortho
      this.controls.enabled = false
      this.renderer.shadowMap.enabled = false
      if (this.room) this.room.planLines.visible = true
      this.frameOrtho()
    } else {
      this.camera = this.persp
      this.controls.enabled = true
      this.renderer.shadowMap.enabled = true
      if (this.room) this.room.planLines.visible = false
      for (const list of this.room?.wallMeshes.values() || []) for (const m of list) (m.material as THREE.MeshStandardMaterial).opacity = 1
    }
    this.cb.onViewChange?.(mode)
    this.render()
  }

  private frameOrtho() {
    if (!this.scene) return
    const xs = this.scene.room.vertices.map(v => v.x), zs = this.scene.room.vertices.map(v => v.z)
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cz = (Math.min(...zs) + Math.max(...zs)) / 2
    this.ortho.position.set(cx, 20, cz)
    this.ortho.up.set(0, 0, -1)
    this.ortho.lookAt(cx, 0, cz)
    this.orthoZoom = 1
    this.fitOrtho(this.persp.aspect)
  }

  /** Screen position (CSS px within the canvas) of an object's centre top. */
  screenPosition(id: string): { x: number; y: number } | null {
    const v = this.objects.get(id)
    if (!v) return null
    const p = new THREE.Vector3(v.group.position.x, v.group.position.y + v.obj.dimensions_m[1] / 2, v.group.position.z)
    p.project(this.camera)
    const r = this.renderer.domElement.getBoundingClientRect()
    return { x: r.left + (p.x + 1) / 2 * r.width, y: r.top + (1 - p.y) / 2 * r.height }
  }

  focus(id: string) {
    const v = this.objects.get(id)
    if (!v) return
    const p = v.group.position
    if (this.mode === '3d') {
      const to = new THREE.Vector3(p.x, v.obj.dimensions_m[1] / 2, p.z)
      const offset = this.persp.position.clone().sub(this.controls.target)
      this.controls.target.copy(to)
      this.persp.position.copy(to.clone().add(offset.setLength(Math.max(2.5, offset.length() * 0.7))))
      this.controls.update()
    }
    this.flash([id])
  }

  private fadeWalls() {
    if (!this.room || !this.scene || this.mode !== '3d') return
    const cam = this.persp.position
    const vm = new Map(this.scene.room.vertices.map(v => [v.id, v]))
    for (const wall of this.scene.room.walls) {
      const a = vm.get(wall.a)!, b = vm.get(wall.b)!
      const dx = b.x - a.x, dz = b.z - a.z
      const L = Math.hypot(dx, dz) || 1
      const n = [-dz / L, dx / L]
      const side = (cam.x - a.x) * n[0] + (cam.z - a.z) * n[1]
      // camera on the outside of this wall (side < 0) -> fade so you can see in
      const target = side < 0 ? 0.12 : 1
      for (const m of this.room.wallMeshes.get(wall.id) || []) {
        const mat = m.material as THREE.MeshStandardMaterial
        mat.opacity += (target - mat.opacity) * 0.25
        mat.depthWrite = mat.opacity > 0.5
        m.castShadow = mat.opacity > 0.5
      }
    }
  }

  // ------------------------------------------------------------ selection

  select(id: string | null, notify = true) {
    if (this.selected === id) return
    const prev = this.selected
    this.selected = id
    if (prev) this.applyHighlight(prev)
    if (id) this.applyHighlight(id)
    if (notify) this.cb.onSelect?.(id)
  }
  get selectedId() { return this.selected }

  private applyHighlight(id: string) {
    const v = this.objects.get(id)
    if (!v) return
    if (this.flashing.has(id)) return v.setHighlight('flash', this.theme)
    if (this.drag?.id === id && this.drag.bad) return v.setHighlight('bad', this.theme)
    if (id === this.selected) return v.setHighlight('selected', this.theme)
    if (id === this.hovered) return v.setHighlight('hover', this.theme)
    v.setHighlight('none', this.theme)
  }

  // ------------------------------------------------------------ picking

  private setPointer(e: PointerEvent | MouseEvent) {
    const r = this.renderer.domElement.getBoundingClientRect()
    this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
    this.raycaster.setFromCamera(this.pointer, this.camera)
  }

  private pick(): { objectId?: string; wallId?: string; openingId?: string; point: THREE.Vector3 } | null {
    const meshes: THREE.Object3D[] = []
    for (const v of this.objects.values()) meshes.push(v.mesh)
    if (this.room) { for (const m of this.room.openingMeshes.values()) meshes.push(m); for (const l of this.room.wallMeshes.values()) meshes.push(...l); meshes.push(this.room.floor) }
    const hits = this.raycaster.intersectObjects(meshes, false)
    for (const h of hits) {
      const u = h.object.userData
      if (u.objectId) return { objectId: u.objectId, point: h.point }
      if (u.openingId) return { openingId: u.openingId, point: h.point }
      if (u.wallId) {
        const mat = (h.object as THREE.Mesh).material as THREE.MeshStandardMaterial
        if (mat.opacity < 0.5) continue // see through faded walls
        return { wallId: u.wallId, point: h.point }
      }
      if (u.floor) return { point: h.point }
    }
    return null
  }

  private onPointerDown = (e: PointerEvent) => {
    this.renderer.domElement.focus()
    if (e.button !== 0) return
    this.setPointer(e)
    const hit = this.pick()
    if (hit?.objectId) {
      const v = this.objects.get(hit.objectId)!
      this.select(hit.objectId)
      this.cb.onSelectOpening?.(null)
      if (v.obj.locked) return
      const y = v.group.position.y
      const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -y)
      const p = new THREE.Vector3()
      this.raycaster.ray.intersectPlane(plane, p)
      this.drag = { id: hit.objectId, plane, offset: p.clone().sub(v.group.position), startPos: v.group.position.clone(), startYaw: v.group.rotation.y, yaw: v.group.rotation.y, moved: false, bad: false }
      this.controls.enabled = false
      ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
      this.cb.onDragState?.(true, null, false)
      return
    }
    if (hit?.openingId) { this.select(null); this.cb.onSelectOpening?.(hit.openingId); return }
    if (hit?.wallId) { this.select(null); this.cb.onSelectOpening?.(null); this.cb.onSelectWall?.(hit.wallId); return }
    if (this.mode === 'plan' && !hit) return
    this.select(null)
    this.cb.onSelectOpening?.(null)
    this.cb.onSelectWall?.(null)
  }

  private onPointerMove = (e: PointerEvent) => {
    this.setPointer(e)
    if (this.drag && this.scene) {
      const v = this.objects.get(this.drag.id)
      if (!v) return
      const p = new THREE.Vector3()
      if (!this.raycaster.ray.intersectPlane(this.drag.plane, p)) return
      const raw: P = [p.x - this.drag.offset.x, p.z - this.drag.offset.z]
      const snap = e.altKey ? { centre: raw, yaw: this.drag.yaw, snapped: null } : snapObject(this.scene, v.obj, raw, this.drag.yaw, this.alignToWall && !e.shiftKey, this.scene.objects)
      v.group.position.set(snap.centre[0], v.group.position.y, snap.centre[1])
      v.group.rotation.y = snap.yaw
      v.target = { x: snap.centre[0], y: v.group.position.y, z: snap.centre[1], yaw: snap.yaw }
      this.drag.yaw = snap.yaw
      this.drag.moved = true
      const bad = overlapsAny(this.scene, v.obj, snap.centre, snap.yaw)
      this.drag.bad = bad.length > 0
      this.applyHighlight(this.drag.id)
      this.cb.onDragState?.(true, snap.snapped, this.drag.bad)
      return
    }
    const hit = this.pick()
    const id = hit?.objectId || null
    if (id !== this.hovered) {
      const prev = this.hovered
      this.hovered = id
      if (prev) this.applyHighlight(prev)
      if (id) this.applyHighlight(id)
      this.renderer.domElement.style.cursor = id ? 'grab' : hit?.openingId || hit?.wallId ? 'pointer' : ''
      this.cb.onHover?.(id)
    }
  }

  private onPointerUp = (e: PointerEvent) => {
    if (!this.drag) return
    const d = this.drag
    this.drag = null
    this.controls.enabled = this.mode === '3d'
    ;(e.target as HTMLElement).releasePointerCapture?.(e.pointerId)
    const v = this.objects.get(d.id)
    this.cb.onDragState?.(false, null, false)
    if (!v) return
    this.applyHighlight(d.id)
    if (d.moved && (v.group.position.distanceTo(d.startPos) > 1e-4 || Math.abs(d.yaw - d.startYaw) > 1e-4)) {
      const p = v.group.position
      this.cb.onMove?.(d.id, [round(p.x), round(p.y), round(p.z)], normalizeYaw(d.yaw))
    }
  }

  private onDblClick = (e: MouseEvent) => {
    this.setPointer(e)
    const hit = this.pick()
    if (hit?.objectId) this.focus(hit.objectId)
  }

  private onKeyDown = (e: KeyboardEvent) => {
    const mod = e.metaKey || e.ctrlKey
    const id = this.selected
    if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? this.cb.onRedo?.() : this.cb.onUndo?.(); return }
    if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); this.cb.onRedo?.(); return }
    if (mod && e.key.toLowerCase() === 'd' && id) { e.preventDefault(); this.cb.onDuplicate?.(id); return }
    if ((e.key === 'Delete' || e.key === 'Backspace') && id) { e.preventDefault(); this.cb.onDelete?.(id); return }
    if (e.key.toLowerCase() === 'r' && id && !mod) {
      e.preventDefault()
      const v = this.objects.get(id)
      if (!v || v.obj.locked) return
      const step = Math.PI / 12 * (e.shiftKey ? -1 : 1)
      const yaw = normalizeYaw(v.target.yaw + step)
      v.target.yaw = yaw
      this.cb.onRotate?.(id, yaw)
      return
    }
    if (e.key.toLowerCase() === 'v' && !mod) { e.preventDefault(); this.setMode(this.mode === '3d' ? 'plan' : '3d'); return }
    if (e.key.toLowerCase() === 'f' && !mod) { e.preventDefault(); if (id) this.focus(id); else this.frameRoom(); return }
    if (e.key === 'Escape') { this.select(null); this.cb.onSelectOpening?.(null); this.cb.onSelectWall?.(null); return }
    if (this.mode === 'plan' && (e.key === '+' || e.key === '=' || e.key === '-')) {
      this.orthoZoom = Math.max(0.5, Math.min(4, this.orthoZoom * (e.key === '-' ? 0.85 : 1.18)))
      this.fitOrtho(this.persp.aspect)
    }
    if (id && !mod && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
      e.preventDefault()
      const v = this.objects.get(id)
      if (!v || v.obj.locked) return
      const s = e.shiftKey ? 0.25 : 0.05
      const dx = e.key === 'ArrowLeft' ? -s : e.key === 'ArrowRight' ? s : 0
      const dz = e.key === 'ArrowUp' ? -s : e.key === 'ArrowDown' ? s : 0
      const p = v.target
      this.cb.onMove?.(id, [round(p.x + dx), round(p.y), round(p.z + dz)], p.yaw)
    }
  }
}

const round = (v: number) => Math.round(v * 1000) / 1000
