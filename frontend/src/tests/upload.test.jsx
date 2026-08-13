import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import UploadZone from '../components/UploadZone'

/**
 * The upload disclosure is a factual claim about where a confidential contract
 * goes. It said "not written to disk and not stored" for as long as that was true;
 * the moment the backend began saving analyses it became a lie, and nothing would
 * have caught it. These are the tests that catch it.
 *
 * They assert MEANING, not wording — that the copy names storage, names the
 * retention the server reports, and never claims the document is not saved while
 * it is. Wording can be improved without touching this file; the claims cannot
 * change without it.
 */

const noop = () => {}

function disclosure() {
  // The lock icon's paragraph. Matched by content rather than by test id so the
  // test breaks if the sentence disappears, not just if a hook is renamed.
  return screen.getByText(/Anthropic API/i).closest('p')
}

describe('upload disclosure', () => {
  it('never claims the document is not saved when history is available', () => {
    render(<UploadZone onSubmit={noop} storage={{ available: true, retentionDays: 30 }} />)
    expect(disclosure()).not.toHaveTextContent(/not stored|never stored|not saved to/i)
  })

  it('says the text and findings are saved', () => {
    render(<UploadZone onSubmit={noop} storage={{ available: true, retentionDays: 30 }} />)
    expect(disclosure()).toHaveTextContent(/saved to your document history/i)
  })

  it('states the retention period the server reports, not a hardcoded one', () => {
    // The number must come from /api/health, which serves config.HISTORY_RETENTION_DAYS.
    // A constant in the component would keep promising 30 days after the server
    // moved to 90.
    render(<UploadZone onSubmit={noop} storage={{ available: true, retentionDays: 90 }} />)
    expect(disclosure()).toHaveTextContent(/90 days/)
    expect(disclosure()).not.toHaveTextContent(/30 days/)
  })

  it('says the PDF itself is never saved', () => {
    // True by construction: no storage bucket is involved anywhere in the backend.
    render(<UploadZone onSubmit={noop} storage={{ available: true, retentionDays: 30 }} />)
    expect(disclosure()).toHaveTextContent(/PDF file itself is never saved/i)
  })

  it('switches to the not-saved wording when the server stores nothing', () => {
    render(<UploadZone onSubmit={noop} storage={{ available: false }} />)
    expect(disclosure()).toHaveTextContent(/not saved/i)
    expect(disclosure()).not.toHaveTextContent(/document history/i)
  })

  // Both spellings of "not loaded yet", because the caller has no reason to care
  // which one it sends. `null` is what Home actually passes — `health && {...}`
  // before the request settles — and it used to CRASH the whole landing page,
  // while the `undefined` case passed happily. One value tested is not the rule
  // tested.
  it.each([
    ['undefined', undefined],
    ['null', null],
  ])('assumes storage while health is still loading (%s)', (_label, storage) => {
    // Over-stating retention is the safe direction to be wrong. Telling someone
    // their contract is not saved when it is, is not.
    render(<UploadZone onSubmit={noop} storage={storage} />)
    expect(disclosure()).toHaveTextContent(/saved to your document history/i)
    expect(disclosure()).not.toHaveTextContent(/held in memory for that analysis only/i)
  })

  it('omits a retention number rather than inventing one', () => {
    render(<UploadZone onSubmit={noop} />)
    expect(disclosure()).not.toHaveTextContent(/\d+ days/)
  })

  it('renders at all with no storage information', () => {
    // The regression this pins is not a wording problem — it is a white screen.
    // Destructuring null in the parameter list threw before anything rendered.
    expect(() => render(<UploadZone onSubmit={noop} storage={null} />)).not.toThrow()
    expect(screen.getByText(/Drag a PDF here/i)).toBeInTheDocument()
  })

  it('keeps the disclosure beside the control, not behind an interaction', () => {
    // docs/ui-patterns.md §5: trust copy belongs at the moment of hesitation. It
    // must be present with no file chosen and nothing expanded.
    render(<UploadZone onSubmit={noop} storage={{ available: true, retentionDays: 30 }} />)
    expect(disclosure()).toBeVisible()
  })
})
