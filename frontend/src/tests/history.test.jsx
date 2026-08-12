import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import History from '../pages/History'
import StoredAnalysis from '../pages/StoredAnalysis'
import { deleteStoredAnalysis, getHistory, getStoredAnalysis } from '../api/client'
import { analysisResult, historyEntry } from './fixtures'

vi.mock('../api/client', () => ({
  getHistory: vi.fn(),
  getStoredAnalysis: vi.fn(),
  deleteStoredAnalysis: vi.fn(),
}))

/** A promise that never settles — the loading branch, held open. */
const pending = () => new Promise(() => {})

function renderHistory() {
  return render(
    <MemoryRouter initialEntries={['/history']}>
      <Routes>
        <Route path="/history" element={<History />} />
        <Route path="/history/:analysisId" element={<StoredAnalysis />} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderStored() {
  return render(
    <MemoryRouter initialEntries={['/history/7f82989b-c00f-48dd-9c37-05f9bf03dfaa']}>
      <Routes>
        <Route path="/history" element={<History />} />
        <Route path="/history/:analysisId" element={<StoredAnalysis />} />
      </Routes>
    </MemoryRouter>,
  )
}

const liveRegions = (container) => [...container.querySelectorAll('[aria-live]')]

beforeEach(() => vi.clearAllMocks())

describe('history list states', () => {
  it('does not claim an empty history while the request is in flight', async () => {
    // The failure this guards: rendering the empty state as the default and
    // letting the response correct it. For one paint the page tells a reader they
    // have never analysed anything, which is exactly the "unavailable is not
    // empty" mistake the API answers 503 to avoid.
    getHistory.mockReturnValue(pending())
    renderHistory()
    expect(screen.queryByText(/no saved analyses/i)).not.toBeInTheDocument()
  })

  it('shows placeholders shaped like the list while loading', () => {
    getHistory.mockReturnValue(pending())
    const { container } = renderHistory()
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('reports an unreachable store instead of an empty history', async () => {
    const error = new Error('Document history is temporarily unavailable.')
    getHistory.mockRejectedValue(error)
    renderHistory()

    expect(await screen.findByRole('alert')).toHaveTextContent(/temporarily unavailable/i)
    expect(screen.queryByText(/no saved analyses/i)).not.toBeInTheDocument()
  })

  it('shows an empty state with a way forward when there is genuinely nothing', async () => {
    getHistory.mockResolvedValue({ entries: [], limit: 25 })
    renderHistory()

    expect(await screen.findByText(/no saved analyses yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /analyze a document/i })).toHaveAttribute('href', '/')
  })

  it('has a live region in every branch', async () => {
    getHistory.mockResolvedValue({ entries: [historyEntry()], limit: 25 })
    const { container } = renderHistory()
    expect(liveRegions(container).length).toBeGreaterThan(0)
    await screen.findByText('sample_lease.pdf')
    expect(liveRegions(container).length).toBeGreaterThan(0)
  })
})

describe('history list contents', () => {
  beforeEach(() => {
    getHistory.mockResolvedValue({ entries: [historyEntry()], limit: 25 })
  })

  it('links each entry to its stored analysis', async () => {
    renderHistory()
    const link = await screen.findByRole('link', { name: /sample_lease\.pdf/ })
    expect(link).toHaveAttribute('href', '/history/7f82989b-c00f-48dd-9c37-05f9bf03dfaa')
  })

  it('shows counts rather than a risk score', async () => {
    renderHistory()
    const row = (await screen.findByRole('listitem'))
    expect(row).toHaveTextContent(/17 risk flags/)
    expect(row).toHaveTextContent(/2 missing/)
  })

  it('gives the save date a machine-readable timestamp', async () => {
    const { container } = renderHistory()
    await screen.findByText('sample_lease.pdf')
    expect(container.querySelector('time')).toHaveAttribute(
      'datetime',
      '2026-08-12T23:02:49.842308Z',
    )
  })

  it('discloses partial extraction', async () => {
    renderHistory()
    expect(await screen.findByText(/5 of 6 pages readable/)).toBeInTheDocument()
  })

  it('discloses skipped sections in the list, before the analysis is opened', async () => {
    // A finding count is misleading while part of the document was never
    // analysed, and most misleading when the count is low. Waiting until the
    // reader opens it is too late — they may never open it.
    getHistory.mockResolvedValue({
      entries: [historyEntry({ risk_flag_count: 0, skipped_count: 2 })],
      limit: 25,
    })
    renderHistory()
    expect(await screen.findByText(/2 sections could not be analyzed/i)).toBeInTheDocument()
  })

  it('renders no severity label, because it has no explanation to attach to one', async () => {
    // The list payload carries counts only. A HIGH badge here would be a bare
    // conclusion with no page reference and no explanation — forbidden by
    // .claude/rules/ai-output.md.
    renderHistory()
    const row = await screen.findByRole('listitem')
    expect(row).not.toHaveTextContent(/\b(HIGH|MEDIUM|LOW)\b/)
  })
})

describe('deleting from the list', () => {
  beforeEach(() => {
    getHistory.mockResolvedValue({ entries: [historyEntry()], limit: 25 })
  })

  it('never deletes on a single click', async () => {
    const user = userEvent.setup()
    renderHistory()
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    expect(deleteStoredAnalysis).not.toHaveBeenCalled()
    expect(screen.getByText(/delete permanently\?/i)).toBeInTheDocument()
  })

  it('can be backed out of', async () => {
    const user = userEvent.setup()
    renderHistory()
    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.queryByText(/delete permanently\?/i)).not.toBeInTheDocument()
    expect(deleteStoredAnalysis).not.toHaveBeenCalled()
  })

  it('removes the row and announces it once confirmed', async () => {
    const user = userEvent.setup()
    deleteStoredAnalysis.mockResolvedValue(undefined)
    const { container } = renderHistory()

    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    const confirm = screen.getByText(/delete permanently\?/i).parentElement
    await user.click(within(confirm).getByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(screen.queryByText('sample_lease.pdf')).not.toBeInTheDocument())
    expect(deleteStoredAnalysis).toHaveBeenCalledWith('7f82989b-c00f-48dd-9c37-05f9bf03dfaa')
    const announced = liveRegions(container).map((el) => el.textContent).join(' ')
    expect(announced).toMatch(/Deleted the saved analysis of sample_lease\.pdf/)
  })

  it('keeps the row when the delete fails', async () => {
    // Removing a row whose delete did not happen tells the reader their document
    // is gone when it is not. For a deletion control that is the one unacceptable
    // outcome, so the list is only edited after the API confirms.
    const user = userEvent.setup()
    deleteStoredAnalysis.mockRejectedValue(new Error('That analysis could not be deleted.'))
    renderHistory()

    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    const confirm = screen.getByText(/delete permanently\?/i).parentElement
    await user.click(within(confirm).getByRole('button', { name: /^delete$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be deleted/i)
    expect(screen.getByText('sample_lease.pdf')).toBeInTheDocument()
  })
})

describe('a stored analysis', () => {
  it('renders through the same view a finished job uses', async () => {
    getStoredAnalysis.mockResolvedValue(analysisResult())
    renderStored()

    // The provenance affordance, the persistent disclosure and the findings are
    // all present because this is the same component — not a read-only summary.
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('sample_lease.pdf')
    expect(screen.getByText(/AI-generated analysis\./i)).toBeInTheDocument()
    expect(screen.getByText('Indemnification')).toBeInTheDocument()
  })

  it('shows placeholders rather than a bare spinner while opening', () => {
    getStoredAnalysis.mockReturnValue(pending())
    const { container } = renderStored()
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders no findings when it could not be opened', async () => {
    // Same rule as a FAILED job: a load error is never rendered as an analysis
    // with nothing in it.
    getStoredAnalysis.mockRejectedValue(new Error('That saved analysis is no longer available.'))
    renderStored()

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      /could not be opened/i,
    )
    // Matched in two places on purpose: the visible paragraph and the live
    // region, which has to carry the reason too.
    expect(screen.getAllByText(/no longer available/i).length).toBeGreaterThan(1)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /back to document history/i })).toBeInTheDocument()
  })

  it('has a live region in every branch', async () => {
    getStoredAnalysis.mockReturnValue(pending())
    const { container } = renderStored()
    expect(liveRegions(container).length).toBeGreaterThan(0)
  })

  it('requires confirmation before deleting', async () => {
    const user = userEvent.setup()
    getStoredAnalysis.mockResolvedValue(analysisResult())
    renderStored()

    await user.click(await screen.findByRole('button', { name: /delete this analysis/i }))
    expect(deleteStoredAnalysis).not.toHaveBeenCalled()
    expect(screen.getByText(/delete permanently\?/i)).toBeInTheDocument()
  })

  it('returns to the history list after a successful delete', async () => {
    const user = userEvent.setup()
    getStoredAnalysis.mockResolvedValue(analysisResult())
    deleteStoredAnalysis.mockResolvedValue(undefined)
    getHistory.mockResolvedValue({ entries: [], limit: 25 })
    renderStored()

    await user.click(await screen.findByRole('button', { name: /delete this analysis/i }))
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(await screen.findByText(/no saved analyses yet/i)).toBeInTheDocument()
  })

  it('stays put and keeps the findings when the delete fails', async () => {
    const user = userEvent.setup()
    getStoredAnalysis.mockResolvedValue(analysisResult())
    deleteStoredAnalysis.mockRejectedValue(new Error('That analysis could not be deleted.'))
    renderStored()

    await user.click(await screen.findByRole('button', { name: /delete this analysis/i }))
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be deleted/i)
    expect(screen.getByText('Indemnification')).toBeInTheDocument()
  })
})

describe('heading structure', () => {
  it('gives the list exactly one h1 and no skipped level', async () => {
    getHistory.mockResolvedValue({ entries: [historyEntry()], limit: 25 })
    const { container } = renderHistory()
    await screen.findByText('sample_lease.pdf')

    const levels = [...container.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h) =>
      Number(h.tagName[1]),
    )
    expect(levels.filter((l) => l === 1)).toHaveLength(1)
    levels.reduce((previous, level) => {
      expect(level).toBeLessThanOrEqual(previous + 1)
      return Math.max(previous, level)
    }, 0)
  })
})
