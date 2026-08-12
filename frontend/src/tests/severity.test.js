import { describe, expect, it } from 'vitest'
import {
  collectMissingClauses,
  collectRiskFlags,
  countBySeverity,
  partitionByLocated,
  sortByDocumentPosition,
  sortBySeverity,
} from '../lib/severity'
import { analysisResult, missingClause, riskFlag, section } from './fixtures'

const flag = (severity, page) => riskFlag({ severity, page_reference: page })

describe('sortBySeverity', () => {
  it('orders HIGH before MEDIUM before LOW', () => {
    const sorted = sortBySeverity([flag('LOW', 1), flag('HIGH', 1), flag('MEDIUM', 1)])
    expect(sorted.map((f) => f.severity)).toEqual(['HIGH', 'MEDIUM', 'LOW'])
  })

  it('is not alphabetical', () => {
    // The failure this guards is silent: sorting these strings alphabetically
    // yields HIGH, LOW, MEDIUM, which looks plausible and buries the mediums
    // under the lows.
    const sorted = sortBySeverity([flag('MEDIUM', 1), flag('LOW', 1), flag('HIGH', 1)])
    expect(sorted.map((f) => f.severity)).not.toEqual(['HIGH', 'LOW', 'MEDIUM'])
  })

  it('orders by page within one severity', () => {
    const sorted = sortBySeverity([flag('HIGH', 9), flag('HIGH', 2), flag('HIGH', 5)])
    expect(sorted.map((f) => f.page_reference)).toEqual([2, 5, 9])
  })

  it('puts unlocated findings LAST within their severity, not first', () => {
    // A null page must not sort as page zero. It is "we could not place this",
    // not "this is at the very start of the document".
    const sorted = sortBySeverity([flag('HIGH', null), flag('HIGH', 3), flag('HIGH', 1)])
    expect(sorted.map((f) => f.page_reference)).toEqual([1, 3, null])
  })

  it('keeps an unlocated HIGH above a located MEDIUM', () => {
    // Severity always wins over locatability: a serious finding we cannot place
    // still outranks a minor one we can.
    const sorted = sortBySeverity([flag('MEDIUM', 1), flag('HIGH', null)])
    expect(sorted.map((f) => f.severity)).toEqual(['HIGH', 'MEDIUM'])
  })

  it('does not mutate its input', () => {
    const input = [flag('LOW', 1), flag('HIGH', 1)]
    sortBySeverity(input)
    expect(input.map((f) => f.severity)).toEqual(['LOW', 'HIGH'])
  })
})

describe('sortByDocumentPosition', () => {
  const at = (page, chunkIndex = 0) => ({ ...riskFlag({ page_reference: page }), chunkIndex })

  it('orders by page ascending', () => {
    const sorted = sortByDocumentPosition([at(9), at(2), at(5)])
    expect(sorted.map((f) => f.page_reference)).toEqual([2, 5, 9])
  })

  it('ignores severity entirely', () => {
    // The navigator's whole purpose is the other axis. If severity leaked into
    // this ordering it would become a second copy of the risk table.
    const high = { ...riskFlag({ severity: 'HIGH', page_reference: 9 }), chunkIndex: 0 }
    const low = { ...riskFlag({ severity: 'LOW', page_reference: 1 }), chunkIndex: 0 }
    expect(sortByDocumentPosition([high, low]).map((f) => f.severity)).toEqual(['LOW', 'HIGH'])
  })

  it('falls back to section order within a page', () => {
    const sorted = sortByDocumentPosition([at(3, 2), at(3, 0), at(3, 1)])
    expect(sorted.map((f) => f.chunkIndex)).toEqual([0, 1, 2])
  })

  it('puts unlocated findings last', () => {
    const sorted = sortByDocumentPosition([at(null), at(4), at(1)])
    expect(sorted.map((f) => f.page_reference)).toEqual([1, 4, null])
  })

  it('does not mutate its input', () => {
    const input = [at(9), at(1)]
    sortByDocumentPosition(input)
    expect(input.map((f) => f.page_reference)).toEqual([9, 1])
  })
})

describe('partitionByLocated', () => {
  it('separates findings with a page from those without', () => {
    const { located, unlocated } = partitionByLocated([
      riskFlag({ page_reference: 3 }),
      riskFlag({ page_reference: null }),
      riskFlag({ page_reference: undefined }),
    ])
    expect(located).toHaveLength(1)
    expect(unlocated).toHaveLength(2)
  })

  it('keeps page 0 on the located side', () => {
    // Guards the falsy-check bug: 0 is a page number, not a missing one.
    const { located } = partitionByLocated([riskFlag({ page_reference: 0 })])
    expect(located).toHaveLength(1)
  })

  it('loses nothing', () => {
    const flags = [riskFlag({ page_reference: 1 }), riskFlag({ page_reference: null })]
    const { located, unlocated } = partitionByLocated(flags)
    expect(located.length + unlocated.length).toBe(flags.length)
  })
})

describe('countBySeverity', () => {
  it('counts each band', () => {
    const counts = countBySeverity([flag('HIGH', 1), flag('HIGH', 2), flag('LOW', 1)])
    expect(counts).toEqual({ HIGH: 2, MEDIUM: 0, LOW: 1 })
  })

  it('reports zeros rather than omitting empty bands', () => {
    expect(countBySeverity([])).toEqual({ HIGH: 0, MEDIUM: 0, LOW: 0 })
  })
})

describe('collecting findings across sections', () => {
  const result = analysisResult({
    sections: [
      section({ chunk_index: 0, pages: [1], risk_flags: [flag('HIGH', 1), flag('LOW', 1)] }),
      section({ chunk_index: 1, pages: [2], risk_flags: [flag('MEDIUM', 2)] }),
    ],
  })

  it('flattens every section', () => {
    expect(collectRiskFlags(result)).toHaveLength(3)
  })

  it('gives every finding a unique key', () => {
    const keys = collectRiskFlags(result).map((f) => f.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('tags each finding with the section it came from', () => {
    expect(collectRiskFlags(result).map((f) => f.chunkIndex)).toEqual([0, 0, 1])
  })

  it('does NOT de-duplicate across the chunk overlap', () => {
    // Chunks overlap by 200 tokens, so a clause on a boundary is legitimately
    // reported twice. Merging is a document-level aggregation step that does not
    // exist yet; collapsing by clause_type here would silently drop distinct
    // findings that happen to share a name.
    const duplicated = analysisResult({
      sections: [
        section({ chunk_index: 0, risk_flags: [riskFlag({ clause_type: 'Indemnification' })] }),
        section({ chunk_index: 1, risk_flags: [riskFlag({ clause_type: 'Indemnification' })] }),
      ],
    })
    expect(collectRiskFlags(duplicated)).toHaveLength(2)
  })

  it('handles a null result', () => {
    expect(collectRiskFlags(null)).toEqual([])
    expect(collectMissingClauses(null)).toEqual([])
  })

  it('collects missing clauses separately from risk flags', () => {
    const mixed = analysisResult({
      sections: [section({ risk_flags: [flag('HIGH', 1)], missing_clauses: [missingClause()] })],
    })
    expect(collectRiskFlags(mixed)).toHaveLength(1)
    expect(collectMissingClauses(mixed)).toHaveLength(1)
  })
})
