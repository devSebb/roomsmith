// Minimal typings for the parts of '@hermes/plugin-sdk' this plugin uses.
// The real module is provided by Hermes Desktop at load time (never bundled).
declare module '@hermes/plugin-sdk' {
  export interface ReadableAtom<T> { get(): T; subscribe(fn: (v: T) => void): () => void }
  export interface WritableAtom<T> extends ReadableAtom<T> { set(v: T): void }
  export function atom<T>(initial: T): WritableAtom<T>
  export function useValue<T>(a: ReadableAtom<T>): T
  export const host: {
    state: Record<string, ReadableAtom<any>>
    notify(n: { kind: 'info' | 'success' | 'warning' | 'error'; message: string; title?: string; detail?: string }): string
    notifyError(e: unknown, fallback: string): void
    navigate(route: string): void
    request<T>(method: string, params?: unknown): Promise<T>
    onEvent(type: string, fn: (e: unknown) => void): () => void
  }
  export const PANES_AREA: string
  export const ROUTES_AREA: string
  export const SIDEBAR_NAV_AREA: string
  export const STATUSBAR_AREAS: { left: string; right: string }
  export const TITLEBAR_AREAS: { left: string; center: string; right: string }
  export const PALETTE_AREA: string
  export const KEYBINDS_AREA: string
}
