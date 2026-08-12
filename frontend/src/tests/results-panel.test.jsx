import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ResultsPanel from '../components/ResultsPanel'
import { analysisResult, missingClause, riskFlag, section } from './fixtures'

const renderPanel = (result) => render(<ResultsPanel result={result} onNavigate={() => {}} />)

describe('framing', () => {
  it('always carries the not-legal-advice disclosure', () => {
    renderPanel(analysisResult())
    expect(
      screen.getByText(/AI-generated analysis\. Verify against the source document\./i),
    ).toBeInTheDocument()
  })

  it('offers no way to dismiss the disclosure', () => {
    renderPanel(analysisResult())
    const dismissers = screen
      .queryAllByRole('button')
      .filter((b) => /dismiss|close|hide/i.test(b.textContent + b.getAttribute('aria-label')))
    expect(dismissers).toHaveLength(0)
  })
})

describe('risk flags', () => {
  it('shows counts per severity rather than one aggregate score', () => {
    renderPanel(
      analysisResult({
        sections: [
          section({
            risk_flags: [
              riskFlag({ severity: 'HIGH' }),
              riskFlag({ severity: 'HIGH' }),
              riskFlag({ severity: 'LOW' }),
            ],
          }),
        ],
      }),
    )
    expect(screen.getByText('2 high · 0 medium · 1 low')).toBeInTheDocument()
  })

  it('renders each flag with its explanation in the same row', () => {
    // A severity and a clause name with no explanation is a conclusion with
    // nothing to check it against.
    renderPanel(
      analysisResult({
        sections: [
          section({
            risk_flags: [
              riskFlag({ clause_type: 'Auto-renewal', explanation: 'Renews for five years.' }),
            ],
          }),
        ],
      }),
    )
    const row = screen.getByText('Auto-renewal').closest('tr')
    expect(within(row).getByText('Renews for five years.')).toBeInTheDocument()
    expect(within(row).getByText('High')).toBeInTheDocument()
  })

  it('states plainly that zero findings is not a clean bill of health', () => {
    // A clean result is the most dangerous moment for over-reliance.
    renderPanel(
      analysisResult({ sections: [section({ risk_flags: [], missing_clauses: [] })] }),
    )
    expect(screen.getByText(/No risk-flagged clauses were identified/i)).toBeInTheDocument()
    expect(screen.getByText(/not a clean bill of health/i)).toBeInTheDocument()
  })
})

describe('claim separation', () => {
  it('keeps missing clauses in their own section, not interleaved with risk flags', () => {
    renderPanel(
      analysisResult({
        sections: [
          section({
            risk_flags: [riskFlag({ clause_type: 'Indemnification' })],
            missing_clauses: [missingClause({ clause_name: 'Governing Law' })],
          }),
        ],
      }),
    )
    const riskTable = screen.getByText('Indemnification').closest('table')
    const missingTable = screen.getByText('Governing Law').closest('table')
    expect(riskTable).not.toBe(missingTable)
  })

  it('frames absence as the weaker claim', () => {
    renderPanel(analysisResult())
    expect(screen.getByText(/weaker claim than a flagged clause/i)).toBeInTheDocument()
  })
})

describe('skipped sections', () => {
  const withSkipped = (skipped) => analysisResult({ skipped })

  it('discloses that sections were skipped', () => {
    renderPanel(
      withSkipped([
        { chunk_index: 2, reason: 'TRUNCATED', message: 'Too long.', pages: [4, 5] },
      ]),
    )
    expect(screen.getByText(/1 section could not be analyzed/i)).toBeInTheDocument()
  })

  it('pluralises the section count', () => {
    renderPanel(
      withSkipped([
        { chunk_index: 2, reason: 'TRUNCATED', message: 'Too long.', pages: [4] },
        { chunk_index: 3, reason: 'API_ERROR', message: 'Failed.', pages: [5] },
      ]),
    )
    expect(screen.getByText(/2 sections could not be analyzed/i)).toBeInTheDocument()
  })

  it('says "Page 6" for one page and "Pages 4, 5" for several', () => {
    renderPanel(
      withSkipped([
        { chunk_index: 2, reason: 'TRUNCATED', message: 'Too long.', pages: [4, 5] },
        { chunk_index: 3, reason: 'API_ERROR', message: 'Failed.', pages: [6] },
      ]),
    )
    expect(screen.getByText(/Pages 4, 5:/)).toBeInTheDocument()
    expect(screen.getByText(/Page 6:/)).toBeInTheDocument()
  })

  it('never leaks the diagnostic detail field', () => {
    // ChunkFailure.detail carries raw API error bodies. SkippedSection omits it
    // by design; this fails loudly if the shape ever changes.
    renderPanel(
      withSkipped([
        {
          chunk_index: 2,
          reason: 'API_ERROR',
          message: 'This section could not be analyzed.',
          pages: [4],
          detail: 'APIStatusError 500: internal-trace-should-never-render',
        },
      ]),
    )
    expect(screen.queryByText(/internal-trace-should-never-render/)).not.toBeInTheDocument()
  })

  it('says nothing about skipped sections when none were skipped', () => {
    renderPanel(analysisResult({ skipped: [] }))
    expect(screen.queryByText(/could not be analyzed/i)).not.toBeInTheDocument()
  })
})

// Document metadata moved to DocumentHeader, which sits outside the tabs so the
// page keeps its h1 whichever view is open. Its assertions live in
// document-header.test.jsx.
