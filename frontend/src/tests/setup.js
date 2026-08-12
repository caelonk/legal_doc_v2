import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'
import { installMatchMedia, setWideViewport } from './viewport'

afterEach(cleanup)

// Narrow by default, so a test that cares about the desktop layout has to say so.
installMatchMedia()
beforeEach(() => setWideViewport(false))

// jsdom implements no layout and no scrolling, so Element.scrollTo does not
// exist and throws "Not implemented" when called. SourcePane calls it when a
// citation is followed. Stubbed rather than avoided: the point of those tests is
// the highlight and the lookup, and a missing browser API should not read as a
// component failure.
//
// This is also the boundary of what these tests can prove — see tests/README.md.
// Anything that depends on real layout (target sizes, reflow, actual scroll
// offsets) is verified in a browser, not here.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = function scrollTo() {}
}
