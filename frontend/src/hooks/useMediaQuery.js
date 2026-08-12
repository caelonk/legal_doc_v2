import { useEffect, useState } from 'react'

/**
 * Track a CSS media query from JS.
 *
 * Used to choose between the two-pane desktop layout and the tabbed narrow one.
 * A CSS-only approach would need both layouts mounted at once, which means two
 * SourcePane instances and two refs — and the citation jump would have to guess
 * which one is visible.
 *
 * Defaults to FALSE (the narrow, tabbed layout) when matchMedia is unavailable.
 * That is the safe direction: every pane stays reachable through a tab, whereas
 * defaulting to the wide layout on a browser that cannot confirm the width would
 * render a two-pane split into a viewport too small to hold it.
 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia?.(query).matches,
  )

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const list = window.matchMedia(query)
    // Re-read on mount: the query may have changed between the initial state and
    // this effect running.
    setMatches(list.matches)
    const onChange = (event) => setMatches(event.matches)
    list.addEventListener('change', onChange)
    return () => list.removeEventListener('change', onChange)
  }, [query])

  return matches
}
