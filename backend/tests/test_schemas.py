"""Schema contract: what structured outputs actually guarantees API-side.

These assert on the generated JSON schema, not just on Python-level validation —
the generated schema is what constrains the model, so a regression there weakens
the guarantee silently.

Run: python backend/tests/test_schemas.py
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
    DocumentChunk,
    RiskFlag,
    RiskLevel,
)


def main() -> int:
    r = Results("schemas")
    schema = ChunkAnalysis.model_json_schema()
    defs = schema["$defs"]
    risk_flag = defs["RiskFlag"]

    r.section("structured-output requirements")
    r.check("top level forbids extra properties", schema.get("additionalProperties") is False)
    r.check("RiskFlag forbids extra properties", risk_flag.get("additionalProperties") is False)
    r.check("MissingClause forbids extra properties",
            defs["MissingClause"].get("additionalProperties") is False)

    r.section("page_reference cannot be silently omitted")
    r.check("page_reference is required", "page_reference" in risk_flag["required"])
    r.check("page_reference is nullable integer",
            risk_flag["properties"]["page_reference"].get("anyOf")
            == [{"type": "integer"}, {"type": "null"}])
    try:
        RiskFlag(clause_type="X", severity="HIGH", explanation="Y")
        r.check("omitting page_reference is rejected", False, "it was accepted")
    except Exception as exc:
        r.check("omitting page_reference is rejected", True, type(exc).__name__)
    ok = RiskFlag(clause_type="X", severity="HIGH", explanation="Y", page_reference=None)
    r.check("explicit null is accepted", ok.page_reference is None)

    r.section("severity is a closed enum")
    r.check("enum values exactly HIGH/MEDIUM/LOW",
            defs["RiskLevel"]["enum"] == ["HIGH", "MEDIUM", "LOW"])
    try:
        RiskFlag(clause_type="X", severity="CRITICAL", explanation="Y", page_reference=None)
        r.check("off-enum severity rejected", False, "it was accepted")
    except Exception:
        r.check("off-enum severity rejected", True)

    r.section("severity ordering")
    levels = [RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.MEDIUM]
    ranked = [x.value for x in sorted(levels, key=lambda v: v.rank, reverse=True)]
    r.check("rank sorts HIGH, MEDIUM, LOW", ranked == ["HIGH", "MEDIUM", "LOW"], str(ranked))
    r.check("alphabetical sort would be wrong (why rank exists)",
            sorted(v.value for v in levels) == ["HIGH", "LOW", "MEDIUM"])

    r.section("DocumentChunk page derivation")
    gapped = DocumentChunk(index=0, text="t", page_numbers=[4, 6])
    r.check("start_page derived", gapped.start_page == 4)
    r.check("end_page derived", gapped.end_page == 6)
    r.check("gap detected", gapped.has_contiguous_pages is False)
    r.check("contiguous detected",
            DocumentChunk(index=1, text="t", page_numbers=[2, 3, 4]).has_contiguous_pages is True)
    r.check("single page is contiguous",
            DocumentChunk(index=2, text="t", page_numbers=[9]).has_contiguous_pages is True)
    empty = DocumentChunk(index=3, text="t")
    r.check("no pages yields None", empty.start_page is None and empty.end_page is None)

    r.section("AnalysisRun accounting")
    run = AnalysisRun(
        analyzed=[AnalyzedChunk(
            chunk_index=0,
            analysis=ChunkAnalysis(summary="s", risk_flags=[], missing_clauses=[],
                                   document_type="NDA"),
        )],
        failures=[ChunkFailure(chunk_index=1, reason=ChunkFailureReason.TRUNCATED,
                               user_message="too long", detail="stop_reason=max_tokens")],
    )
    r.check("total counts successes and failures", run.total_chunks == 2)
    r.check("is_partial when anything failed", run.is_partial is True)
    r.check("clean run is not partial",
            AnalysisRun(analyzed=[], failures=[]).is_partial is False)
    r.check("truncation and invalid output are distinct reasons",
            ChunkFailureReason.TRUNCATED != ChunkFailureReason.INVALID_OUTPUT)

    return r.finish()


if __name__ == "__main__":
    sys.exit(main())
