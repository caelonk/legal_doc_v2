"""Document-level aggregation: merging, reconciliation, and what must NOT merge.

The must-NOT-merge cases carry as much weight here as the must-merge ones. Over-
merging deletes a finding, which is the same class of harm as dropping a chunk;
under-merging shows a duplicate, which is visible and recoverable. A test suite
that only proves things collapse would be pushing on the dangerous side.

Run: python backend/tests/test_aggregator.py
"""

from __future__ import annotations

import sys

from _harness import Results

from models.schemas import (
    AnalysisRun,
    AnalyzedChunk,
    ChunkAnalysis,
    ChunkFailure,
    ChunkFailureReason,
    MissingClause,
    RiskFlag,
    RiskLevel,
)
from services.aggregator import aggregate_run


def flag(clause_type, severity=RiskLevel.HIGH, page=1, explanation="Because of the text."):
    return RiskFlag(
        clause_type=clause_type,
        severity=severity,
        explanation=explanation,
        page_reference=page,
    )


def missing(clause_name, importance=RiskLevel.MEDIUM, explanation="Normally present."):
    return MissingClause(
        clause_name=clause_name, importance=importance, explanation=explanation
    )


def chunk(index, *, flags=(), missing_clauses=(), document_type="Commercial Lease"):
    return AnalyzedChunk(
        chunk_index=index,
        analysis=ChunkAnalysis(
            summary="S",
            risk_flags=list(flags),
            missing_clauses=list(missing_clauses),
            document_type=document_type,
        ),
    )


def run_of(*chunks, hint=None, failures=()):
    return AnalysisRun(analyzed=list(chunks), failures=list(failures), document_type_hint=hint)


def main() -> int:
    r = Results("aggregator")

    # ------------------------------------------------------- merging duplicates
    r.section("merging duplicates from the chunk overlap")

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", page=4)]),
            chunk(1, flags=[flag("Indemnification", page=4)]),
        )
    )
    r.check("same clause on the same page merges", len(agg.risk_flags) == 1)
    r.check("merge count is reported", agg.merged_duplicate_count == 1)
    r.check(
        "both reporting sections are recorded",
        agg.risk_flags[0].reported_by == [0, 1],
        str(agg.risk_flags[0].reported_by),
    )

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("INDEMNIFICATION.", page=4)]),
            chunk(1, flags=[flag("Indemnification", page=4)]),
        )
    )
    r.check("labels differing only by case and punctuation merge", len(agg.risk_flags) == 1)

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", page=None)]),
            chunk(1, flags=[flag("Indemnification", page=None)]),
        )
    )
    r.check("unlocated duplicates from ADJACENT sections merge", len(agg.risk_flags) == 1)

    # ------------------------------------------------- what must NOT merge
    r.section("findings that must survive intact")

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", page=4)]),
            chunk(1, flags=[flag("Indemnification", page=7)]),
        )
    )
    r.check(
        "same clause name on DIFFERENT pages stays two findings",
        len(agg.risk_flags) == 2,
        "two indemnity clauses in one lease is ordinary",
    )

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", page=4)]),
            chunk(1, flags=[flag("Indemnification", page=None)]),
        )
    )
    r.check(
        "one located and one unlocated stay separate",
        len(agg.risk_flags) == 2,
        "could be the same clause, but 'could be' is not enough to delete one",
    )

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", page=None)]),
            chunk(1),
            chunk(2),
            chunk(3, flags=[flag("Indemnification", page=None)]),
        )
    )
    r.check(
        "unlocated duplicates from DISTANT sections stay separate",
        len(agg.risk_flags) == 2,
        "the overlap can only duplicate across adjacent chunks",
    )

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", page=4), flag("Holdover", page=4)]),
        )
    )
    r.check("different clauses on the same page stay separate", len(agg.risk_flags) == 2)

    agg = aggregate_run(run_of(chunk(0, flags=[flag("A", page=1), flag("A", page=1)])))
    r.check(
        "a section reporting the same clause twice is left alone",
        len(agg.risk_flags) == 2,
        "the overlap is between sections; within one, two reports are two findings",
    )

    # ------------------------------------------------------ severity handling
    r.section("severity when sections disagree")

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", RiskLevel.MEDIUM, page=4)]),
            chunk(1, flags=[flag("Indemnification", RiskLevel.HIGH, page=4)]),
        )
    )
    r.check("merged severity is the highest reported", agg.risk_flags[0].severity is RiskLevel.HIGH)
    r.check("the disagreement is surfaced", agg.risk_flags[0].severity_disagreement is True)

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("Indemnification", RiskLevel.HIGH, page=4)]),
            chunk(1, flags=[flag("Indemnification", RiskLevel.HIGH, page=4)]),
        )
    )
    r.check("agreement is not flagged as disagreement", agg.risk_flags[0].severity_disagreement is False)

    agg = aggregate_run(
        run_of(
            chunk(0, flags=[flag("X", RiskLevel.LOW, page=1, explanation="mild")]),
            chunk(1, flags=[flag("X", RiskLevel.HIGH, page=1, explanation="severe")]),
        )
    )
    r.check(
        "the explanation comes from the most severe report",
        agg.risk_flags[0].explanation == "severe",
        agg.risk_flags[0].explanation,
    )

    # ------------------------------------------------------- missing clauses
    r.section("missing clauses")

    agg = aggregate_run(
        run_of(
            chunk(0, missing_clauses=[missing("Governing Law")]),
            chunk(1, missing_clauses=[missing("Governing Law")]),
            chunk(2, missing_clauses=[missing("Governing Law")]),
        )
    )
    r.check("the same absence claim merges to one", len(agg.missing_clauses) == 1)
    r.check("all reporting sections recorded", agg.missing_clauses[0].reported_by == [0, 1, 2])

    agg = aggregate_run(
        run_of(
            chunk(0, missing_clauses=[missing("Governing Law", RiskLevel.LOW)]),
            chunk(1, missing_clauses=[missing("Governing Law", RiskLevel.HIGH)]),
        )
    )
    r.check("importance is the highest reported", agg.missing_clauses[0].importance is RiskLevel.HIGH)

    agg = aggregate_run(
        run_of(
            chunk(0, missing_clauses=[missing("Governing Law")]),
            chunk(1, missing_clauses=[missing("Casualty")]),
        )
    )
    r.check("different provisions stay separate", len(agg.missing_clauses) == 2)

    # ------------------------------------------------ contradiction resolution
    r.section("absence claims contradicted by the document itself")

    agg = aggregate_run(
        run_of(
            chunk(0, missing_clauses=[missing("Governing Law")]),
            chunk(1, flags=[flag("Governing Law", page=6)]),
        )
    )
    r.check(
        "a provision another section flagged is not reported missing",
        agg.missing_clauses == [],
        "a risk flag is grounded in text that exists; absence is only an inference",
    )
    r.check(
        "the withheld claim is named, not silently dropped",
        agg.contradicted_missing_clauses == ["Governing Law"],
        str(agg.contradicted_missing_clauses),
    )
    r.check("the risk flag itself survives", len(agg.risk_flags) == 1)

    agg = aggregate_run(
        run_of(
            chunk(0, missing_clauses=[missing("Governing Law")]),
            chunk(1, flags=[flag("Indemnification", page=6)]),
        )
    )
    r.check(
        "an unrelated risk flag does not suppress an absence claim",
        len(agg.missing_clauses) == 1 and agg.contradicted_missing_clauses == [],
    )

    # ------------------------------------------------- document type
    r.section("document type reconciliation")

    agg = aggregate_run(
        run_of(
            chunk(0, document_type="Commercial Lease"),
            chunk(1, document_type="Commercial Lease"),
            chunk(2, document_type="NDA"),
        )
    )
    r.check("majority wins", agg.document_type == "Commercial Lease")
    r.check("agreement is counted", agg.document_type_agreement == 2)
    r.check("sections analyzed is reported", agg.sections_analyzed == 3)

    agg = aggregate_run(
        run_of(
            chunk(0, document_type="NDA"),
            chunk(1, document_type="Commercial Lease"),
            hint="Commercial Lease",
        )
    )
    r.check(
        "a tie breaks toward the classification pre-pass",
        agg.document_type == "Commercial Lease",
        "it read the opening, where the type is usually stated outright",
    )

    agg = aggregate_run(
        run_of(chunk(0, document_type="NDA"), chunk(1, document_type="Lease"), hint=None)
    )
    r.check("a tie with no hint is deterministic, earliest section wins", agg.document_type == "NDA")

    agg = aggregate_run(
        run_of(
            chunk(0, document_type="commercial lease"),
            chunk(1, document_type="Commercial Lease"),
        )
    )
    r.check("case variants count as one type", agg.document_type_agreement == 2)
    r.check(
        "the reported spelling is one a section actually used",
        agg.document_type in ("commercial lease", "Commercial Lease"),
    )

    # ----------------------------------------------------------- edge cases
    r.section("edge cases")

    agg = aggregate_run(run_of())
    r.check("an empty run aggregates to an empty view", agg.risk_flags == [])
    r.check("empty run has no document type", agg.document_type is None)
    r.check("empty run reports zero sections", agg.sections_analyzed == 0)

    agg = aggregate_run(
        run_of(
            chunk(0),
            failures=[
                ChunkFailure(
                    chunk_index=1,
                    reason=ChunkFailureReason.TRUNCATED,
                    user_message="Too long.",
                    detail="internal",
                )
            ],
        )
    )
    r.check("failed chunks do not contribute findings", agg.risk_flags == [])
    r.check("failed chunks are not counted as analyzed", agg.sections_analyzed == 1)

    agg = aggregate_run(run_of(chunk(0, document_type="   ")))
    r.check("a blank document type is ignored", agg.document_type_agreement == 0)

    agg = aggregate_run(run_of(chunk(0, flags=[flag("A", page=9), flag("B", page=2)])))
    r.check(
        "output ordering is deterministic",
        [f.clause_type for f in aggregate_run(run_of(chunk(0, flags=[flag("A", page=9), flag("B", page=2)]))).risk_flags]
        == [f.clause_type for f in agg.risk_flags],
    )

    r.section("nothing is invented")
    big = run_of(
        chunk(0, flags=[flag("A", page=1), flag("B", page=2)]),
        chunk(1, flags=[flag("C", page=3)]),
    )
    agg = aggregate_run(big)
    r.check("no finding appears that no section reported", len(agg.risk_flags) == 3)
    r.check(
        "merged count plus output equals input",
        len(agg.risk_flags) + agg.merged_duplicate_count == 3,
    )

    return r.finish()


if __name__ == "__main__":
    sys.exit(main())
