// `react/jsx-runtime` for the dashboard bundle, built on the host's React.
const R = (window as any).__HERMES_PLUGIN_SDK__?.React
if (!R) throw new Error('Room Studio: window.__HERMES_PLUGIN_SDK__.React is missing')
export const Fragment = R.Fragment
function make(type: any, props: any, key?: any) {
  const { children, ...rest } = props || {}
  if (key !== undefined) rest.key = key
  if (children === undefined) return R.createElement(type, rest)
  return Array.isArray(children) ? R.createElement(type, rest, ...children) : R.createElement(type, rest, children)
}
export const jsx = make
export const jsxs = make
export const jsxDEV = make
