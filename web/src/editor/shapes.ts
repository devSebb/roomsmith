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
function glow(color: string): Mat {
  const m = mat(new THREE.Color(color).lerp(new THREE.Color('#fff3d6'), 0.5), 0.9)
  m.emissive = new THREE.Color('#ffd9a0'); m.emissiveIntensity = 0.55
  m.userData.glow = { color: '#ffd9a0', k: 0.55 }
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

export function buildShape(obj: SceneObject): ShapeParts {
  const [w, h, d] = obj.dimensions_m
  const base = new THREE.Color(obj.color || '#9aa0a6')
  const main = mat(base)
  const group = new THREE.Group()
  const parts: THREE.Mesh[] = []
  const add = (...ms: THREE.Mesh[]) => { for (const m of ms) { parts.push(m); group.add(m) } }
  const fam = familyOf(obj.category, obj.name)

  switch (fam) {
    case 'bed': {
      const frameH = Math.min(0.35, h * 0.45), mattH = Math.max(0.12, Math.min(0.3, h - frameH))
      const wood = mat(WOOD)
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
      if (h > 0.5) add(box(w, Math.min(h, 1.1) - frameH, 0.06, wood, 0, frameH, d / 2 - 0.03, 0.025)) // headboard at the back (+Z)
      break
    }
    case 'sofa':
    case 'ottoman': {
      const armW = fam === 'sofa' && w > 1.0 ? Math.min(0.2, w * 0.1) : 0
      const legH = Math.min(0.12, h * 0.15), seatH = Math.min(h * 0.5, 0.45) - legH
      const backD = fam === 'sofa' ? Math.min(0.25, d * 0.3) : 0
      add(...legs(w, d, legH, mat(DARK), 0.04, 0.04))
      add(box(w - 2 * armW, seatH, d, main, 0, legH))                           // base
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
      } else {
        add(...legs(sw, sd, seatH - seatT, mat(DARK), 0.02, 0.035))
        add(box(sw, seatT, sd, main, 0, seatH - seatT, 0, 0.03))
        const back = box(sw, h - seatH - 0.02, 0.045, mat(shade(base, -0.05)), 0, seatH + 0.02, sd / 2 - 0.022, 0.02)
        back.rotation.x = 0.07
        add(back)
      }
      break
    }
    case 'table': {
      const topT = 0.04, legH = h - topT
      const wood = mat(obj.color || WOOD)
      if (Math.min(w, d) < 0.6 && obj.shape === 'cylinder') add(cyl(Math.min(w, d) / 2, topT, wood, 0, legH), cyl(0.04, legH, mat(DARK)), cyl(Math.min(w, d) / 4, 0.03, mat(DARK)))
      else { add(box(w, topT, d, wood, 0, legH)); add(...legs(w, d, legH, mat(obj.category === 'desk' ? DARK : shade(new THREE.Color(obj.color || WOOD), -0.1)), 0.04, 0.05)) }
      break
    }
    case 'drawers':
    case 'doors': {
      add(box(w, h, d, main))
      const face = mat(shade(base, -0.08))
      const panelD = 0.012
      if (fam === 'drawers') {
        const rows = Math.max(1, Math.min(4, Math.round(h / 0.3)))
        for (let i = 0; i < rows; i++) {
          const rh = h / rows
          add(box(w - 0.08, rh - 0.04, panelD, face, 0, i * rh + 0.02, -d / 2 - panelD / 2 + 0.002))
          add(box(Math.min(0.3, w * 0.3), 0.02, 0.02, mat(METAL, 0.4, 0.6), 0, i * rh + rh / 2, -d / 2 - 0.02))
        }
      } else {
        const cols = w > 0.9 ? 2 : 1
        for (let i = 0; i < cols; i++) {
          const cw = w / cols
          add(box(cw - 0.05, h - 0.06, panelD, face, -w / 2 + cw * (i + 0.5), 0.03, -d / 2 - panelD / 2 + 0.002))
          const hx = cols === 1 ? w * 0.35 : (i === 0 ? cw * 0.4 : -cw * 0.4) + (-w / 2 + cw * (i + 0.5))
          add(box(0.02, Math.min(0.25, h * 0.2), 0.02, mat(METAL, 0.4, 0.6), hx, h * 0.45, -d / 2 - 0.02))
        }
      }
      break
    }
    case 'shelves': {
      const t = 0.025
      const wood = mat(obj.color || WOOD)
      add(box(t, h, d, wood, -w / 2 + t / 2), box(t, h, d, wood, w / 2 - t / 2), box(w, t, d, wood, 0, h - t), box(w, h, 0.01, mat(shade(base, -0.1)), 0, 0, d / 2 - 0.005))
      const n = Math.max(1, Math.round(h / 0.35))
      for (let i = 0; i <= n; i++) add(box(w - 2 * t, t, d - 0.01, wood, 0, (h / (n + 1)) * i))
      break
    }
    case 'lamp': {
      const r = Math.min(w, d) / 2
      add(cyl(r * 0.6, 0.03, mat(DARK)), cyl(0.015, h * 0.75, mat(METAL, 0.5, 0.7)), cyl(r, h * 0.25, glow(obj.color || '#e9dcb8'), 0, h * 0.75, 0, r * 0.7))
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
      add(box(w, Math.max(h, 0.012), d, main))
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
