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

/**
 * A pass-through aggregate: every section's findings, none merged.
 *
 * Derived from the sections a test actually supplies, so a fixture cannot drift
 * from the findings it claims to summarise. Tests about MERGING pass an explicit
 * `aggregate` — the real merge rules are pinned in backend/tests/test_aggregator.py,
 * where they belong, rather than reimplemented here.
 */
export function passthroughAggregate(sections, hint = null) {
  return {
    document_type: sections[0]?.analysis.document_type ?? hint,
    document_type_agreement: sections.length,
    sections_analyzed: sections.length,
    risk_flags: sections.flatMap((s) =>
      s.analysis.risk_flags.map((flag) => ({
        ...flag,
        reported_by: [s.chunk_index],
        severity_disagreement: false,
      })),
    ),
    missing_clauses: sections.flatMap((s) =>
      s.analysis.missing_clauses.map((clause) => ({
        ...clause,
        reported_by: [s.chunk_index],
      })),
    ),
    merged_duplicate_count: 0,
    contradicted_missing_clauses: [],
  }
}

export function analysisResult(overrides = {}) {
  const base = {
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
  return {
    ...base,
    aggregate:
      overrides.aggregate ?? passthroughAggregate(base.sections, base.document_type_hint),
  }
}

/**
 * One row of GET /api/documents/history.
 *
 * Summary fields ONLY — mirrors models.schemas.HistoryEntry, which deliberately
 * omits the analysis and the document text. A fixture carrying `result` here
 * would let a test pass against a list page that renders findings it will never
 * actually receive.
 */
export function historyEntry(overrides = {}) {
  return {
    id: '7f82989b-c00f-48dd-9c37-05f9bf03dfaa',
    created_at: '2026-08-12T23:02:49.842308Z',
    filename: 'sample_lease.pdf',
    page_count: 6,
    pages_with_text: 5,
    document_type: 'Commercial Lease',
    risk_flag_count: 17,
    missing_clause_count: 2,
    skipped_count: 0,
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
