import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ResultsPanel from '../components/ResultsPanel'
import { analysisResult, missingClause, riskFlag, section } from './fixtures'

/**
 * Heading structure.
 *
 * This file exists because of a mistake: promoting the document title from h2 to
 * h1 to give the page a top-level heading left the panel going h1 straight to h3,
 * trading a missing level for a skipped one. Both break heading-based screen
 * reader navigation, and neither is visible on screen — which is exactly the kind
 * of regression a test has to catch, because a human reviewing the rendered page
 * will not.
 */

function headingLevels(container) {
  return [...container.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((el) => ({
    level: Number(el.tagName[1]),
    text: el.textContent.trim().slice(0, 40),
  }))
}

function findSkip(headings) {
  for (let i = 1; i < headings.length; i += 1) {
    const jump = headings[i].level - headings[i - 1].level
    if (jump > 1) {
      return `"${headings[i - 1].text}" (h${headings[i - 1].level}) -> "${headings[i].text}" (h${headings[i].level})`
    }
  }
  return null
}

const populated = analysisResult({
  skipped: [{ chunk_index: 2, reason: 'TRUNCATED', message: 'Too long.', pages: [4, 5] }],
  sections: [
    section({ risk_flags: [riskFlag()], missing_clauses: [missingClause()] }),
  ],
})

const empty = analysisResult({
  skipped: [],
  sections: [section({ risk_flags: [], missing_clauses: [] })],
})

describe.each([
  ['a populated result', populated],
  ['an empty result', empty],
])('heading hierarchy for %s', (_label, result) => {
  it('has exactly one h1', () => {
    const { container } = render(<ResultsPanel result={result} onNavigate={() => {}} />)
    const h1s = headingLevels(container).filter((h) => h.level === 1)
    expect(h1s).toHaveLength(1)
  })

  it('starts at h1', () => {
    const { container } = render(<ResultsPanel result={result} onNavigate={() => {}} />)
    expect(headingLevels(container)[0].level).toBe(1)
  })

  it('skips no heading level', () => {
    const { container } = render(<ResultsPanel result={result} onNavigate={() => {}} />)
    const headings = headingLevels(container)
    const skip = findSkip(headings)
    expect(skip, `heading level skipped: ${skip}`).toBeNull()
  })
})

describe('section headings', () => {
  it('puts every top-level section at h2 under the document title', () => {
    const { container } = render(<ResultsPanel result={populated} onNavigate={() => {}} />)
    const byText = Object.fromEntries(
      headingLevels(container).map((h) => [h.text, h.level]),
    )
    expect(byText['sample_lease.pdf']).toBe(1)
    expect(byText['Risk flags']).toBe(2)
    expect(byText['Possibly missing provisions']).toBe(2)
    expect(byText['Section summaries']).toBe(2)
  })
})

describe('tables', () => {
  it('gives every table real column headers', () => {
    const { container } = render(<ResultsPanel result={populated} onNavigate={() => {}} />)
    const tables = [...container.querySelectorAll('table')]
    expect(tables.length).toBeGreaterThan(0)
    for (const table of tables) {
      expect(table.querySelectorAll('th[scope="col"]').length).toBeGreaterThan(0)
    }
  })
})

describe('interactive elements', () => {
  it('gives every button an accessible name', () => {
    const { container } = render(<ResultsPanel result={populated} onNavigate={() => {}} />)
    const unnamed = [...container.querySelectorAll('button')].filter(
      (b) => !(b.getAttribute('aria-label') || b.textContent.trim()),
    )
    expect(unnamed).toHaveLength(0)
  })
})
