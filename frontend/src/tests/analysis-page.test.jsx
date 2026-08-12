import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Analysis from '../pages/Analysis'
import { useAnalysisJob } from '../hooks/useAnalysisJob'
import { analysisResult, jobState, section } from './fixtures'

vi.mock('../hooks/useAnalysisJob', () => ({ useAnalysisJob: vi.fn() }))

function renderAnalysis({ job = null, error = null }) {
  useAnalysisJob.mockReturnValue({ job, error, isPolling: false })
  return render(
    <MemoryRouter initialEntries={['/analysis/abc123']}>
      <Routes>
        <Route path="/analysis/:jobId" element={<Analysis />} />
      </Routes>
    </MemoryRouter>,
  )
}

const liveRegions = (container) => [...container.querySelectorAll('[aria-live]')]

beforeEach(() => vi.clearAllMocks())

/**
 * The live region has to exist in EVERY branch, not just the one that has
 * something to say. A region that mounts at the same moment as its text is
 * unreliably announced — which is how analysis completion ended up silent, since
 * AnalysisProgress owned the only region and unmounts the instant the job
 * finishes.
 */
describe('status is announced in every state', () => {
  it.each([
    ['loading', { job: null }],
    ['running', { job: jobState({ status: 'ANALYZING', result: null, completed_chunks: 1 }) }],
    ['complete', { job: jobState() }],
    ['failed', { job: jobState({ status: 'FAILED', result: null, error: 'Everything failed.' }) }],
    ['load error', { job: null, error: new Error('Job expired.') }],
  ])('has a live region while %s', (_label, props) => {
    const { container } = renderAnalysis(props)
    expect(liveRegions(container).length).toBeGreaterThan(0)
  })

  it('announces completion with the finding count', () => {
    const { container } = renderAnalysis({ job: jobState() })
    const announced = liveRegions(container).map((el) => el.textContent).join(' ')
    expect(announced).toMatch(/Analysis complete\. 1 risk flag found\./)
  })

  it('pluralises the announced count', () => {
    const job = jobState({
      result: analysisResult({
        sections: [section({ risk_flags: [{ clause_type: 'A', severity: 'HIGH', explanation: 'x', page_reference: 1 }, { clause_type: 'B', severity: 'LOW', explanation: 'y', page_reference: 2 }] })],
      }),
    })
    const { container } = renderAnalysis({ job })
    const announced = liveRegions(container).map((el) => el.textContent).join(' ')
    expect(announced).toMatch(/2 risk flags found/)
  })

  it('announces skipped sections alongside completion', () => {
    const job = jobState({
      result: analysisResult({
        skipped: [{ chunk_index: 1, reason: 'TRUNCATED', message: 'Too long.', pages: [3] }],
      }),
    })
    const { container } = renderAnalysis({ job })
    const announced = liveRegions(container).map((el) => el.textContent).join(' ')
    expect(announced).toMatch(/1 section could not be analyzed/)
  })

  it('announces failure', () => {
    const { container } = renderAnalysis({
      job: jobState({ status: 'FAILED', result: null, error: 'Everything failed.' }),
    })
    const announced = liveRegions(container).map((el) => el.textContent).join(' ')
    expect(announced).toMatch(/Analysis failed/)
  })
})

describe('a failed run is never shown as an empty result', () => {
  const failed = jobState({
    status: 'FAILED',
    result: null,
    error: 'None of the 2 sections of this document could be analyzed.',
  })

  it('renders the failure reason visibly, as well as announcing it', () => {
    // The reason legitimately appears twice: once on screen and once inside the
    // sr-only live region. Asserted separately so this cannot pass on the
    // announcement alone — a failure nobody can SEE is not reported.
    renderAnalysis({ job: failed })
    const matches = screen.getAllByText(/None of the 2 sections/i)
    const visible = matches.filter((el) => !el.closest('[aria-live]'))
    const announced = matches.filter((el) => el.closest('[aria-live]'))
    expect(visible).toHaveLength(1)
    expect(announced.length).toBeGreaterThan(0)
  })

  it('renders no findings table', () => {
    // "No risks found" is the most dangerous thing this product can say. A run
    // that analyzed nothing must never be presented as a run that found nothing.
    const { container } = renderAnalysis({ job: failed })
    expect(container.querySelectorAll('table')).toHaveLength(0)
  })

  it('does not claim zero risks were identified', () => {
    renderAnalysis({ job: failed })
    expect(screen.queryByText(/No risk-flagged clauses were identified/i)).not.toBeInTheDocument()
  })

  it('offers a way back', () => {
    renderAnalysis({ job: failed })
    expect(screen.getByRole('link', { name: /upload a document/i })).toBeInTheDocument()
  })
})

describe('progress', () => {
  it('renders the stage message verbatim from the API', () => {
    // Composed in services/jobs.py::_stage_message so the count and the wording
    // cannot drift apart. Re-deriving the sentence here would reintroduce that.
    renderAnalysis({
      job: jobState({
        status: 'ANALYZING',
        result: null,
        stage_message: 'Analyzing 4 of 11 sections',
        completed_chunks: 3,
        total_chunks: 11,
      }),
    })
    expect(screen.getByText('Analyzing 4 of 11 sections')).toBeInTheDocument()
  })

  it('exposes determinate progress, not an opaque spinner', () => {
    renderAnalysis({
      job: jobState({ status: 'ANALYZING', result: null, completed_chunks: 3, total_chunks: 11 }),
    })
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '3')
    expect(bar).toHaveAttribute('aria-valuemax', '11')
  })

  it('shows the document metadata before the analysis finishes', () => {
    renderAnalysis({ job: jobState({ status: 'ANALYZING', result: null }) })
    expect(screen.getByText('sample_lease.pdf')).toBeInTheDocument()
  })
})
