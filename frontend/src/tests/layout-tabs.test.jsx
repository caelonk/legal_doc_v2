import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Analysis from '../pages/Analysis'
import { useAnalysisJob } from '../hooks/useAnalysisJob'
import { jobState } from './fixtures'
import { setWideViewport } from './viewport'

vi.mock('../hooks/useAnalysisJob', () => ({ useAnalysisJob: vi.fn() }))

/**
 * Interactions go through user-event rather than element.click().
 *
 * Radix Tabs activates a trigger on mousedown and on focus, not on click — a bare
 * .click() dispatches neither and the panel never changes. That is not a quirk to
 * work around; a real pointer and a real keyboard both produce those events, and
 * a test that fakes a lone click event is asserting against something no user
 * does.
 */
function renderAnalysis({ wide }) {
  setWideViewport(wide)
  useAnalysisJob.mockReturnValue({ job: jobState(), error: null, isPolling: false })
  return {
    user: userEvent.setup(),
    ...render(
      <MemoryRouter initialEntries={['/analysis/abc123']}>
        <Routes>
          <Route path="/analysis/:jobId" element={<Analysis />} />
        </Routes>
      </MemoryRouter>,
    ),
  }
}

const tabNames = () => screen.getAllByRole('tab').map((t) => t.textContent.trim())
const selectedTab = () => screen.getByRole('tab', { selected: true }).textContent.trim()
const sourceVisible = () => screen.queryByText(/COMMERCIAL LEASE AGREEMENT/) !== null

beforeEach(() => vi.clearAllMocks())

describe('wide viewport', () => {
  it('keeps the source pane always visible beside the findings', () => {
    // The split pane is the point: check a claim against the source without
    // losing your place. Putting the document behind a tab here would break that.
    renderAnalysis({ wide: true })
    expect(sourceVisible()).toBe(true)
  })

  it('offers findings and the navigator as tabs, and no document tab', () => {
    renderAnalysis({ wide: true })
    expect(tabNames()).toEqual(['Findings', 'Clause navigator'])
  })

  it('starts on findings', () => {
    renderAnalysis({ wide: true })
    expect(selectedTab()).toBe('Findings')
  })

  it('shows the navigator when its tab is chosen', async () => {
    const { user } = renderAnalysis({ wide: true })
    await user.click(screen.getByRole('tab', { name: 'Clause navigator' }))
    expect(screen.getByRole('navigation', { name: /flagged clauses/i })).toBeInTheDocument()
  })

  it('keeps the document visible while the navigator tab is open', async () => {
    const { user } = renderAnalysis({ wide: true })
    await user.click(screen.getByRole('tab', { name: 'Clause navigator' }))
    expect(sourceVisible()).toBe(true)
  })
})

describe('narrow viewport', () => {
  it('collapses to one pane at a time with three tabs', () => {
    renderAnalysis({ wide: false })
    expect(tabNames()).toEqual(['Findings', 'Navigator', 'Document'])
  })

  it('does not render the source alongside the findings', () => {
    // design-system.md §3: do not try to keep two panes on a phone.
    renderAnalysis({ wide: false })
    expect(sourceVisible()).toBe(false)
  })

  it('reveals the document when its tab is chosen', async () => {
    const { user } = renderAnalysis({ wide: false })
    await user.click(screen.getByRole('tab', { name: 'Document' }))
    expect(sourceVisible()).toBe(true)
  })

  it('reaches the navigator too', async () => {
    const { user } = renderAnalysis({ wide: false })
    await user.click(screen.getByRole('tab', { name: 'Navigator' }))
    expect(screen.getByRole('navigation', { name: /flagged clauses/i })).toBeInTheDocument()
  })
})

describe('following a citation on a narrow viewport', () => {
  it('switches to the document tab', async () => {
    // The source is unmounted behind a tab here, so a citation click that only
    // called scrollToPage would silently do nothing — the same class of failure
    // the desktop scroll was hardened against.
    const { user } = renderAnalysis({ wide: false })
    await user.click(screen.getAllByRole('button', { name: /go to page/i })[0])
    expect(selectedTab()).toBe('Document')
  })

  it('brings the source text into view', async () => {
    const { user } = renderAnalysis({ wide: false })
    await user.click(screen.getAllByRole('button', { name: /go to page/i })[0])
    expect(sourceVisible()).toBe(true)
  })

  it('works from the navigator as well as the findings table', async () => {
    const { user } = renderAnalysis({ wide: false })
    await user.click(screen.getByRole('tab', { name: 'Navigator' }))
    await user.click(screen.getAllByRole('button', { name: /severity, page/i })[0])
    expect(selectedTab()).toBe('Document')
  })

  it('does not switch tabs on a wide viewport, where the source is already shown', async () => {
    const { user } = renderAnalysis({ wide: true })
    await user.click(screen.getAllByRole('button', { name: /go to page/i })[0])
    expect(selectedTab()).toBe('Findings')
  })
})

describe('keyboard operability', () => {
  // This is the reason the Radix dependency exists rather than divs with onClick.
  // If these pass with a hand-rolled version, the dependency was not needed.
  it('moves between tabs with the arrow keys', async () => {
    const { user } = renderAnalysis({ wide: true })
    await user.tab()
    await user.keyboard('{ArrowRight}')
    expect(selectedTab()).toBe('Clause navigator')
  })

  it('wraps from the last tab back to the first', async () => {
    const { user } = renderAnalysis({ wide: false })
    await user.click(screen.getByRole('tab', { name: 'Document' }))
    await user.keyboard('{ArrowRight}')
    expect(selectedTab()).toBe('Findings')
  })

  it('jumps to the last tab with End', async () => {
    const { user } = renderAnalysis({ wide: false })
    await user.click(screen.getByRole('tab', { name: 'Findings' }))
    await user.keyboard('{End}')
    expect(selectedTab()).toBe('Document')
  })

  it('treats the whole tab list as one tab stop', async () => {
    // Roving tabindex, asserted through behaviour rather than attributes. Radix
    // assigns the tab stop lazily — at mount every trigger is tabindex="-1" and
    // the stop appears only once focus enters the group — so checking attributes
    // on a freshly rendered list measures an implementation detail and reports a
    // failure that no user could experience.
    //
    // What a user can experience: Tab enters the list once, and the next Tab
    // leaves it instead of walking through every trigger.
    const { user } = renderAnalysis({ wide: true })
    await user.tab()
    expect(screen.getByRole('tab', { name: 'Findings' })).toHaveFocus()

    await user.tab()
    const focusedTabs = screen.getAllByRole('tab').filter((t) => t === document.activeElement)
    expect(focusedTabs).toHaveLength(0)
  })
})

describe('tab semantics', () => {
  it('gives the tab list an accessible name', () => {
    renderAnalysis({ wide: true })
    expect(screen.getByRole('tablist', { name: /analysis views/i })).toBeInTheDocument()
  })

  it('wires each tab to a panel', () => {
    renderAnalysis({ wide: true })
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).toHaveAttribute('aria-controls')
    }
    expect(screen.getAllByRole('tabpanel').length).toBeGreaterThan(0)
  })
})
