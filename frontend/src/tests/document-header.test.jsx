import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DocumentHeader from '../components/DocumentHeader'
import { documentMeta } from './fixtures'

const renderHeader = (docOverrides = {}, documentType = 'Commercial Lease', typeAgreement) =>
  render(
    <DocumentHeader
      document={documentMeta(docOverrides)}
      documentType={documentType}
      typeAgreement={typeAgreement}
    />,
  )

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

  it('shows the reconciled document type', () => {
    // The type the SECTIONS agreed on, reconciled in services/aggregator.py —
    // not the pre-pass hint. The hint conditioned the analysis; the sections then
    // read the actual clauses.
    renderHeader({}, 'Commercial Lease')
    expect(screen.getByText('Commercial Lease')).toBeInTheDocument()
  })

  it('omits the type when nothing could be reconciled', () => {
    renderHeader({}, null)
    expect(screen.queryByText('Commercial Lease')).not.toBeInTheDocument()
  })

  it('discloses the split when sections disagreed on the type', () => {
    renderHeader({}, 'Commercial Lease', { agreeing: 3, total: 4 })
    expect(screen.getByText('3 of 4 sections')).toBeInTheDocument()
  })

  it('says nothing about agreement when every section agreed', () => {
    // Unanimity is the normal case; reporting it would be noise on every document.
    renderHeader({}, 'Commercial Lease', { agreeing: 4, total: 4 })
    expect(screen.queryByText(/of 4 sections/)).not.toBeInTheDocument()
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
