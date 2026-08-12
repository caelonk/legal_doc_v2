import { render, renderHook, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Analysis from '../pages/Analysis'
import ResultsPanel from '../components/ResultsPanel'
import { useAnalysisJob } from '../hooks/useAnalysisJob'
import { useReviewState } from '../hooks/useReviewState'
import { analysisResult, jobState, riskFlag, section } from './fixtures'
import { setWideViewport } from './viewport'

vi.mock('../hooks/useAnalysisJob', () => ({ useAnalysisJob: vi.fn() }))

const THREE_FLAGS = analysisResult({
  sections: [
    section({
      risk_flags: [
        riskFlag({ clause_type: 'Indemnification', severity: 'HIGH', page_reference: 4 }),
        riskFlag({ clause_type: 'Holdover', severity: 'MEDIUM', page_reference: 5 }),
        riskFlag({ clause_type: 'Late Charges', severity: 'LOW', page_reference: 2 }),
      ],
    }),
  ],
})

function renderPage({ result = THREE_FLAGS, wide = true } = {}) {
  setWideViewport(wide)
  useAnalysisJob.mockReturnValue({ job: jobState({ result }), error: null, isPolling: false })
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

const markButton = (clause) => screen.getByRole('button', { name: `Mark ${clause} as reviewed` })

beforeEach(() => vi.clearAllMocks())

describe('marking a finding reviewed', () => {
  it('starts unreviewed', () => {
    renderPage()
    expect(markButton('Indemnification')).toHaveAttribute('aria-pressed', 'false')
  })

  it('toggles on', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    expect(markButton('Indemnification')).toHaveAttribute('aria-pressed', 'true')
  })

  it('toggles back off', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(markButton('Indemnification'))
    expect(markButton('Indemnification')).toHaveAttribute('aria-pressed', 'false')
  })

  it('marks only the finding that was clicked', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    expect(markButton('Holdover')).toHaveAttribute('aria-pressed', 'false')
  })

  it('reports how many have been reviewed', async () => {
    const { user } = renderPage()
    expect(screen.getByText('0 of 3 reviewed')).toBeInTheDocument()
    await user.click(markButton('Indemnification'))
    expect(screen.getByText('1 of 3 reviewed')).toBeInTheDocument()
  })

  it('keeps the explanation visible on a reviewed finding', async () => {
    // Reviewing must not collapse the one field that supports the conclusion.
    // .claude/rules/ai-output.md: never render a conclusion without its
    // explanation in the same visual unit.
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    const row = markButton('Indemnification').closest('tr')
    expect(row.textContent).toMatch(/indemnifies Landlord/i)
  })

  it('keeps the severity badge on a reviewed finding', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    const row = markButton('Indemnification').closest('tr')
    expect(row.textContent).toMatch(/High/)
  })

  it('does not remove the finding from the list', async () => {
    // Marked reviewed is not dismissed. The default view still shows everything.
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    expect(screen.getByText('Indemnification')).toBeInTheDocument()
  })
})

describe('hiding reviewed findings', () => {
  it('offers no filter until something has been reviewed', () => {
    renderPage()
    expect(screen.queryByRole('button', { name: /hide reviewed/i })).not.toBeInTheDocument()
  })

  it('hides them on request', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(screen.getByRole('button', { name: /hide reviewed/i }))
    expect(screen.queryByText('Indemnification')).not.toBeInTheDocument()
  })

  it('says how many are hidden rather than letting them vanish silently', async () => {
    // Findings are never silently absent — the same principle as disclosing
    // skipped sections.
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(screen.getByRole('button', { name: /hide reviewed/i }))
    expect(screen.getByText(/1 reviewed finding hidden/i)).toBeInTheDocument()
  })

  it('pluralises the hidden count', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(markButton('Holdover'))
    await user.click(screen.getByRole('button', { name: /hide reviewed/i }))
    expect(screen.getByText(/2 reviewed findings hidden/i)).toBeInTheDocument()
  })

  it('keeps the total count honest while filtered', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(screen.getByRole('button', { name: /hide reviewed/i }))
    expect(screen.getByText('1 of 3 reviewed')).toBeInTheDocument()
  })

  it('brings them back', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(screen.getByRole('button', { name: /hide reviewed/i }))
    await user.click(screen.getByRole('button', { name: /show reviewed/i }))
    expect(screen.getByText('Indemnification')).toBeInTheDocument()
  })
})

describe('the navigator shares the review state', () => {
  it('shows a finding marked in the findings table as reviewed', async () => {
    // Two views of the same findings. A mark made in one that did not show in
    // the other would read as a bug.
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(screen.getByRole('tab', { name: /navigator/i }))
    const nav = screen.getByRole('navigation', { name: /flagged clauses/i })
    const entry = [...nav.querySelectorAll('button')].find((b) =>
      /Indemnification/.test(b.getAttribute('aria-label')),
    )
    expect(entry.textContent).toMatch(/Reviewed/)
  })

  it('leaves unreviewed entries unmarked', async () => {
    const { user } = renderPage()
    await user.click(markButton('Indemnification'))
    await user.click(screen.getByRole('tab', { name: /navigator/i }))
    const nav = screen.getByRole('navigation', { name: /flagged clauses/i })
    const entry = [...nav.querySelectorAll('button')].find((b) =>
      /Holdover/.test(b.getAttribute('aria-label')),
    )
    expect(entry.textContent).not.toMatch(/Reviewed/)
  })
})

describe('useReviewState', () => {
  it('clears when the job changes', () => {
    // Review marks are keyed per finding within one result. Carrying them into a
    // different document would mark findings the reader has never seen.
    const { result, rerender } = renderHook(({ id }) => useReviewState(id), {
      initialProps: { id: 'job-a' },
    })
    act(() => result.current.toggle('0-0'))
    expect(result.current.reviewed.has('0-0')).toBe(true)

    rerender({ id: 'job-b' })
    expect(result.current.reviewed.size).toBe(0)
  })

  it('keeps marks while the job is unchanged', () => {
    const { result, rerender } = renderHook(({ id }) => useReviewState(id), {
      initialProps: { id: 'job-a' },
    })
    act(() => result.current.toggle('0-0'))
    rerender({ id: 'job-a' })
    expect(result.current.reviewed.has('0-0')).toBe(true)
  })
})

describe('ResultsPanel without review wiring', () => {
  it('renders when no review props are supplied', () => {
    // The panel is also rendered in tests and could be reused elsewhere; a
    // missing Set must not throw.
    render(<ResultsPanel result={THREE_FLAGS} onNavigate={() => {}} />)
    expect(screen.getByText('0 of 3 reviewed')).toBeInTheDocument()
  })
})
