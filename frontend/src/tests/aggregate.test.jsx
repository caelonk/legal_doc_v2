import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ResultsPanel from '../components/ResultsPanel'
import { collectMissingClauses, collectRiskFlags } from '../lib/severity'
import { analysisResult, missingClause, riskFlag, section } from './fixtures'

/**
 * The frontend reads the MERGED view, and discloses what merging did.
 *
 * The merge rules themselves are pinned in backend/tests/test_aggregator.py —
 * duplicating them here would create a second implementation to drift. What these
 * assert is that the UI uses the aggregate rather than re-deriving from sections,
 * and that everything the merge removed is accounted for on screen.
 */

const withAggregate = (aggregate) => analysisResult({ aggregate })

const renderPanel = (result) => render(<ResultsPanel result={result} onNavigate={() => {}} />)

const baseAggregate = (overrides = {}) => ({
  document_type: 'Commercial Lease',
  document_type_agreement: 2,
  sections_analyzed: 2,
  risk_flags: [],
  missing_clauses: [],
  merged_duplicate_count: 0,
  contradicted_missing_clauses: [],
  ...overrides,
})

describe('findings come from the aggregate, not the sections', () => {
  it('renders merged findings even when they differ from the raw sections', () => {
    // Two sections each reported the clause; the aggregate has one. If the panel
    // re-derived from `sections` it would show two.
    const duplicated = section({
      chunk_index: 0,
      risk_flags: [riskFlag({ clause_type: 'Indemnification' }), riskFlag({ clause_type: 'Indemnification' })],
    })
    const result = analysisResult({
      sections: [duplicated],
      aggregate: baseAggregate({
        risk_flags: [
          { ...riskFlag({ clause_type: 'Indemnification' }), reported_by: [0, 1], severity_disagreement: false },
        ],
        merged_duplicate_count: 1,
      }),
    })
    expect(collectRiskFlags(result)).toHaveLength(1)
  })

  it('reads missing clauses from the aggregate too', () => {
    const result = analysisResult({
      aggregate: baseAggregate({
        missing_clauses: [{ ...missingClause({ clause_name: 'Casualty' }), reported_by: [0, 1] }],
      }),
    })
    expect(collectMissingClauses(result)).toHaveLength(1)
    expect(collectMissingClauses(result)[0].clause_name).toBe('Casualty')
  })

  it('gives every merged finding a unique key', () => {
    const result = withAggregate(
      baseAggregate({
        risk_flags: [
          { ...riskFlag({ clause_type: 'A' }), reported_by: [0], severity_disagreement: false },
          { ...riskFlag({ clause_type: 'B' }), reported_by: [1], severity_disagreement: false },
        ],
      }),
    )
    const keys = collectRiskFlags(result).map((f) => f.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('returns nothing when there is no aggregate at all', () => {
    expect(collectRiskFlags(null)).toEqual([])
    expect(collectRiskFlags({ sections: [] })).toEqual([])
  })
})

describe('disclosing what the merge removed', () => {
  it('says how many duplicate reports were merged', () => {
    // Explains why the finding count is smaller than the sum of the section
    // counts. Without it a reader comparing the two is left guessing.
    renderPanel(
      withAggregate(
        baseAggregate({
          risk_flags: [
            { ...riskFlag({ clause_type: 'Indemnification' }), reported_by: [0, 1], severity_disagreement: false },
          ],
          merged_duplicate_count: 2,
        }),
      ),
    )
    expect(screen.getByText(/2 duplicate reports merged/i)).toBeInTheDocument()
  })

  it('says nothing when nothing was merged', () => {
    renderPanel(
      withAggregate(
        baseAggregate({
          risk_flags: [
            { ...riskFlag({ clause_type: 'A' }), reported_by: [0], severity_disagreement: false },
          ],
        }),
      ),
    )
    expect(screen.queryByText(/duplicate/i)).not.toBeInTheDocument()
  })

  it('names absence claims withheld because the clause exists elsewhere', () => {
    // Dropping a claim silently is the thing this codebase does not do.
    renderPanel(
      withAggregate(
        baseAggregate({
          risk_flags: [
            { ...riskFlag({ clause_type: 'Governing Law' }), reported_by: [1], severity_disagreement: false },
          ],
          contradicted_missing_clauses: ['Governing Law'],
        }),
      ),
    )
    expect(screen.getByText(/reported missing by one section but flagged as present/i)).toBeInTheDocument()
    expect(screen.getByText('Governing Law', { selector: 'span' })).toBeInTheDocument()
  })

  it('says nothing about contradictions when there are none', () => {
    renderPanel(withAggregate(baseAggregate()))
    expect(screen.queryByText(/flagged as present elsewhere/i)).not.toBeInTheDocument()
  })
})

describe('severity disagreement between sections', () => {
  it('is surfaced on the finding', () => {
    // The merged severity is the highest any section gave; the reader should
    // know the model was not consistent about this clause.
    renderPanel(
      withAggregate(
        baseAggregate({
          risk_flags: [
            {
              ...riskFlag({ clause_type: 'Indemnification', severity: 'HIGH' }),
              reported_by: [0, 1],
              severity_disagreement: true,
            },
          ],
        }),
      ),
    )
    expect(screen.getByText(/Sections disagreed on severity/i)).toBeInTheDocument()
  })

  it('is not mentioned when the sections agreed', () => {
    renderPanel(
      withAggregate(
        baseAggregate({
          risk_flags: [
            {
              ...riskFlag({ clause_type: 'Indemnification' }),
              reported_by: [0, 1],
              severity_disagreement: false,
            },
          ],
        }),
      ),
    )
    expect(screen.queryByText(/disagreed on severity/i)).not.toBeInTheDocument()
  })

  it('still shows the higher severity badge', () => {
    renderPanel(
      withAggregate(
        baseAggregate({
          risk_flags: [
            {
              ...riskFlag({ clause_type: 'Indemnification', severity: 'HIGH' }),
              reported_by: [0, 1],
              severity_disagreement: true,
            },
          ],
        }),
      ),
    )
    expect(screen.getByText('High')).toBeInTheDocument()
  })
})
