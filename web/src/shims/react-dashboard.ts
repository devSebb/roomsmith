// In the dashboard bundle, `react` resolves to the host's React via the SDK.
const SDK = (window as any).__HERMES_PLUGIN_SDK__
const R = SDK?.React
if (!R) throw new Error('Roomsmith: window.__HERMES_PLUGIN_SDK__.React is missing')
export default R
export const useState = R.useState
export const useEffect = R.useEffect
export const useLayoutEffect = R.useLayoutEffect
export const useRef = R.useRef
export const useMemo = R.useMemo
export const useCallback = R.useCallback
export const useContext = R.useContext
export const createContext = R.createContext
export const createElement = R.createElement
export const Fragment = R.Fragment
export const Component = R.Component
export const memo = R.memo
export const forwardRef = R.forwardRef
