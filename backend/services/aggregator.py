"""Merge per-section analysis into one document-level view.

The gap this closes was recorded in AnalysisRun's docstring from the start:
chunks overlap by 200 tokens, so a clause sitting on a boundary is analyzed twice
and reported twice, and `document_type` can differ between sections.

ONE PRINCIPLE GOVERNS EVERY RULE HERE, and it is worth stating before the code:

    Over-merging deletes a finding. Under-merging shows a duplicate.

Those are not symmetric. A duplicate is visible, mildly annoying, and the reader
can see both entries. A wrongly merged pair is a risk that silently disappears —
the same class of harm as dropping a chunk, in a product whose stated worst
outcome is saying "no risks found" when there are some. So every rule below is
deliberately conservative: when the evidence for "these are the same finding" is
anything less than strong, both survive.

Nothing here calls the API. It is pure, synchronous, and testable without network
access, which is what lets the merge rules be pinned by unit tests rather than
inspected by eye.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict

from models.schemas import (
    AggregatedMissingClause,
    AggregatedRiskFlag,
    AnalysisRun,
    DocumentAggregate,
    MissingClause,
    RiskFlag,
    RiskLevel,
)

logger = logging.getLogger(__name__)

_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def _normalize_label(text: str) -> str:
    """Fold a clause label to a comparison key.

    Case, surrounding punctuation and spacing vary between sections for what is
    plainly the same label ("Indemnification" / "INDEMNIFICATION."). Nothing
    cleverer than that: no stemming, no fuzzy distance, no synonym table. A fuzzy
    match that fires wrongly merges two distinct clauses, and per the principle at
    the top of this module that is the expensive direction to be wrong.
    """
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", text)).strip().lower()


def _merge_flag_group(group: list[tuple[int, RiskFlag]]) -> AggregatedRiskFlag:
    """Collapse flags already established to be the same finding.

    Severity is the maximum, never an average. A clause one section called HIGH
    does not become MEDIUM because another section was more relaxed, and the
    disagreement itself is reported rather than smoothed away.

    The explanation comes from the most severe report, tie-broken by document
    order, because that is the reading the severity now reflects.
    """
    severities = {flag.severity for _, flag in group}
    best_severity = max(severities, key=lambda level: level.rank)

    # Document order within the winning severity.
    chosen = min(
        (item for item in group if item[1].severity is best_severity),
        key=lambda item: item[0],
    )[1]

    return AggregatedRiskFlag(
        clause_type=chosen.clause_type,
        severity=best_severity,
        explanation=chosen.explanation,
        page_reference=chosen.page_reference,
        reported_by=sorted(index for index, _ in group),
        severity_disagreement=len(severities) > 1,
    )


def _group_unlocated(items: list[tuple[int, RiskFlag]]) -> list[list[tuple[int, RiskFlag]]]:
    """Split same-named unlocated flags into runs of ADJACENT sections.

    With no page number there is no positional evidence that two same-named
    findings are one clause — except adjacency, which is the only way the chunk
    overlap can produce a duplicate in the first place. Two unlocated
    "Indemnification" flags from sections 0 and 4 are far more likely to be two
    separate indemnity clauses, and merging them would delete one.
    """
    runs: list[list[tuple[int, RiskFlag]]] = []
    for item in sorted(items, key=lambda pair: pair[0]):
        if runs and item[0] - runs[-1][-1][0] <= 1:
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def _aggregate_risk_flags(
    run: AnalysisRun,
) -> tuple[list[AggregatedRiskFlag], int]:
    """Merge duplicate risk flags. Returns the merged list and how many vanished.

    Two reports are the same finding when their clause labels match AND either:

      * they cite the SAME page — the overlap reproduces identical text, so both
        sections cite the page that text is on; or
      * neither cites a page and they come from ADJACENT sections, which is the
        only shape the overlap can produce.

    Different pages means different clauses, and one-null-one-numbered stays
    unmerged: it could be the same clause with a lost citation, but "could be" is
    not enough to delete a finding over.
    """
    ordered: list[tuple[int, RiskFlag]] = [
        (analyzed.chunk_index, flag)
        for analyzed in sorted(run.analyzed, key=lambda a: a.chunk_index)
        for flag in analyzed.analysis.risk_flags
    ]

    # Bucketed by label, page, AND the report's ordinal within its own section.
    #
    # The ordinal matters: duplication comes from the OVERLAP, which is strictly
    # between sections. If one section reports "Limitation of Liability" on page 6
    # twice, those are two provisions it found, not one it stuttered on — a page
    # can carry two. Without the ordinal they would collapse into one and a real
    # finding would vanish.
    #
    # Pairing by ordinal also preserves multiplicity across the overlap: two
    # reports in section 0 and the same two in section 1 merge to two, not one.
    seen_in_chunk: dict[tuple[int, str, int | None], int] = defaultdict(int)
    buckets: dict[tuple[str, int | None, int], list[tuple[int, RiskFlag]]] = defaultdict(list)

    for index, flag in ordered:
        label = _normalize_label(flag.clause_type)
        occurrence_key = (index, label, flag.page_reference)
        ordinal = seen_in_chunk[occurrence_key]
        seen_in_chunk[occurrence_key] += 1
        buckets[(label, flag.page_reference, ordinal)].append((index, flag))

    groups: list[list[tuple[int, RiskFlag]]] = []
    for (_, page, _ordinal), items in buckets.items():
        if page is None:
            groups.extend(_group_unlocated(items))
        else:
            groups.append(items)

    # Document order: earliest reporting section, then page, then label. Sorting
    # for display is the frontend's job; this only needs to be deterministic.
    groups.sort(
        key=lambda group: (
            min(index for index, _ in group),
            group[0][1].page_reference if group[0][1].page_reference is not None else 1 << 30,
            _normalize_label(group[0][1].clause_type),
        )
    )

    merged = [_merge_flag_group(group) for group in groups]
    removed = len(ordered) - len(merged)

    if removed:
        logger.info(
            "aggregation merged %s duplicate risk flag(s) across the chunk overlap "
            "(%s reports -> %s findings)",
            removed,
            len(ordered),
            len(merged),
        )
    return merged, removed


def _aggregate_missing_clauses(
    run: AnalysisRun, risk_flags: list[AggregatedRiskFlag]
) -> tuple[list[AggregatedMissingClause], list[str]]:
    """Merge absence claims and drop the ones the document contradicts.

    Merging is unconditional here: unlike a risk flag, a missing-clause claim is
    about the whole document rather than a location, so two sections naming the
    same provision are making one claim, not two.

    The contradiction check is the useful part. A risk flag is grounded in text
    that EXISTS; a missing clause is an inference that some text does not. When a
    section reports "Governing Law" missing and another section raises a risk flag
    about a "Governing Law" clause, the provision demonstrably exists somewhere in
    the document and the absence claim is simply wrong.
    `.claude/rules/ai-output.md` already ranks these two claim types, so the
    stronger one wins — but the suppressed names are returned so the UI can say so
    rather than quietly showing a shorter list.
    """
    present_clause_types = {_normalize_label(flag.clause_type) for flag in risk_flags}

    buckets: dict[str, list[tuple[int, MissingClause]]] = defaultdict(list)
    for analyzed in sorted(run.analyzed, key=lambda a: a.chunk_index):
        for clause in analyzed.analysis.missing_clauses:
            buckets[_normalize_label(clause.clause_name)].append((analyzed.chunk_index, clause))

    merged: list[AggregatedMissingClause] = []
    contradicted: list[str] = []

    for key, items in buckets.items():
        importances = {clause.importance for _, clause in items}
        best = max(importances, key=lambda level: level.rank)
        chosen = min(
            (item for item in items if item[1].importance is best), key=lambda item: item[0]
        )[1]

        if key in present_clause_types:
            contradicted.append(chosen.clause_name)
            continue

        merged.append(
            AggregatedMissingClause(
                clause_name=chosen.clause_name,
                importance=best,
                explanation=chosen.explanation,
                reported_by=sorted(index for index, _ in items),
            )
        )

    merged.sort(key=lambda clause: (-clause.importance.rank, clause.clause_name.lower()))
    contradicted.sort(key=str.lower)

    if contradicted:
        logger.info(
            "aggregation withheld %s missing-clause claim(s) contradicted by a risk "
            "flag elsewhere in the document: %s",
            len(contradicted),
            contradicted,
        )
    return merged, contradicted


def _reconcile_document_type(run: AnalysisRun) -> tuple[str | None, int]:
    """Pick one document type from what the sections each concluded.

    Majority vote. Ties break toward the classification pre-pass's answer when it
    is one of the candidates — it read the opening of the document, where the type
    is usually stated outright, which is better evidence than a mid-document
    section inferring from clauses. Otherwise the earliest section wins, so the
    result is deterministic rather than dict-order dependent.
    """
    labels = [
        (analyzed.chunk_index, analyzed.analysis.document_type)
        for analyzed in sorted(run.analyzed, key=lambda a: a.chunk_index)
        if analyzed.analysis.document_type.strip()
    ]
    if not labels:
        return run.document_type_hint, 0

    counts = Counter(_normalize_label(label) for _, label in labels)
    top = max(counts.values())
    tied = [key for key, count in counts.items() if count == top]

    winner = tied[0]
    if len(tied) > 1:
        hint_key = _normalize_label(run.document_type_hint or "")
        if hint_key in tied:
            winner = hint_key
        else:
            winner = next(_normalize_label(label) for _, label in labels if _normalize_label(label) in tied)

    # Report the spelling a section actually used, not the folded key.
    original = next(label for _, label in labels if _normalize_label(label) == winner)
    return original, counts[winner]


def aggregate_run(run: AnalysisRun) -> DocumentAggregate:
    """Build the document-level view from per-section results.

    Never raises on an empty or fully failed run: a run where every chunk failed is
    reported as FAILED upstream, and this returning an empty aggregate rather than
    blowing up keeps that path simple.
    """
    risk_flags, removed = _aggregate_risk_flags(run)
    missing_clauses, contradicted = _aggregate_missing_clauses(run, risk_flags)
    document_type, agreement = _reconcile_document_type(run)

    return DocumentAggregate(
        # Carried through, never composed here. Producing it takes an API call and
        # this module is pure by design — that is what makes every merge rule
        # above testable without a network. `analyzer.summarize_document` owns it.
        summary=run.document_summary,
        document_type=document_type,
        document_type_agreement=agreement,
        sections_analyzed=len(run.analyzed),
        risk_flags=risk_flags,
        missing_clauses=missing_clauses,
        merged_duplicate_count=removed,
        contradicted_missing_clauses=contradicted,
    )
