// Procedural stand-ins: a dozen shape families built from the object's measured
// size, so a bed reads as a bed and a sofa as a sofa without any model files.
// Every family fills the box [-w/2, w/2] × [0, h] × [-d/2, d/2]; front = -Z.
// Unknown categories stay a plain box (or cylinder).

import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import type { SceneObject } from '../types'

export interface ShapeParts { group: THREE.Group; meshes: THREE.Mesh[] }

type Mat = THREE.MeshStandardMaterial

function mat(color: THREE.Color | string, rough = 0.85, metal = 0): Mat {
  return new THREE.MeshStandardMaterial({ color: new THREE.Color(color as any), roughness: rough, metalness: metal, transparent: true, opacity: 1 })
}
/** A lampshade: its own colour, lit from inside. */
function glow(color: string, towardsCream = 0.5): Mat {
  const m = mat(new THREE.Color(color).lerp(new THREE.Color('#fff3d6'), towardsCream), 0.9)
  const k = 0.2 + towardsCream * 0.7 // a coloured shade keeps its colour; a cream one glows
  m.emissive = new THREE.Color('#ffd9a0'); m.emissiveIntensity = k
  m.userData.glow = { color: '#ffd9a0', k }
  return m
}
function shade(c: THREE.Color, k: number) { const o = c.clone(); o.offsetHSL(0, 0, k); return o }

const WOOD = '#7a5a3a', DARK = '#2a2a2e', METAL = '#8d9196', WHITE = '#f3f1ec', GLASS = '#9fb6c9'

export function familyOf(category: string, name = ''): string {
  const c = category.toLowerCase(), n = name.toLowerCase()
  if (c.startsWith('bed') || c === 'crib') return 'bed'
  if (c === 'sofa' || c === 'loveseat' || c === 'armchair' || c === 'ottoman' || c === 'bench') return c === 'ottoman' || c === 'bench' ? 'ottoman' : 'sofa'
  if (c === 'chair' || c === 'stool') return 'chair'
  if (c.startsWith('table') || c === 'desk' || c === 'nightstand' || c === 'counter') return c === 'nightstand' ? 'drawers' : 'table'
  if (c === 'bookshelf' || c === 'shelf') return 'shelves'
  if (c === 'wardrobe' || c === 'cabinet' || c === 'dresser' || c === 'sideboard' || c === 'tv_stand' || c === 'fridge' || c === 'washing_machine' || c === 'oven') return c === 'wardrobe' || c === 'cabinet' || c === 'fridge' ? 'doors' : 'drawers'
  if (c === 'lamp_floor' || c === 'lamp_table') return 'lamp'
  if (c === 'lamp_ceiling' || (c === 'other' && /ceiling|pendant|chandelier/.test(n))) return /fan/.test(n) ? 'fan' : 'pendant'
  if (c === 'plant') return 'plant'
  if (c === 'tv') return 'tv'
  if (c === 'mirror' || c === 'picture') return 'panel'
  if (c === 'rug') return 'rug'
  if (c === 'bathtub') return 'tub'
  if (c === 'toilet') return 'toilet'
  if (c === 'sink' || c === 'shower') return 'box'
  if (c === 'piano') return 'piano'
  return 'box'
}

/** A box with softened edges. `soft` is the edge radius in metres (capped to the box). */
function box(w: number, h: number, d: number, m: Mat, x = 0, y = 0, z = 0, soft = 0.012): THREE.Mesh {
  const r = Math.max(0, Math.min(soft, Math.min(w, h, d) * 0.45))
  const g = r > 0.002 ? new RoundedBoxGeometry(w, h, d, 3, r) : new THREE.BoxGeometry(w, h, d)
  const mesh = new THREE.Mesh(g, m)
  mesh.position.set(x, y + h / 2, z)
  return mesh
}
function cyl(r: number, h: number, m: Mat, x = 0, y = 0, z = 0, rTop = r, seg = 24): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(rTop, r, h, seg), m)
  mesh.position.set(x, y + h / 2, z)
  return mesh
}
function legs(w: number, d: number, h: number, m: Mat, inset = 0.05, t = 0.05): THREE.Mesh[] {
  const out: THREE.Mesh[] = []
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) out.push(box(t, h, t, m, sx * (w / 2 - inset - t / 2), 0, sz * (d / 2 - inset - t / 2)))
  return out
}

/** What a product's own name says about how it looks. Cues only: the size is always the measured one. */
export interface Look {
  count: number | null        // "6-tier", "3-drawer", "9 cube"
  round: boolean
  glass: boolean
  legs: 'metal' | 'brass' | 'wood' | null
  wood: string | null          // a wood tone named in the title
  soft: boolean                // upholstered, velvet, linen, bouclé
  leather: boolean
  words: string
}
const WOODS: Record<string, string> = { 'dark walnut': '#4f3524', walnut: '#6b4a32', espresso: '#3b2a20', mahogany: '#5a2e22', 'light oak': '#d3b88c', oak: '#c2a06b', pine: '#d9bd8a', birch: '#dcc9a3', bamboo: '#c9a86a', rattan: '#c2a06b', teak: '#9a6b3f', acacia: '#8a5a36', ash: '#d6c6a5' }

export function lookOf(obj: SceneObject): Look {
  const words = `${obj.name} ${obj.product?.title || ''}`.toLowerCase()
  const n = words.match(/(\d{1,2})\s*[- ]?\s*(?:tier|tiers|shelf|shelves|drawer|drawers|cube|cubes|door|doors)\b/)
  const wood = Object.keys(WOODS).sort((a, b) => b.length - a.length).find(k => words.includes(k)) || null
  return {
    count: n ? Math.max(1, Math.min(12, parseInt(n[1], 10))) : null,
    round: /\b(round|circular|oval|drum)\b/.test(words),
    glass: /\bglass\b/.test(words),
    legs: /\b(brass|gold)\b/.test(words) ? 'brass' : /\b(metal|steel|iron|hairpin|chrome|black legs|industrial)\b/.test(words) ? 'metal' : /\b(wood(en)? legs|mid[- ]century|tapered|splayed)\b/.test(words) ? 'wood' : null,
    wood: wood ? WOODS[wood] : null,
    soft: /\b(upholster\w*|velvet|linen|boucl[eé]|fabric|tufted|chenille|woven|plush)\b/.test(words),
    leather: /\bleather\b/.test(words),
    words,
  }
}

/** Four legs that lean outward a little and taper: the mid-century look. */
function splayedLegs(w: number, d: number, h: number, m: Mat, inset = 0.07): THREE.Mesh[] {
  const out: THREE.Mesh[] = []
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    const leg = cyl(0.014, h * 1.03, m, sx * (w / 2 - inset), 0, sz * (d / 2 - inset), 0.024, 10)
    leg.rotation.z = -sx * 0.12; leg.rotation.x = sz * 0.12
    out.push(leg)
  }
  return out
}

export function buildShape(obj: SceneObject): ShapeParts {
  const [w, h, d] = obj.dimensions_m
  const base = new THREE.Color(obj.color || '#9aa0a6')
  const main = mat(base)
  const group = new THREE.Group()
  const parts: THREE.Mesh[] = []
  const add = (...ms: THREE.Mesh[]) => { for (const m of ms) { parts.push(m); group.add(m) } }
  const fam = familyOf(obj.category, obj.name)
  const look = lookOf(obj)
  const legMat = () => look.legs === 'brass' ? mat('#b08d4c', 0.35, 0.8) : look.legs === 'metal' ? mat(DARK, 0.45, 0.6) : mat(look.wood || shade(base, -0.12), 0.7)
  if (look.soft) main.roughness = 1
  if (look.leather) main.roughness = 0.45

  switch (fam) {
    case 'bed': {
      const frameH = Math.min(0.35, h * 0.45), mattH = Math.max(0.12, Math.min(0.3, h - frameH))
      const wood = mat(look.legs === 'metal' ? DARK : look.wood || (obj.product ? base : new THREE.Color(WOOD)), look.legs === 'metal' ? 0.45 : 0.8, look.legs === 'metal' ? 0.5 : 0)
      add(box(w, frameH, d, wood))                                   // platform
      add(box(w - 0.06, mattH, d - 0.06, mat(WHITE, 0.95), 0, frameH, 0, 0.06)) // mattress
      // a duvet over the foot two thirds, in a soft tint of the piece's colour
      const duvet = shade(base.clone().lerp(new THREE.Color('#e9e4da'), 0.55), 0.02)
      add(box(w - 0.02, mattH * 0.55 + 0.03, d * 0.64, mat(duvet, 1), 0, frameH + mattH * 0.5, -d / 2 + d * 0.32 + 0.01, 0.05))
      const pillowW = Math.min(0.6, w * 0.4), pillowD = Math.min(0.4, d * 0.2)
      const py = frameH + mattH
      const n = w > 1.1 ? 2 : 1
      for (let i = 0; i < n; i++) {
        const px = n === 1 ? 0 : (i === 0 ? -1 : 1) * (pillowW / 2 + 0.04)
        add(box(pillowW, 0.13, pillowD, mat(WHITE, 0.9), px, py - 0.02, d / 2 - pillowD / 2 - 0.08, 0.055))
      }
      if (h > 0.5) {
        // an upholstered headboard is padded and in the piece's own colour; otherwise it matches the frame
        const padded = look.soft || (/headboard/.test(look.words) && !look.wood)
        add(box(w, Math.min(h, 1.3) - frameH, padded ? 0.09 : 0.06, padded ? mat(shade(base, 0.02), 1) : wood, 0, frameH, d / 2 - (padded ? 0.045 : 0.03), padded ? 0.05 : 0.025))
      }
      if (/canopy|four[- ]poster/.test(look.words)) for (const sx of [-1, 1]) for (const sz of [-1, 1]) add(box(0.05, Math.max(h, 1.9), 0.05, wood, sx * (w / 2 - 0.025), 0, sz * (d / 2 - 0.025)))
      break
    }
    case 'sofa':
    case 'ottoman': {
      const armW = fam === 'sofa' && w > 1.0 && !/armless/.test(look.words) ? Math.min(0.2, w * 0.1) : 0
      const legH = Math.min(0.12, h * 0.15), seatH = Math.min(h * 0.5, 0.45) - legH
      const backD = fam === 'sofa' ? Math.min(0.25, d * 0.3) : 0
      add(...(look.legs === 'wood' ? splayedLegs(w, d, legH, legMat(), 0.08) : legs(w, d, legH, look.legs ? legMat() : mat(DARK), 0.04, 0.04)))
      add(box(w - 2 * armW, seatH, d, main, 0, legH))                           // base
      if (fam === 'sofa' && /sectional|chaise|l[- ]shaped/.test(look.words)) add(box(Math.min(0.9, w * 0.4), seatH + 0.12, d * 0.55, main, w / 2 - armW - Math.min(0.9, w * 0.4) / 2, legH, -d / 2 - d * 0.27, 0.05)) // the chaise runs forward
      const cushions = w > 1.6 ? 3 : w > 1.0 ? 2 : 1
      const cw = (w - 2 * armW) / cushions
      for (let i = 0; i < cushions; i++) add(box(cw - 0.03, 0.14, d - backD - 0.06, mat(shade(base, 0.06), 0.95), -w / 2 + armW + cw * (i + 0.5), legH + seatH, -backD / 2, 0.05))
      if (backD) add(box(w - 2 * armW, h - legH - seatH, backD, mat(shade(base, 0.03)), 0, legH + seatH, d / 2 - backD / 2, 0.06))
      if (armW) for (const s of [-1, 1]) add(box(armW, h * 0.8 - legH, d, mat(shade(base, -0.03)), s * (w / 2 - armW / 2), legH, 0, 0.06))
      break
    }
    case 'chair': {
      const seatH = Math.min(0.48, h * 0.45), seatT = 0.07
      const sw = Math.min(w, 0.52), sd = Math.min(d, 0.5)
      if (/office|desk chair|ergonomic|task|swivel|gaming/i.test(obj.name)) {
        // a swivel chair: five-star base, gas lift, padded seat, tall curved-looking back, armrests
        const metal = mat(DARK, 0.5, 0.4)
        for (let i = 0; i < 5; i++) {
          const spoke = box(Math.min(w, d) * 0.46, 0.03, 0.045, metal, Math.min(w, d) * 0.23, 0.04, 0, 0.012)
          const pivot = new THREE.Group(); pivot.rotation.y = (i * 2 * Math.PI) / 5; pivot.add(spoke); group.add(pivot); parts.push(spoke)
        }
        add(cyl(0.03, seatH - seatT - 0.06, mat(METAL, 0.35, 0.8), 0, 0.06))
        add(box(sw, seatT, sd, main, 0, seatH - seatT, -0.02, 0.035))
        const backH = Math.max(0.3, h - seatH - 0.06)
        const back = box(sw * 0.92, backH, 0.07, mat(shade(base, -0.04)), 0, seatH + 0.04, sd / 2 - 0.02, 0.035)
        back.rotation.x = 0.1 // leaning back a little
        add(back)
        for (const s of [-1, 1]) add(box(0.05, 0.03, sd * 0.55, metal, s * (sw / 2 + 0.01), seatH + 0.17, 0, 0.012), box(0.03, 0.17, 0.03, metal, s * (sw / 2 + 0.01), seatH, 0.06, 0.01))
      } else if (/\b(stool|backless)\b/.test(look.words) || obj.category === 'stool') {
        add(...(look.legs === 'wood' ? splayedLegs(sw, sd, h - seatT, legMat(), 0.05) : legs(sw, sd, h - seatT, legMat(), 0.02, 0.03)))
        add(look.round ? cyl(Math.min(sw, sd) / 2, seatT, main, 0, h - seatT, 0, Math.min(sw, sd) / 2, 28) : box(sw, seatT, sd, main, 0, h - seatT, 0, 0.03))
        if (h > 0.6) add(box(sw * 0.8, 0.02, 0.02, legMat(), 0, h * 0.3, -sd / 2 + 0.03), box(sw * 0.8, 0.02, 0.02, legMat(), 0, h * 0.3, sd / 2 - 0.03))
        break
      } else {
        add(...(look.legs === 'wood' || look.wood ? splayedLegs(sw, sd, seatH - seatT, legMat(), 0.05) : legs(sw, sd, seatH - seatT, look.legs ? legMat() : mat(DARK), 0.02, 0.035)))
        add(box(sw, seatT, sd, main, 0, seatH - seatT, 0, 0.03))
        const back = box(sw, h - seatH - 0.02, 0.045, mat(shade(base, -0.05)), 0, seatH + 0.02, sd / 2 - 0.022, 0.02)
        back.rotation.x = 0.07
        add(back)
      }
      break
    }
    case 'table': {
      const topT = look.glass ? 0.015 : 0.04, legH = h - topT
      const top = look.glass ? mat(GLASS, 0.08, 0.1) : mat(look.wood || obj.color || WOOD, 0.7)
      if (look.glass) top.userData.keepOpacity = 0.45
      const legM = look.legs ? legMat() : mat(obj.category === 'desk' ? DARK : shade(new THREE.Color(look.wood || obj.color || WOOD), -0.1))
      const r = Math.min(w, d) / 2
      if (look.round || obj.shape === 'cylinder') {
        const disc = cyl(r, topT, top, 0, legH, 0, r, 40)
        disc.scale.set(w / (2 * r), 1, d / (2 * r)) // an oval when the footprint is not square
        add(disc)
        if (r < 0.32 || /pedestal|tulip/.test(look.words)) add(cyl(0.03, legH, legM), cyl(r * 0.55, 0.025, legM, 0, 0, 0, r * 0.2))
        else {
          const n = 3 + (r > 0.45 ? 1 : 0)
          for (let i = 0; i < n; i++) {
            const ang = (i * 2 * Math.PI) / n + Math.PI / 4
            const leg = cyl(0.016, legH * 1.02, legM, Math.cos(ang) * (w / 2) * 0.72, 0, Math.sin(ang) * (d / 2) * 0.72, 0.022, 10)
            leg.rotation.z = -Math.cos(ang) * 0.1; leg.rotation.x = Math.sin(ang) * 0.1
            add(leg)
          }
        }
        if (/nesting/.test(look.words)) add(cyl(r * 0.62, topT, top, w * 0.3, legH * 0.72, d * 0.25, r * 0.62, 32), cyl(0.02, legH * 0.72, legM, w * 0.3, 0, d * 0.25))
      } else {
        add(box(w, topT, d, top, 0, legH))
        add(...(look.legs === 'wood' ? splayedLegs(w, d, legH, legM) : legs(w, d, legH, legM, 0.04, look.legs === 'metal' || look.legs === 'brass' ? 0.03 : 0.05)))
        if (/drawer/.test(look.words) && h > 0.5) add(box(Math.min(w * 0.45, 0.6), 0.11, d - 0.08, mat(shade(new THREE.Color(look.wood || obj.color || WOOD), -0.06), 0.7), obj.category === 'desk' ? w / 2 - Math.min(w * 0.45, 0.6) / 2 - 0.05 : 0, legH - 0.11))
        if (/shelf|storage/.test(look.words) && h < 0.6) add(box(w - 0.12, 0.02, d - 0.12, top, 0, legH * 0.3))
      }
      break
    }
    case 'drawers':
    case 'doors': {
      // raised on legs when the name says so (mid-century, metal legs); the body sits above them
      const lift = look.legs && h > 0.4 ? Math.min(0.16, h * 0.22) : 0
      if (lift) add(...(look.legs === 'wood' ? splayedLegs(w, d, lift, legMat(), 0.08) : legs(w, d, lift, legMat(), 0.04, 0.03)))
      const bodyH = h - lift
      add(box(w, bodyH, d, look.wood ? mat(look.wood, 0.7) : main, 0, lift))
      const face = mat(shade(look.wood ? new THREE.Color(look.wood) : base, -0.08))
      const panelD = 0.012
      const pull = mat(look.legs === 'brass' ? '#b08d4c' : METAL, 0.4, 0.6)
      if (fam === 'drawers') {
        // "6-drawer" on a wide chest is two columns of three; on a narrow one, a stack
        const total = look.count && /drawer/.test(look.words) ? look.count : Math.max(1, Math.min(4, Math.round(bodyH / 0.3)))
        const cols = w > 1.0 && total >= 4 && total % 2 === 0 ? 2 : 1
        const rows = Math.max(1, Math.round(total / cols))
        const open = /open shelf|with shelf|open storage/.test(look.words) ? 1 : 0 // a nightstand with an open cubby under its drawer
        for (let c = 0; c < cols; c++) for (let i = 0; i < rows; i++) {
          const rh = bodyH / (rows + open), cw = w / cols, cx = -w / 2 + cw * (c + 0.5)
          add(box(cw - 0.06, rh - 0.04, panelD, face, cx, lift + (i + open) * rh + 0.02, -d / 2 - panelD / 2 + 0.002))
          add(box(Math.min(0.24, cw * 0.3), 0.02, 0.02, pull, cx, lift + (i + open) * rh + rh / 2, -d / 2 - 0.02))
        }
        if (open) add(box(w - 0.06, bodyH / (rows + 1) - 0.05, 0.02, mat(shade(base, -0.3)), 0, lift + 0.03, -d / 2 + 0.012))
      } else {
        const cols = look.count && /door/.test(look.words) ? Math.min(4, look.count) : w > 0.9 ? 2 : 1
        for (let i = 0; i < cols; i++) {
          const cw = w / cols
          add(box(cw - 0.05, bodyH - 0.06, panelD, face, -w / 2 + cw * (i + 0.5), lift + 0.03, -d / 2 - panelD / 2 + 0.002))
          const hx = cols === 1 ? w * 0.35 : (i % 2 === 0 ? cw * 0.4 : -cw * 0.4) + (-w / 2 + cw * (i + 0.5))
          add(box(0.02, Math.min(0.25, bodyH * 0.2), 0.02, pull, hx, lift + bodyH * 0.45, -d / 2 - 0.02))
        }
      }
      break
    }
    case 'shelves': {
      const t = 0.025
      const wood = mat(look.wood || obj.color || WOOD, 0.7)
      const frame = look.legs === 'metal' || look.legs === 'brass' ? legMat() : wood
      const tiers = look.count && /tier|shel/.test(look.words) ? look.count : Math.max(1, Math.round(h / 0.35))
      if (/cube/.test(look.words) && look.count) {
        // a cube organiser: a grid of open boxes
        const cols = Math.max(1, Math.round(Math.sqrt(look.count * (w / h)))), rows = Math.max(1, Math.round(look.count / cols))
        add(box(w, h, 0.012, mat(shade(base, -0.1)), 0, 0, d / 2 - 0.006))
        for (let i = 0; i <= cols; i++) add(box(t, h, d, wood, -w / 2 + (w - t) * (i / cols) + t / 2))
        for (let j = 0; j <= rows; j++) add(box(w, t, d, wood, 0, (h - t) * (j / rows)))
      } else if (/ladder|leaning/.test(look.words)) {
        // a ladder shelf leans back: deep shelves at the bottom, shallow at the top, two slanted rails
        for (const sx of [-1, 1]) { const rail = box(0.03, h * 1.01, 0.03, frame, sx * (w / 2 - 0.015), 0, 0); rail.rotation.x = -Math.atan2(d * 0.75, h); rail.position.z = d * 0.08; add(rail) }
        for (let i = 0; i < tiers; i++) {
          const k = i / Math.max(1, tiers - 1), depth = d * (1 - 0.7 * k)
          add(box(w - 0.04, t, depth, wood, 0, h * 0.9 * k + 0.05, d / 2 - depth / 2))
        }
      } else {
        const open = look.legs === 'metal' || look.legs === 'brass' || /open|etagere|industrial/.test(look.words) // no back or sides, just a frame
        if (open) for (const sx of [-1, 1]) for (const sz of [-1, 1]) add(box(0.022, h, 0.022, frame, sx * (w / 2 - 0.011), 0, sz * (d / 2 - 0.011)))
        else add(box(t, h, d, wood, -w / 2 + t / 2), box(t, h, d, wood, w / 2 - t / 2), box(w, h, 0.01, mat(shade(base, -0.1)), 0, 0, d / 2 - 0.005))
        for (let i = 0; i <= tiers; i++) add(box(w - (open ? 0 : 2 * t), t, d - 0.01, wood, 0, (h - t) * (i / tiers)))
      }
      break
    }
    case 'lamp': {
      const r = Math.min(w, d) / 2
      // a real product is one colour from foot to shade; a generic lamp has a metal stem and a cream shade
      const body = obj.product ? mat(shade(base, -0.04), 0.45, 0.3) : null
      const stem = body || mat(METAL, 0.5, 0.7)
      if (/tripod/.test(look.words)) {
        for (let i = 0; i < 3; i++) { const ang = (i * 2 * Math.PI) / 3; const leg = cyl(0.012, h * 0.78, body || mat(look.wood || WOOD, 0.7), Math.cos(ang) * r * 0.5, 0, Math.sin(ang) * r * 0.5, 0.012, 8); leg.rotation.z = -Math.cos(ang) * 0.16; leg.rotation.x = Math.sin(ang) * 0.16; add(leg) }
        add(cyl(r, h * 0.26, glow(obj.color || '#e9dcb8', obj.product ? 0.25 : 0.5), 0, h * 0.74, 0, r * 0.8))
      } else if (/uplight|torchi|reading|task|arc\b/i.test(obj.name)) {
        // a slim pole with a small cone shade at the top
        add(cyl(r * 0.75, 0.035, body || mat(DARK), 0, 0, 0, r * 0.25), cyl(0.014, h * 0.9, stem, 0, 0.03))
        add(cyl(r * 0.22, h * 0.09, glow(obj.color || '#e9dcb8', obj.product ? 0.12 : 0.5), 0, h * 0.91, 0, r * 0.85))
      } else {
        add(cyl(r * 0.6, 0.03, body || mat(DARK)), cyl(0.015, h * 0.75, stem), cyl(r, h * 0.25, glow(obj.color || '#e9dcb8', obj.product ? 0.2 : 0.5), 0, h * 0.75, 0, r * 0.7))
      }
      break
    }
    case 'pendant': {
      const r = Math.min(w, d) / 2
      add(cyl(0.008, h * 0.4, mat(METAL, 0.5, 0.7), 0, h * 0.6), cyl(r, h * 0.6, main, 0, 0, 0, r * 0.8))
      break
    }
    case 'fan': {
      const r = Math.min(w, d) / 2
      add(cyl(0.015, h * 0.35, mat(DARK), 0, h * 0.65), cyl(0.12, h * 0.25, mat(DARK), 0, h * 0.4), cyl(0.1, 0.05, mat(WHITE, 0.6), 0, h * 0.35))
      for (let i = 0; i < 4; i++) {
        const blade = box(r - 0.12, 0.015, 0.12, mat(shade(base, 0), 0.7), (r - 0.12) / 2 + 0.12, h * 0.45, 0)
        const pivot = new THREE.Group(); pivot.rotation.y = (i * Math.PI) / 2; pivot.add(blade); group.add(pivot); parts.push(blade)
      }
      break
    }
    case 'plant': {
      const r = Math.min(w, d) / 2
      const potH = Math.min(h * 0.35, 0.45)
      add(cyl(r * 0.75, potH, mat('#b8865b', 0.9), 0, 0, 0, r * 0.85))
      const foliage = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 1), mat(obj.color || '#4f7a4a', 0.95))
      foliage.scale.set(r, (h - potH) / 2, r); foliage.position.set(0, potH + (h - potH) / 2, 0)
      parts.push(foliage); group.add(foliage)
      break
    }
    case 'tv': {
      add(box(w, h * 0.92, Math.min(d, 0.05), mat(DARK, 0.4, 0.2), 0, h * 0.08, 0), box(w * 0.4, h * 0.08, d, mat(METAL, 0.5, 0.6)))
      break
    }
    case 'panel': {
      add(box(w, h, Math.min(d, 0.04), obj.category === 'mirror' ? mat(GLASS, 0.1, 0.8) : main), box(w + 0.04, h + 0.04, Math.min(d, 0.04) * 0.5, mat(obj.category === 'mirror' ? METAL : WOOD), 0, -0.02, 0.005))
      break
    }
    case 'tub': {
      add(box(w, h, d, main), box(w - 0.16, h * 0.7, d - 0.16, mat('#dfe6ea', 0.3), 0, h * 0.3))
      break
    }
    case 'toilet': {
      add(box(w, h * 0.5, d * 0.55, main, 0, 0, -d * 0.22), box(w * 0.9, h, d * 0.3, main, 0, 0, d * 0.35))
      break
    }
    case 'piano': {
      add(box(w, h, d, main), box(w * 0.9, 0.05, 0.25, mat(WHITE, 0.6), 0, h * 0.6, -d / 2 + 0.1))
      break
    }
    case 'rug': {
      if (look.round) { const rr = Math.min(w, d) / 2; const disc = cyl(rr, Math.max(h, 0.012), main, 0, 0, 0, rr, 48); disc.scale.set(w / (2 * rr), 1, d / (2 * rr)); add(disc) }
      else add(box(w, Math.max(h, 0.012), d, main, 0, 0, 0, 0.004))
      break
    }
    default: {
      if (obj.shape === 'cylinder') add(cyl(Math.min(w, d) / 2, h, main, 0, 0, 0, Math.min(w, d) / 2, 32))
      else add(box(w, h, d, main))
    }
  }
  for (const m of parts) { m.castShadow = true; m.receiveShadow = true; m.userData.objectId = obj.id }
  return { group, meshes: parts }
}
