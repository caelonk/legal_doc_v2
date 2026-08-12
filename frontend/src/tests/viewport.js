/**
 * Controllable matchMedia for tests.
 *
 * jsdom implements no media queries at all, so without this every test sees the
 * narrow layout and the two-pane desktop path is never exercised. The stub
 * answers only the width query the app actually asks; anything else is false, so
 * a query added later fails loudly here rather than quietly matching.
 */
let wide = false

export function setWideViewport(value) {
  wide = value
}

export function installMatchMedia() {
  window.matchMedia = (query) => ({
    matches: /min-width:\s*1024px/.test(query) ? wide : false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })
}
