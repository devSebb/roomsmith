import React from 'react'
import type { Api } from '../api'
import { Editor, type ViewMode } from '../editor/editor'
import { cm, deg, fmt, rad, wallLength } from '../editor/math'
import type { Theme } from '../editor/three-scene'
import { Store, type State } from '../store'
import type { Issue, Opening, Scene, SceneObject, Wall } from '../types'
import { CSS } from './styles'

export interface AppProps {
  api: Api
  shell: 'desktop' | 'dashboard' | 'dev'
  persist?: { get(k: string): string | null; set(k: string, v: string): void }
  openExternal?: (url: string) => void
  onStateChange?: (s: State) => void
}

const CATEGORIES = ['sofa', 'armchair', 'chair', 'bed_double', 'bed_single', 'nightstand', 'desk', 'table_dining', 'table_coffee', 'table_side', 'bookshelf', 'shelf', 'wardrobe', 'dresser', 'cabinet', 'sideboard', 'tv_stand', 'tv', 'rug', 'plant', 'lamp_floor', 'lamp_table', 'fridge', 'counter', 'washing_machine', 'piano', 'ottoman', 'bench', 'other']
const nice = (c: string) => c.replace(/_/g, ' ')
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

function useStore(store: Store) {
  const [s, setS] = React.useState(store.state)
  React.useEffect(() => store.subscribe(setS), [store])
  return s
}

function readTheme(el: HTMLElement): Theme {
  const cs = getComputedStyle(el)
  const accent = cs.getPropertyValue('--ui-accent').trim() || '#4f8cff'
  const text = cs.color || '#222'
  return { accent, text, muted: text, warn: '#e0a200', bg: cs.backgroundColor || 'transparent' }
}

export function App(props: AppProps) {
  const storeRef = React.useRef<Store | null>(null)
  if (!storeRef.current) storeRef.current = new Store(props.api, props.persist)
  const store = storeRef.current
  const s = useStore(store)
  const rootRef = React.useRef<HTMLDivElement>(null)
  const canvasRef = React.useRef<HTMLDivElement>(null)
  const editorRef = React.useRef<Editor | null>(null)
  const [mode, setMode] = React.useState<ViewMode>('3d')
  const [labels, setLabels] = React.useState(true)
  const [drag, setDrag] = React.useState<{ on: boolean; snapped: string | null; bad: boolean }>({ on: false, snapped: null, bad: false })
  const [tab, setTab] = React.useState<'room' | 'objects' | 'issues' | 'history' | 'add'>('objects')
  const [narrow, setNarrow] = React.useState(false)

  React.useEffect(() => { props.onStateChange?.(s) }, [s])

  // boot + dispose
  React.useEffect(() => { store.boot(); return () => store.dispose() }, [store])

  // editor
  React.useEffect(() => {
    const el = canvasRef.current
    if (!el) return
    const theme = readTheme(rootRef.current || el)
    const ed = new Editor(el, {
      onSelect: id => { store.select(id); if (id) setTab('objects') },
      onMove: (id, p, yaw) => store.moveObject(id, p, yaw),
      onRotate: (id, yaw) => store.rotateObject(id, yaw),
      onDelete: id => store.deleteObject(id),
      onDuplicate: id => store.duplicateObject(id),
      onUndo: () => store.undo(),
      onRedo: () => store.redo(),
      onViewChange: m => setMode(m),
      onSelectOpening: id => { store.selectOpening(id); if (id) setTab('room') },
      onSelectWall: id => { store.selectWall(id); if (id) setTab('room') },
      onDragState: (on, snapped, bad) => setDrag({ on, snapped, bad }),
    }, { theme, showLabels: true })
    editorRef.current = ed
    store.onFlash = ids => ed.flash(ids)
    if (props.shell === 'dev') (window as any).__rs = { editor: ed, store }
    const ro = new ResizeObserver(() => setNarrow((rootRef.current?.clientWidth || 1000) < 640))
    if (rootRef.current) ro.observe(rootRef.current)
    const mo = new MutationObserver(() => ed.setTheme(readTheme(rootRef.current || el)))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme', 'style'] })
    return () => { ro.disconnect(); mo.disconnect(); ed.dispose(); editorRef.current = null }
  }, [])

  React.useEffect(() => { if (s.scene && editorRef.current) editorRef.current.setScene(s.scene, s.issues, true) }, [s.scene, s.issues])
  React.useEffect(() => { editorRef.current?.select(s.selectedId, false) }, [s.selectedId])

  const ed = editorRef.current
  const scene = s.scene
  const realIssues = s.issues.filter(i => i.code !== 'uncalibrated')
  const selected = scene?.objects.find(o => o.id === s.selectedId) || null
  const selectedOpening = scene?.room.openings.find(o => o.id === s.selectedOpeningId) || null

  return (
    <div className={'rs-root' + (narrow ? ' rs-narrow' : '')} ref={rootRef}>
      <style>{CSS}</style>
      <div className="rs-toolbar">
        <ProjectSwitcher store={store} s={s} />
        <button className={'rs-btn sm' + (mode === '3d' ? ' on' : '')} onClick={() => ed?.setMode('3d')} title="3D view (V)">3D</button>
        <button className={'rs-btn sm' + (mode === 'plan' ? ' on' : '')} onClick={() => ed?.setMode('plan')} title="Plan view (V)">Plan</button>
        <button className="rs-btn sm" onClick={() => { if (s.selectedId) ed?.focus(s.selectedId); else ed?.frameRoom() }} title="Frame (F)">⌖</button>
        <button className={'rs-btn sm' + (labels ? ' on' : '')} onClick={() => { setLabels(!labels); ed?.setLabels(!labels) }} title="Labels">Aa</button>
        <span className="rs-spacer" />
        <button className="rs-btn sm" disabled={!s.canUndo} onClick={() => store.undo()} title="Undo (⌘Z)">↶ Undo</button>
        <button className="rs-btn sm" disabled={!s.canRedo} onClick={() => store.redo()} title="Redo (⇧⌘Z)">↷ Redo</button>
        <span className="rs-faint" title="Revision">r{s.revision}</span>
        <span className={'rs-online' + (s.online ? '' : ' off')} title={s.online ? 'Connected' : 'Backend unreachable'} />
      </div>
      <div className="rs-canvas" ref={canvasRef}>
        {drag.on && <div className={'rs-chip' + (drag.bad ? ' bad' : '')}>{drag.bad ? 'Overlaps' : drag.snapped === 'wall' ? 'Against wall' : drag.snapped === 'object' ? 'Aligned' : 'Moving'} · ⇧ free rotate · ⌥ no snap</div>}
        {scene && scene.calibration.status !== 'calibrated' && !drag.on && (
          <div className="rs-draft" title="Give one real measurement to set the scale" onClick={() => setTab('room')}>Draft — estimated sizes · calibrate</div>
        )}
        {!scene && !s.loading && (
          <div className="rs-empty">
            <div style={{ fontSize: 15 }}>No room yet</div>
            <div className="rs-muted">{s.error || 'Create one from measurements or a photo, or ask Hermes: "make a 4 by 5 metre living room".'}</div>
            <NewRoom store={store} api={props.api} compact />
          </div>
        )}
        {scene && <div className="rs-help">drag to move · ⇧drag pan · wheel zoom · R rotate · ⌫ delete · ⌘D duplicate · ⌘Z undo · V view · F frame</div>}
        <div className="rs-toasts">{s.toasts.map(t => <div key={t.id} className={'rs-toast ' + t.kind} onClick={() => t.ids?.[0] && store.select(t.ids[0])}>{t.text}</div>)}</div>
      </div>
      <div className="rs-panel">
        <div className="rs-tabs">
          <button className={tab === 'objects' ? 'on' : ''} onClick={() => setTab('objects')}>Objects{scene ? <span className="rs-count">{scene.objects.length}</span> : null}</button>
          <button className={tab === 'room' ? 'on' : ''} onClick={() => setTab('room')}>Room</button>
          <button className={tab === 'issues' ? 'on' : ''} onClick={() => setTab('issues')}>Issues{realIssues.length ? <span className="rs-count bad">{realIssues.length}</span> : null}</button>
          <button className={tab === 'history' ? 'on' : ''} onClick={() => setTab('history')}>History</button>
          <button className={tab === 'add' ? 'on' : ''} onClick={() => setTab('add')}>Add</button>
        </div>
        <div className="rs-body">
          {!scene && <div className="rs-muted">Open or create a room to start.</div>}
          {scene && tab === 'objects' && (selected ? <ObjectInspector store={store} scene={scene} o={selected} openExternal={props.openExternal} /> : <ObjectList store={store} scene={scene} issues={s.issues} onFocus={id => ed?.focus(id)} />)}
          {scene && tab === 'room' && <RoomPanel store={store} scene={scene} opening={selectedOpening} wallId={s.selectedWallId} api={props.api} openExternal={props.openExternal} />}
          {scene && tab === 'issues' && <IssuesPanel issues={s.issues} scene={scene} onPick={id => { store.select(id); ed?.focus(id); setTab('objects') }} />}
          {scene && tab === 'history' && <HistoryPanel store={store} s={s} />}
          {scene && tab === 'add' && <AddPanel store={store} scene={scene} />}
        </div>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ pieces

function ProjectSwitcher({ store, s }: { store: Store; s: State }) {
  const [creating, setCreating] = React.useState(false)
  return (
    <>
      <select className="rs-sel" style={{ width: 170 }} value={s.projectId || ''} onChange={e => { if (e.target.value === '__new') setCreating(true); else store.switchRoom(e.target.value) }}>
        {!s.projectId && <option value="">No room</option>}
        {s.projects.map(p => <option key={p.project_id} value={p.project_id}>{p.name} · r{p.revision}</option>)}
        <option value="__new">+ New room…</option>
      </select>
      {creating && <NewRoomDialog store={store} onClose={() => setCreating(false)} />}
    </>
  )
}

function NewRoomDialog({ store, onClose }: { store: Store; onClose: () => void }) {
  return (
    <div style={{ position: 'absolute', top: 40, left: 8, zIndex: 20, width: 300, padding: 12, borderRadius: 10, border: '1px solid var(--rs-line)', background: 'color-mix(in srgb, currentColor 6%, Canvas)', boxShadow: '0 10px 30px rgba(0,0,0,.3)' }}>
      <div className="rs-row" style={{ justifyContent: 'space-between', marginBottom: 8 }}><b>New room</b><button className="rs-btn sm" onClick={onClose}>✕</button></div>
      <NewRoom store={store} api={store.api} onDone={onClose} />
    </div>
  )
}

function NewRoom({ store, api, onDone, compact }: { store: Store; api: Api; onDone?: () => void; compact?: boolean }) {
  const [name, setName] = React.useState('Living room')
  const [w, setW] = React.useState('4.0'), [d, setD] = React.useState('5.0'), [h, setH] = React.useState('2.5')
  const [photo, setPhoto] = React.useState<{ id: string; name: string } | null>(null)
  const [busy, setBusy] = React.useState(false)
  const fileRef = React.useRef<HTMLInputElement>(null)
  const importRef = React.useRef<HTMLInputElement>(null)
  const upload = async (f: File) => {
    setBusy(true)
    try {
      const bytes = new Uint8Array(await f.arrayBuffer())
      const r = await api.uploadPhoto(bytes, f.type || 'image/jpeg')
      setPhoto({ id: r.photo_id, name: f.name })
      store.toast('info', `Photo uploaded as ${r.photo_id}. Ask Hermes: "make a room from photo ${r.photo_id}".`)
    } catch (e: any) { store.toast('error', e?.message || 'Upload failed') } finally { setBusy(false) }
  }
  const doImport = async (f: File) => {
    try { const j = JSON.parse(await f.text()); await store.createRoom({ import: j, name: j?.scene?.project?.name || f.name.replace(/\.room\.json$|\.json$/, '') }); onDone?.() } catch (e: any) { store.toast('error', 'Not a Roomsmith file') }
  }
  return (
    <div className="rs-sec" style={{ width: compact ? 280 : undefined, textAlign: 'left' }}>
      <div className="rs-row"><label>Name</label><input className="rs-in" value={name} onChange={e => setName(e.target.value)} /></div>
      <div className="rs-row rs-3"><input className="rs-in" value={w} onChange={e => setW(e.target.value)} placeholder="width m" /><input className="rs-in" value={d} onChange={e => setD(e.target.value)} placeholder="depth m" /><input className="rs-in" value={h} onChange={e => setH(e.target.value)} placeholder="height m" /></div>
      <div className="rs-faint">width × depth × height in metres</div>
      <button className="rs-btn primary" disabled={busy} onClick={async () => { await store.createRoom({ name, width_m: +w, depth_m: +d, height_m: +h }); onDone?.() }}>Create from measurements</button>
      <div className="rs-faint" style={{ marginTop: 4 }}>— or from a photo —</div>
      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) upload(f) }} />
      <button className="rs-btn" disabled={busy} onClick={() => fileRef.current?.click()}>{busy ? 'Uploading…' : 'Upload a photo'}</button>
      {photo && <div className="rs-res">Uploaded as <b>{photo.id}</b>. Now tell Hermes: “make a room from photo {photo.id}” — it will read it and build a draft here.</div>}
      <input ref={importRef} type="file" accept=".json,application/json" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) doImport(f) }} />
      <button className="rs-btn sm" onClick={() => importRef.current?.click()}>Import .room.json</button>
    </div>
  )
}

function ObjectList({ store, scene, issues, onFocus }: { store: Store; scene: Scene; issues: Issue[]; onFocus: (id: string) => void }) {
  const bad = new Set(issues.filter(i => i.code !== 'uncalibrated').flatMap(i => i.ids))
  if (!scene.objects.length) return <div className="rs-muted">No objects yet. Use the Add tab, or ask Hermes: “add a 2 m sofa against the back wall”.</div>
  return (
    <div className="rs-list">
      {scene.objects.map(o => (
        <div key={o.id} className="rs-item" onClick={() => store.select(o.id)} onDoubleClick={() => onFocus(o.id)} title={`${o.id} · double-click to focus`}>
          <span className="rs-sw" style={{ background: o.color }} />
          <span className="rs-name">{o.name}{o.locked ? ' 🔒' : ''}</span>
          {bad.has(o.id) && <span className="rs-badge warn">!</span>}
          <span className="rs-dim">{fmt(o.dimensions_m[0])}×{fmt(o.dimensions_m[2])}</span>
        </div>
      ))}
    </div>
  )
}

function NumField({ label, value, onCommit, step = 0.01, min, max, unit = 'm' }: { label: string; value: number; onCommit: (v: number) => void; step?: number; min?: number; max?: number; unit?: string }) {
  const [txt, setTxt] = React.useState(fmt(value, 3))
  React.useEffect(() => setTxt(fmt(value, 3)), [value])
  const commit = () => { const v = parseFloat(txt.replace(',', '.')); if (Number.isFinite(v) && Math.abs(v - value) > 1e-6) onCommit(v); else setTxt(fmt(value, 3)) }
  return (
    <div className="rs-row"><label>{label}</label><input className="rs-in num" value={txt} step={step} min={min} max={max} onChange={e => setTxt(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }} /><span className="rs-faint">{unit}</span></div>
  )
}

function ObjectInspector({ store, scene, o, openExternal }: { store: Store; scene: Scene; o: SceneObject; openExternal?: (u: string) => void }) {
  const [name, setName] = React.useState(o.name)
  React.useEffect(() => setName(o.name), [o.id, o.name])
  const [calib, setCalib] = React.useState('')
  const setDims = (i: number, v: number) => { const dims = [...o.dimensions_m] as [number, number, number]; dims[i] = v; store.apply([{ op: 'set_dimensions', id: o.id, dimensions_m: dims }], s => { const x = s.objects.find(y => y.id === o.id); if (x) x.dimensions_m = dims }) }
  const setPos = (i: number, v: number) => { const p = [...o.position_m] as [number, number, number]; p[i] = v; store.moveObject(o.id, p, o.yaw_rad) }
  const p = o.product
  const src = o.provenance?.dims_source || 'estimated'
  return (
    <div className="rs-sec">
      <div className="rs-row"><button className="rs-btn sm" onClick={() => store.select(null)}>‹ All</button><span className="rs-faint">{o.id} · {nice(o.category)}</span><span className="rs-spacer" /><span className={'rs-badge' + (src === 'estimated' ? ' warn' : ' ok')}>{src}</span></div>
      <div className="rs-row"><label>Name</label><input className="rs-in" value={name} onChange={e => setName(e.target.value)} onBlur={() => { if (name.trim() && name !== o.name) store.apply([{ op: 'update_object', id: o.id, name: name.trim() }]) }} /></div>
      <h4>Size</h4>
      <NumField label="Width" value={o.dimensions_m[0]} onCommit={v => setDims(0, v)} />
      <NumField label="Height" value={o.dimensions_m[1]} onCommit={v => setDims(1, v)} />
      <NumField label="Depth" value={o.dimensions_m[2]} onCommit={v => setDims(2, v)} />
      <h4>Position</h4>
      <NumField label="X" value={o.position_m[0]} onCommit={v => setPos(0, v)} />
      <NumField label="Z" value={o.position_m[2]} onCommit={v => setPos(2, v)} />
      {(o.mount !== 'floor' || o.position_m[1] > 0) && <NumField label="Y" value={o.position_m[1]} onCommit={v => setPos(1, v)} />}
      <NumField label="Facing" value={deg(o.yaw_rad)} unit="°" step={15} onCommit={v => store.rotateObject(o.id, rad(v))} />
      <div className="rs-row">
        <label>Colour</label>
        <input type="color" className="rs-color" value={o.color} onChange={e => store.apply([{ op: 'update_object', id: o.id, color: e.target.value }], s => { const x = s.objects.find(y => y.id === o.id); if (x) x.color = e.target.value })} />
        <select className="rs-sel" value={o.category} onChange={e => store.apply([{ op: 'update_object', id: o.id, category: e.target.value }])}>{CATEGORIES.map(c => <option key={c} value={c}>{nice(c)}</option>)}</select>
      </div>
      <div className="rs-row">
        <button className={'rs-btn sm' + (o.locked ? ' on' : '')} onClick={() => store.apply([{ op: 'update_object', id: o.id, locked: !o.locked }])}>{o.locked ? '🔒 Locked' : '🔓 Lock'}</button>
        <button className="rs-btn sm" onClick={() => store.duplicateObject(o.id)}>Duplicate</button>
        <button className="rs-btn sm danger" disabled={o.locked} onClick={() => store.deleteObject(o.id)}>Delete</button>
      </div>
      <div className="rs-row">
        <button className="rs-btn sm" onClick={() => store.apply([{ op: 'move_object', id: o.id, place: { against_wall: nearestWall(scene, o), align: 'center' } }])}>Snap to nearest wall</button>
        <button className="rs-btn sm" onClick={() => store.apply([{ op: 'move_object', id: o.id, place: { centered_in_room: true } }])}>Centre</button>
      </div>
      {p && (
        <div className="rs-card">
          {p.image_url ? <img src={p.image_url} alt="" referrerPolicy="no-referrer" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} /> : null}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600 }}>{p.title}</div>
            {p.price && <div className="rs-muted">{p.price}</div>}
            {p.dimensions_text && <div className="rs-faint">{p.dimensions_text}{p.assumed_order ? ' (read as W×D×H)' : ''}</div>}
            {p.url && <a href={p.url} target="_blank" rel="noreferrer" onClick={e => { if (openExternal) { e.preventDefault(); openExternal(p.url!) } }}>Open product page ↗</a>}
          </div>
        </div>
      )}
      {scene.calibration.status !== 'calibrated' && (
        <details className="rs-det"><summary>Calibrate: I know this object's real width</summary>
          <div className="rs-row" style={{ marginTop: 6 }}><input className="rs-in num" placeholder="m" value={calib} onChange={e => setCalib(e.target.value)} /><button className="rs-btn sm primary" onClick={() => { const v = parseFloat(calib); if (v > 0) store.apply([{ op: 'calibrate', reference: { kind: 'object_width', id: o.id, real_m: v } }]) }}>Set scale</button></div>
        </details>
      )}
    </div>
  )
}

function nearestWall(scene: Scene, o: SceneObject): string {
  let best = scene.room.walls[0].id, bd = Infinity
  const vm = new Map(scene.room.vertices.map(v => [v.id, v]))
  for (const w of scene.room.walls) {
    const a = vm.get(w.a)!, b = vm.get(w.b)!
    const ax = a.x, az = a.z, bx = b.x, bz = b.z
    const l2 = (bx - ax) ** 2 + (bz - az) ** 2 || 1
    const t = Math.max(0, Math.min(1, ((o.position_m[0] - ax) * (bx - ax) + (o.position_m[2] - az) * (bz - az)) / l2))
    const d = Math.hypot(o.position_m[0] - (ax + t * (bx - ax)), o.position_m[2] - (az + t * (bz - az)))
    if (d < bd) { bd = d; best = w.id }
  }
  return best
}

function RoomPanel({ store, scene, opening, wallId, api, openExternal }: { store: Store; scene: Scene; opening: Opening | null; wallId: string | null; api: Api; openExternal?: (u: string) => void }) {
  const isRect = scene.room.vertices.length === 4
  const xs = scene.room.vertices.map(v => v.x), zs = scene.room.vertices.map(v => v.z)
  const W = Math.max(...xs) - Math.min(...xs), D = Math.max(...zs) - Math.min(...zs)
  const [name, setName] = React.useState(scene.project.name)
  React.useEffect(() => setName(scene.project.name), [scene.project.name])
  const [calWall, setCalWall] = React.useState(scene.room.walls[0]?.id || 'w1')
  const [calLen, setCalLen] = React.useState('')
  const wall: Wall | undefined = scene.room.walls.find(w => w.id === wallId)
  return (
    <div className="rs-sec">
      <div className="rs-row"><label>Name</label><input className="rs-in" value={name} onChange={e => setName(e.target.value)} onBlur={() => { if (name.trim() && name !== scene.project.name) store.renameRoom(name.trim()) }} /></div>
      <h4>Size {isRect ? '' : '(polygon)'}</h4>
      {isRect && <NumField label="Width" value={W} onCommit={v => store.apply([{ op: 'set_room_rectangle', width_m: v, depth_m: D }])} />}
      {isRect && <NumField label="Depth" value={D} onCommit={v => store.apply([{ op: 'set_room_rectangle', width_m: W, depth_m: v }])} />}
      <NumField label="Height" value={scene.room.height_m} onCommit={v => store.apply([{ op: 'set_room_height', height_m: v }])} />
      <div className="rs-row"><label>Floor</label><input type="color" className="rs-color" value={scene.room.floor.color} onChange={e => store.apply([{ op: 'set_surface_color', surface: 'floor', color: e.target.value }], s => { s.room.floor.color = e.target.value })} />
        <label>Walls</label><input type="color" className="rs-color" value={scene.room.walls[0]?.color || '#f2efe9'} onChange={e => store.apply([{ op: 'set_surface_color', surface: 'walls', color: e.target.value }], s => { s.room.walls.forEach(w => (w.color = e.target.value)) })} /></div>
      <h4>Walls</h4>
      <div className="rs-list">
        {scene.room.walls.map(w => (
          <div key={w.id} className={'rs-item' + (w.id === wallId ? ' on' : '')} onClick={() => store.selectWall(w.id === wallId ? null : w.id)}>
            <span className="rs-sw" style={{ background: w.color }} /><span className="rs-name">{w.id} {w.label}</span><span className="rs-dim">{fmt(wallLength(scene, w))} m</span>
          </div>
        ))}
      </div>
      {wall && (
        <div className="rs-sec" style={{ paddingLeft: 8, borderLeft: '2px solid var(--rs-line)' }}>
          {isRect && <NumField label="Length" value={wallLength(scene, wall)} onCommit={v => store.apply([{ op: 'set_wall_length', id: wall.id, length_m: v }])} />}
          <div className="rs-row"><label>Colour</label><input type="color" className="rs-color" value={wall.color} onChange={e => store.apply([{ op: 'set_surface_color', surface: wall.id, color: e.target.value }])} /></div>
          <div className="rs-row">
            <button className="rs-btn sm" onClick={() => store.apply([{ op: 'add_opening', wall_id: wall.id, kind: 'door', width_m: 0.9 }])}>+ Door</button>
            <button className="rs-btn sm" onClick={() => store.apply([{ op: 'add_opening', wall_id: wall.id, kind: 'window', width_m: 1.2 }])}>+ Window</button>
          </div>
        </div>
      )}
      <h4>Openings</h4>
      {scene.room.openings.length === 0 && <div className="rs-faint">None. Select a wall to add a door or window.</div>}
      <div className="rs-list">
        {scene.room.openings.map(o => (
          <div key={o.id} className={'rs-item' + (opening?.id === o.id ? ' on' : '')} onClick={() => store.selectOpening(opening?.id === o.id ? null : o.id)}>
            <span className="rs-name">{o.kind} {o.id} on {o.wall_id}</span><span className="rs-dim">{fmt(o.width_m)}×{fmt(o.height_m)}</span>
          </div>
        ))}
      </div>
      {opening && <OpeningInspector store={store} scene={scene} o={opening} />}
      <h4>Scale</h4>
      {scene.calibration.status === 'calibrated' ? <div className="rs-badge ok">Calibrated</div> : (
        <div className="rs-sec">
          <div className="rs-faint">Sizes are estimates. Give one real length and everything rescales.</div>
          <div className="rs-row"><select className="rs-sel" value={calWall} onChange={e => setCalWall(e.target.value)}>{scene.room.walls.map(w => <option key={w.id} value={w.id}>{w.id} {w.label}</option>)}</select><input className="rs-in num" placeholder="m" value={calLen} onChange={e => setCalLen(e.target.value)} /><button className="rs-btn sm primary" onClick={() => { const v = parseFloat(calLen); if (v > 0) store.apply([{ op: 'calibrate', reference: { kind: 'wall_length', id: calWall, real_m: v } }]) }}>Set</button></div>
        </div>
      )}
      <h4>Export</h4>
      <div className="rs-row">
        {(['glb', 'json', 'summary'] as const).map(f => (
          <a key={f} className="rs-btn sm" href={api.exportUrl(scene.project.id, f)} download onClick={async e => {
            e.preventDefault()
            const safe = scene.project.name.replace(/[^\w-]+/g, '_')
            if (await api.download(scene.project.id, f, safe)) return
            if (openExternal) openExternal(api.exportUrl(scene.project.id, f))
            else window.open(api.exportUrl(scene.project.id, f), '_blank')
          }}>{f.toUpperCase()}</a>
        ))}
      </div>
      <div className="rs-row"><button className="rs-btn sm danger" onClick={() => { if (confirm(`Delete room "${scene.project.name}"?`)) store.deleteRoom() }}>Delete room</button></div>
    </div>
  )
}

function OpeningInspector({ store, scene, o }: { store: Store; scene: Scene; o: Opening }) {
  const upd = (patch: Record<string, unknown>) => store.apply([{ op: 'update_opening', id: o.id, ...patch }], s => { const x = s.room.openings.find(y => y.id === o.id); if (x) Object.assign(x, patch) })
  return (
    <div className="rs-sec" style={{ paddingLeft: 8, borderLeft: '2px solid var(--rs-line)' }}>
      <div className="rs-row"><label>Kind</label><select className="rs-sel" value={o.kind} onChange={e => upd({ kind: e.target.value })}><option value="door">door</option><option value="window">window</option><option value="opening">opening</option></select></div>
      <div className="rs-row"><label>Wall</label><select className="rs-sel" value={o.wall_id} onChange={e => upd({ wall_id: e.target.value, offset_m: 0 })}>{scene.room.walls.map(w => <option key={w.id} value={w.id}>{w.id} {w.label}</option>)}</select></div>
      <NumField label="Offset" value={o.offset_m} onCommit={v => upd({ offset_m: v })} />
      <NumField label="Width" value={o.width_m} onCommit={v => upd({ width_m: v })} />
      <NumField label="Height" value={o.height_m} onCommit={v => upd({ height_m: v })} />
      {o.kind === 'window' && <NumField label="Sill" value={o.sill_m} onCommit={v => upd({ sill_m: v })} />}
      {o.kind === 'door' && <div className="rs-row"><label>Swing</label><select className="rs-sel" value={o.swing || 'in'} onChange={e => upd({ swing: e.target.value })}><option value="in">in</option><option value="out">out</option><option value="none">none</option></select><select className="rs-sel" value={o.hinge || 'left'} onChange={e => upd({ hinge: e.target.value })}><option value="left">hinge left</option><option value="right">hinge right</option></select></div>}
      <div className="rs-row"><button className="rs-btn sm danger" onClick={() => store.apply([{ op: 'remove_opening', id: o.id }], s => { s.room.openings = s.room.openings.filter(x => x.id !== o.id) })}>Remove</button></div>
    </div>
  )
}

function IssuesPanel({ issues, scene, onPick }: { issues: Issue[]; scene: Scene; onPick: (id: string) => void }) {
  const real = issues.filter(i => i.code !== 'uncalibrated')
  return (
    <div className="rs-sec">
      {real.length === 0 && <div className="rs-badge ok">No issues</div>}
      {issues.map((i, k) => (
        <div key={k} className={'rs-issue' + (i.severity === 'info' ? ' info' : '')} onClick={() => { const id = i.ids.find(x => scene.objects.some(o => o.id === x)); if (id) onPick(id) }}>
          <b>{nice(i.code)}</b> · {i.message}
        </div>
      ))}
    </div>
  )
}

function HistoryPanel({ store, s }: { store: Store; s: State }) {
  return (
    <div className="rs-sec">
      <div className="rs-row"><button className="rs-btn sm" disabled={!s.canUndo} onClick={() => store.undo()}>↶ Undo</button><button className="rs-btn sm" disabled={!s.canRedo} onClick={() => store.redo()}>↷ Redo</button></div>
      <div className="rs-list">
        {s.history.map(r => (
          <div key={r.revision} className={'rs-hist ' + r.actor}><span className="rs-r">r{r.revision}</span><span className="rs-who">{r.actor === 'agent' ? 'Hermes' : r.actor === 'user' ? 'You' : 'System'}</span><span className="rs-grow">{r.summary.replace(/^(Hermes|You|System): /, '')}</span></div>
        ))}
      </div>
    </div>
  )
}

function AddPanel({ store, scene }: { store: Store; scene: Scene }) {
  const [cat, setCat] = React.useState('sofa')
  const [name, setName] = React.useState('')
  const [dims, setDims] = React.useState({ w: '', h: '', d: '' })
  const [prod, setProd] = React.useState({ title: '', dims: '', url: '', price: '' })
  const [fit, setFit] = React.useState({ w: '', h: '', d: '' })
  const [fitRes, setFitRes] = React.useState<string>('')
  const add = () => {
    const op: Record<string, unknown> = { op: 'add_object', name: name.trim() || cap(nice(cat)), category: cat }
    const w = +dims.w, h = +dims.h, d = +dims.d
    if (w > 0 && h > 0 && d > 0) op.dimensions_m = [w, h, d]
    store.apply([op as any]).then(r => { const id = r?.results?.[0]?.created_id; if (id) store.select(id) })
  }
  return (
    <div className="rs-sec">
      <h4>Furniture</h4>
      <div className="rs-row"><select className="rs-sel" value={cat} onChange={e => setCat(e.target.value)}>{CATEGORIES.map(c => <option key={c} value={c}>{nice(c)}</option>)}</select></div>
      <div className="rs-row"><input className="rs-in" placeholder="Name (optional)" value={name} onChange={e => setName(e.target.value)} /></div>
      <div className="rs-row rs-3"><input className="rs-in" placeholder="w" value={dims.w} onChange={e => setDims({ ...dims, w: e.target.value })} /><input className="rs-in" placeholder="h" value={dims.h} onChange={e => setDims({ ...dims, h: e.target.value })} /><input className="rs-in" placeholder="d" value={dims.d} onChange={e => setDims({ ...dims, d: e.target.value })} /></div>
      <div className="rs-faint">Leave sizes empty for a typical size. New objects go to the first free wall.</div>
      <button className="rs-btn primary" onClick={add}>Add {nice(cat)}</button>
      <h4>Product</h4>
      <div className="rs-faint">Paste what the shop page says. Or ask Hermes with the link and it fills this in.</div>
      <div className="rs-row"><input className="rs-in" placeholder="Title" value={prod.title} onChange={e => setProd({ ...prod, title: e.target.value })} /></div>
      <div className="rs-row"><input className="rs-in" placeholder="Dimensions, e.g. W 228 x D 95 x H 83 cm" value={prod.dims} onChange={e => setProd({ ...prod, dims: e.target.value })} /></div>
      <div className="rs-row"><input className="rs-in" placeholder="Link (optional)" value={prod.url} onChange={e => setProd({ ...prod, url: e.target.value })} /><input className="rs-in" style={{ width: 80 }} placeholder="Price" value={prod.price} onChange={e => setProd({ ...prod, price: e.target.value })} /></div>
      <button className="rs-btn" disabled={!prod.title || !prod.dims} onClick={async () => { const r = await store.addProduct({ title: prod.title, dimensions_text: prod.dims, url: prod.url || undefined, price: prod.price || undefined }); if (r?.ok) { setProd({ title: '', dims: '', url: '', price: '' }); const id = r.results?.[0]?.created_id; if (id) store.select(id) } }}>Add at true size</button>
      <h4>Will it fit?</h4>
      <div className="rs-row rs-3"><input className="rs-in" placeholder="w" value={fit.w} onChange={e => setFit({ ...fit, w: e.target.value })} /><input className="rs-in" placeholder="h" value={fit.h} onChange={e => setFit({ ...fit, h: e.target.value })} /><input className="rs-in" placeholder="d" value={fit.d} onChange={e => setFit({ ...fit, d: e.target.value })} /></div>
      <div className="rs-row">
        <button className="rs-btn sm" onClick={async () => { const r = await store.check({ question: 'where_fits', dimensions_m: [+fit.w, +fit.h, +fit.d] }); if (r) setFitRes(r.verdict + (r.candidates?.length ? '\n' + r.candidates.map((c: any) => `• wall ${c.wall_id} ${c.wall_label}: ${cm(Math.min(c.clearance_m.left, c.clearance_m.right))} spare`).join('\n') : '')) }}>Where does it fit?</button>
        <button className="rs-btn sm" onClick={async () => { const r = await store.check({ question: 'passes_door', dimensions_m: [+fit.w, +fit.h, +fit.d] }); if (r) setFitRes(r.verdict) }}>Through the door?</button>
      </div>
      {fitRes && <div className="rs-res">{fitRes}</div>}
    </div>
  )
}
