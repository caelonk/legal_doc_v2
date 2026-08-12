import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Analysis from '../pages/Analysis'
import ResultsPanel from '../components/ResultsPanel'
import { useAnalysisJob } from '../hooks/useAnalysisJob'
import { analysisResult, jobState, missingClause, riskFlag, section } from './fixtures'
import { setWideViewport } from './viewport'

vi.mock('../hooks/useAnalysisJob', () => ({ useAnalysisJob: vi.fn() }))

/**
 * Heading structure, asserted at the PAGE level.
 *
 * This file exists because of two mistakes, one per pass. First, promoting the
 * document title from h2 to h1 left ResultsPanel going h1 straight to h3 — a
 * missing level traded for a skipped one. Then tabs moved that h1 inside a panel,
 * so opening the Clause navigator unmounted it and the page had no top-level
 * heading at all.
 *
 * Both were invisible on screen, and the second is why these assertions now run
 * against the whole page with each tab open, rather than against one component.
 * A heading hierarchy is a property of a page, and a component test cannot see it.
 */

function headings() {
  return [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((el) => ({
    level: Number(el.tagName[1]),
    text: el.textContent.trim().slice(0, 40),
  }))
}

function findSkip(list) {
  for (let i = 1; i < list.length; i += 1) {
    if (list[i].level - list[i - 1].level > 1) {
      return `"${list[i - 1].text}" (h${list[i - 1].level}) -> "${list[i].text}" (h${list[i].level})`
    }
  }
  return null
}

const populated = analysisResult({
  skipped: [{ chunk_index: 2, reason: 'TRUNCATED', message: 'Too long.', pages: [4, 5] }],
  sections: [section({ risk_flags: [riskFlag()], missing_clauses: [missingClause()] })],
})

const empty = analysisResult({
  skipped: [],
  sections: [section({ risk_flags: [], missing_clauses: [] })],
})

function renderPage({ wide, result }) {
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

beforeEach(() => vi.clearAllMocks())

const LAYOUTS = [
  ['wide', true],
  ['narrow', false],
]

describe.each(LAYOUTS)('heading hierarchy on a %s viewport', (_label, wide) => {
  it.each([
    ['populated', populated],
    ['empty', empty],
  ])('has exactly one h1 with a %s result', (_name, result) => {
    renderPage({ wide, result })
    expect(headings().filter((h) => h.level === 1)).toHaveLength(1)
  })

  it('starts at h1', () => {
    renderPage({ wide, result: populated })
    expect(headings()[0].level).toBe(1)
  })

  it('skips no level', () => {
    renderPage({ wide, result: populated })
    const skip = findSkip(headings())
    expect(skip, `heading level skipped: ${skip}`).toBeNull()
  })

  it('keeps the h1 when the navigator tab is opened', async () => {
    // The regression this catches: the document title used to live inside the
    // findings panel, so switching tabs unmounted it and the page silently lost
    // its top-level heading.
    const { user } = renderPage({ wide, result: populated })
    await user.click(screen.getByRole('tab', { name: /navigator/i }))
    expect(headings().filter((h) => h.level === 1)).toHaveLength(1)
    expect(findSkip(headings())).toBeNull()
  })
})

describe('narrow viewport, document tab', () => {
  it('still has exactly one h1', async () => {
    const { user } = renderPage({ wide: false, result: populated })
    await user.click(screen.getByRole('tab', { name: 'Document' }))
    expect(headings().filter((h) => h.level === 1)).toHaveLength(1)
  })
})

describe('section headings inside the findings panel', () => {
  it('puts every top-level section at h2', () => {
    render(<ResultsPanel result={populated} onNavigate={() => {}} />)
    const byText = Object.fromEntries(headings().map((h) => [h.text, h.level]))
    expect(byText['Risk flags']).toBe(2)
    expect(byText['Possibly missing provisions']).toBe(2)
    expect(byText['Section summaries']).toBe(2)
  })

  it('does not own an h1 — that belongs to the page, not one of its panels', () => {
    render(<ResultsPanel result={populated} onNavigate={() => {}} />)
    expect(headings().filter((h) => h.level === 1)).toHaveLength(0)
  })
})

describe('tables and controls', () => {
  it('gives every table real column headers', () => {
    const { container } = render(<ResultsPanel result={populated} onNavigate={() => {}} />)
    const tables = [...container.querySelectorAll('table')]
    expect(tables.length).toBeGreaterThan(0)
    for (const table of tables) {
      expect(table.querySelectorAll('th[scope="col"]').length).toBeGreaterThan(0)
    }
  })

  it('gives every button an accessible name', () => {
    renderPage({ wide: true, result: populated })
    const unnamed = [...document.querySelectorAll('button')].filter(
      (b) => !(b.getAttribute('aria-label') || b.textContent.trim()),
    )
    expect(unnamed).toHaveLength(0)
  })
})
