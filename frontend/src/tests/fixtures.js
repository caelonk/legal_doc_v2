/**
 * Builders for API-shaped objects.
 *
 * The counterpart to backend/tests/_harness.py::make_document. Everything is
 * constructed in code rather than loaded from a recorded response, so a test says
 * what it depends on and a fixture cannot quietly drift from the assertion that
 * relies on it.
 *
 * Shapes mirror backend/models/schemas.py exactly: SkippedSection has no `detail`
 * field, because that never crosses the wire.
 */

export function riskFlag(overrides = {}) {
  return {
    clause_type: 'Indemnification',
    severity: 'HIGH',
    explanation: 'Tenant indemnifies Landlord for the Landlord’s own negligence.',
    page_reference: 4,
    ...overrides,
  }
}

export function missingClause(overrides = {}) {
  return {
    clause_name: 'Governing Law',
    importance: 'MEDIUM',
    explanation: 'No governing law provision appears in this section.',
    ...overrides,
  }
}

export function section(overrides = {}) {
  const { risk_flags, missing_clauses, summary, document_type, ...rest } = overrides
  return {
    chunk_index: 0,
    pages: [1, 2],
    analysis: {
      summary: summary ?? 'This section is heavily one-sided.',
      risk_flags: risk_flags ?? [riskFlag()],
      missing_clauses: missing_clauses ?? [missingClause()],
      document_type: document_type ?? 'Commercial Lease',
    },
    ...rest,
  }
}

export function documentMeta(overrides = {}) {
  return {
    filename: 'sample_lease.pdf',
    size_bytes: 11049,
    page_count: 6,
    pages_with_text: 5,
    extraction_method: 'pdfplumber',
    chunk_count: 2,
    ...overrides,
  }
}

export function analysisResult(overrides = {}) {
  return {
    document: documentMeta(),
    document_type_hint: 'Commercial Lease',
    pages: [
      { page_number: 1, text: 'COMMERCIAL LEASE AGREEMENT' },
      { page_number: 2, text: '3. TERM AND RENEWAL.' },
      { page_number: 3, text: '' },
    ],
    sections: [section()],
    skipped: [],
    ...overrides,
  }
}

export function jobState(overrides = {}) {
  return {
    job_id: 'abc123',
    status: 'COMPLETE',
    stage_message: 'Analysis complete',
    completed_chunks: 2,
    total_chunks: 2,
    document: documentMeta(),
    result: analysisResult(),
    error: null,
    ...overrides,
  }
}
