import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Analysis from '../pages/Analysis'
import { useAnalysisJob } from '../hooks/useAnalysisJob'
import { jobState } from './fixtures'
import { setWideViewport } from './viewport'

vi.mock('../hooks/useAnalysisJob', () => ({ useAnalysisJob: vi.fn() }))

const running = (overrides = {}) =>
  jobState({
    status: 'ANALYZING',
    result: null,
    stage_message: 'Analyzing 2 of 6 sections',
    completed_chunks: 1,
    total_chunks: 6,
    ...overrides,
  })

function renderRunning({ wide = true, job = running() } = {}) {
  setWideViewport(wide)
  useAnalysisJob.mockReturnValue({ job, error: null, isPolling: true })
  return render(
    <MemoryRouter initialEntries={['/analysis/abc123']}>
      <Routes>
        <Route path="/analysis/:jobId" element={<Analysis />} />
      </Routes>
    </MemoryRouter>,
  )
}

const skeletons = (container) => container.querySelectorAll('.animate-pulse')
// The paper surface is the document-page card, so this counts placeholder pages
// rather than every shimmering line inside them.
const pageCards = (container) => container.querySelectorAll('.bg-surface-paper').length

beforeEach(() => vi.clearAllMocks())

describe('while an analysis is running', () => {
  it('renders skeleton placeholders rather than a bare spinner', () => {
    // ui-patterns.md §4 and design-system.md §5: skeleton shapes matching the
    // final layout for anything over ~400ms, and a chunked analysis runs for
    // tens of seconds.
    const { container } = renderRunning()
    expect(skeletons(container).length).toBeGreaterThan(0)
  })

  it('still shows determinate progress alongside them', () => {
    // The skeleton is shape, not status. The count is what tells the reader how
    // far along the analysis is, and it must not be replaced by decoration.
    renderRunning()
    expect(screen.getByText('Analyzing 2 of 6 sections')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1')
  })

  it('shows the real document identity, which is known before analysis finishes', () => {
    // Page count and filename arrive with the 202 — the route parses inside the
    // POST precisely so this is available immediately.
    renderRunning()
    expect(screen.getByRole('heading', { level: 1, name: 'sample_lease.pdf' })).toBeInTheDocument()
    expect(screen.getByText('6 pages')).toBeInTheDocument()
  })

  it('hides the placeholders from assistive tech', () => {
    // A screen reader announcing a dozen empty boxes would be noise on top of
    // the progress bar and live region, which already carry the real status.
    const { container } = renderRunning()
    for (const block of skeletons(container)) {
      expect(block.closest('[aria-hidden="true"]')).not.toBeNull()
    }
  })

  it('shows no findings table yet', () => {
    const { container } = renderRunning()
    expect(container.querySelectorAll('table')).toHaveLength(0)
  })

  it('claims nothing about risks while still running', () => {
    renderRunning()
    expect(screen.queryByText(/No risk-flagged clauses/i)).not.toBeInTheDocument()
  })
})

describe('skeleton layout matches the final one', () => {
  it('places source placeholders beside the findings on a wide viewport', () => {
    const { container } = renderRunning({ wide: true })
    // The source column only exists in the wide layout, so its placeholders are
    // what distinguish the two.
    expect(container.querySelector('.w-3\\/5')).not.toBeNull()
  })

  it('uses a single column on a narrow viewport', () => {
    const { container } = renderRunning({ wide: false })
    expect(container.querySelector('.w-3\\/5')).toBeNull()
    expect(skeletons(container).length).toBeGreaterThan(0)
  })

  it('matches the placeholder page count to a short document', () => {
    const { container } = renderRunning({
      job: running({ document: { ...running().document, page_count: 3 } }),
    })
    expect(pageCards(container)).toBe(3)
  })

  it('caps placeholder pages for a long document', () => {
    // A 200-page document should not mount 200 cards nobody will scroll to while
    // waiting. Four establish the shape.
    const { container } = renderRunning({
      job: running({ document: { ...running().document, page_count: 200 } }),
    })
    expect(pageCards(container)).toBe(4)
  })
})
