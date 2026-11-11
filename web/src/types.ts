// Mirrors rs_core/model.py. Metres, radians, +Y up, floor at y = 0, front = -Z.

export interface Vertex { id: string; x: number; z: number }
export interface Wall { id: string; a: string; b: string; color: string; label?: string }
export interface Opening {
  id: string; wall_id: string; kind: 'door' | 'window' | 'opening';
  offset_m: number; width_m: number; height_m: number; sill_m: number;
  swing?: 'in' | 'out' | 'none'; hinge?: 'left' | 'right'; dims_source?: string
}
export interface Product { title?: string; url?: string | null; image_url?: string | null; image_data?: string | null; price?: string | null; price_amount?: number | null; price_currency?: string | null; dimensions_text?: string | null; assumed_order?: boolean; source?: string | null }
export interface SceneObject {
  id: string; name: string; category: string; shape: 'box' | 'cylinder';
  dimensions_m: [number, number, number]; position_m: [number, number, number]; yaw_rad: number;
  mount: 'floor' | 'wall' | 'surface' | 'ceiling'; color: string; locked: boolean;
  provenance?: { class?: string; dims_source?: string; confidence?: number }; product?: Product | null
}
export interface Scene {
  schema_version: number
  project: { id: string; name: string; units: string }
  calibration: { status: 'calibrated' | 'uncalibrated'; reference: unknown }
  room: { height_m: number; vertices: Vertex[]; walls: Wall[]; floor: { color: string }; ceiling: { color: string }; openings: Opening[] }
  objects: SceneObject[]
  photos: unknown[]
  budget?: { limit: number; currency: string | null; reserve: number } | null
}
/** Mirrors rs_core/money.budget_status. */
export interface BudgetStatus {
  limit: number; currency: string | null; reserve: number; spendable: number; spent: number; remaining: number; remaining_spendable: number
  over_limit: boolean; uses_reserve: boolean; text: string
  items: { id: string; name: string; amount: number; currency: string | null; url?: string | null }[]
  unpriced: string[]; other_currency: { id: string; name: string; amount: number; currency: string }[]
}
export interface Issue { code: string; severity: 'info' | 'warning'; ids: string[]; message: string }
export interface Head { project_id: string; name: string; revision: number; updated_at: number; actor: string; summary: string; changed_ids: string[] }
export interface ProjectRow { project_id: string; name: string; revision: number; updated_at: number; size_m: [number, number]; objects: number; issues: number; calibrated: boolean; active: boolean }
export interface Revision { revision: number; created_at: number; actor: string; summary: string; changed_ids: string[] }

export type Op = Record<string, unknown> & { op: string }

export interface ApplyResult {
  ok: boolean; revision?: number; summary?: string; changed_ids?: string[]; issues?: Issue[]
  results?: { op: string; summary: string; created_id?: string }[]
  error?: { code: string; message: string; current_revision?: number }
}
