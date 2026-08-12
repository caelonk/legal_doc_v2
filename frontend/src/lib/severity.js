/**
 * Severity ordering and counting.
 *
 * SEVERITY_RANK duplicates `RiskLevel.rank` in backend/models/schemas.py. That
 * duplication is deliberate — sorting is presentation, and the API deliberately
 * returns sections in document order rather than pre-sorting them — but it is
 * worth naming, because the failure it prevents is silent: sorting these values
 * alphabetically yields HIGH, LOW, MEDIUM, which looks plausible and is wrong.
 */
export const SEVERITY_RANK = { HIGH: 3, MEDIUM: 2, LOW: 1 }

export const SEVERITY_ORDER = ['HIGH', 'MEDIUM', 'LOW']

/**
 * Flatten every section's risk flags into one list, tagged with where each came
 * from so a citation can still be traced back to its section.
 *
 * NOTE: no de-duplication. Chunks overlap by 200 tokens, so a clause sitting on a
 * boundary can legitimately be reported by two sections. Merging them is a
 * document-level aggregation step that does not exist yet (recorded in the
 * AnalysisRun docstring); guessing at it here — by clause_type, say — would
 * quietly drop distinct findings that happen to share a name.
 */
export function collectRiskFlags(result) {
  if (!result) return []
  return result.sections.flatMap((section) =>
    section.analysis.risk_flags.map((flag, i) => ({
      ...flag,
      key: `${section.chunk_index}-${i}`,
      chunkIndex: section.chunk_index,
      sectionPages: section.pages,
    })),
  )
}

export function collectMissingClauses(result) {
  if (!result) return []
  return result.sections.flatMap((section) =>
    section.analysis.missing_clauses.map((clause, i) => ({
      ...clause,
      key: `${section.chunk_index}-${i}`,
      chunkIndex: section.chunk_index,
    })),
  )
}

/** Severity descending, then document position. "What is the worst thing in here." */
export function sortBySeverity(flags) {
  return [...flags].sort((a, b) => {
    const bySeverity = (SEVERITY_RANK[b.severity] ?? 0) - (SEVERITY_RANK[a.severity] ?? 0)
    if (bySeverity !== 0) return bySeverity
    // Unlocated findings sort last within their severity rather than first, which
    // is what `null` would do numerically.
    const pageA = a.page_reference ?? Number.MAX_SAFE_INTEGER
    const pageB = b.page_reference ?? Number.MAX_SAFE_INTEGER
    return pageA - pageB
  })
}

/**
 * Counts per severity. Shown as "3 high · 5 medium · 2 low" — never collapsed
 * into one overall document score, which would invite reliance on a figure
 * nothing in the pipeline validates (docs/ui-patterns.md §3).
 */
export function countBySeverity(flags) {
  const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 }
  for (const flag of flags) {
    if (flag.severity in counts) counts[flag.severity] += 1
  }
  return counts
}
