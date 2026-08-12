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
 * The document-level findings.
 *
 * Read from `result.aggregate`, which the backend produces in
 * services/aggregator.py — NOT re-derived from `result.sections`. Chunks overlap
 * by 200 tokens, so a clause on a boundary is reported by two sections, and the
 * merge rules that decide when two reports are one finding are subtle enough to
 * deserve one implementation with its own tests rather than a second guess here.
 * `sections` remains on the wire as the evidence behind the merge.
 *
 * `chunkIndex` is the earliest reporting section, which keeps document-position
 * sorting working on merged findings.
 */
export function collectRiskFlags(result) {
  if (!result?.aggregate) return []
  return result.aggregate.risk_flags.map((flag, i) => ({
    ...flag,
    key: `flag-${i}`,
    chunkIndex: flag.reported_by[0] ?? 0,
  }))
}

export function collectMissingClauses(result) {
  if (!result?.aggregate) return []
  return result.aggregate.missing_clauses.map((clause, i) => ({
    ...clause,
    key: `missing-${i}`,
    chunkIndex: clause.reported_by[0] ?? 0,
  }))
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
 * Document order: page ascending, unlocated findings last.
 *
 * Deliberately a DIFFERENT order from sortBySeverity. The risk table answers
 * "what is the worst thing in here", so it leads with severity. ClauseNavigator
 * answers "where are the problems as I read through", so it follows the document.
 * Presenting both in the same order would make the navigator redundant.
 *
 * Unlocated findings still sort last rather than being dropped — they are listed
 * under their own heading, because a finding with no page is still a finding.
 */
export function sortByDocumentPosition(flags) {
  return [...flags].sort((a, b) => {
    const pageA = a.page_reference ?? Number.MAX_SAFE_INTEGER
    const pageB = b.page_reference ?? Number.MAX_SAFE_INTEGER
    if (pageA !== pageB) return pageA - pageB
    // Same page: fall back to the order the analyzer reported them in, which
    // follows position within the section.
    return a.chunkIndex - b.chunkIndex
  })
}

/** Findings the parser could place, and those it could not. */
export function partitionByLocated(flags) {
  return {
    located: flags.filter((f) => f.page_reference !== null && f.page_reference !== undefined),
    unlocated: flags.filter((f) => f.page_reference === null || f.page_reference === undefined),
  }
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
