import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DocumentHeader from '../components/DocumentHeader'
import { documentMeta } from './fixtures'

const renderHeader = (docOverrides = {}, hint = 'Commercial Lease') =>
  render(<DocumentHeader document={documentMeta(docOverrides)} documentTypeHint={hint} />)

describe('DocumentHeader', () => {
  it('names the document as the page heading', () => {
    renderHeader()
    expect(screen.getByRole('heading', { level: 1, name: 'sample_lease.pdf' })).toBeInTheDocument()
  })

  it('reports the page count', () => {
    renderHeader()
    expect(screen.getByText('6 pages')).toBeInTheDocument()
  })

  it('discloses when some pages had no readable text', () => {
    // A part-scanned document analyzed silently is the failure this prevents.
    renderHeader({ page_count: 6, pages_with_text: 5 })
    expect(screen.getByText('5 with readable text')).toBeInTheDocument()
  })

  it('says nothing about readable text when every page had some', () => {
    renderHeader({ page_count: 6, pages_with_text: 6 })
    expect(screen.queryByText(/with readable text/)).not.toBeInTheDocument()
  })

  it('shows the classification hint that conditioned every finding', () => {
    // Exposed rather than buried: it fed the missing-clause judgments in every
    // section, so a wrong hint should be visible.
    renderHeader({}, 'Commercial Lease')
    expect(screen.getByText('Commercial Lease')).toBeInTheDocument()
  })

  it('omits the hint when classification was not confident enough to use', () => {
    renderHeader({}, null)
    expect(screen.queryByText('Commercial Lease')).not.toBeInTheDocument()
  })

  it('discloses which extractor produced the text', () => {
    renderHeader({ extraction_method: 'pymupdf' })
    expect(screen.getByText('pymupdf')).toBeInTheDocument()
  })

  it('reports how many sections were analyzed', () => {
    renderHeader({ chunk_count: 4 })
    expect(screen.getByText('4 sections')).toBeInTheDocument()
  })
})
