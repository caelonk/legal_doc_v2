"""End-to-end: PDF bytes -> parser -> chunker -> analyzer prompt -> analyzer.

Covers the seams between components, which is where page attribution and the
request contract actually have to hold. No network: the Anthropic client is
stubbed, so this asserts the request we *would* send.

Run: python backend/tests/test_pipeline.py
"""

from __future__ import annotations

import asyncio
import sys
import types

from _harness import Results, make_mixed_pdf

from models.schemas import AnalyzedChunk, ChunkAnalysis, ChunkFailure, DocumentChunk
from prompts.analysis import build_chunk_prompt
from services import analyzer
from services.chunker import chunk_document_async
from services.parser import parse_pdf

CLAUSES = [
    "1. CONFIDENTIALITY. The Receiving Party shall hold all Confidential Information "
    "in strict confidence and shall not disclose it to any third party.",
    "2. LIMITATION OF LIABILITY. In no event shall either party be liable for indirect "
    "or consequential damages, provided that this limitation shall not apply to "
    "breaches of confidentiality, for which liability shall be unlimited.",
    "3. TERM. This Agreement commences on the Effective Date and continues for three "
    "(3) years, renewing automatically for successive one-year terms unless either "
    "party gives ninety (90) days written notice.",
    "4. INDEMNIFICATION. Each party shall indemnify and hold harmless the other from "
    "any claims arising out of its breach of this Agreement.",
]

GOOD = ChunkAnalysis(summary="S", risk_flags=[], missing_clauses=[], document_type="NDA")


def stub_response(stop_reason, parsed):
    return types.SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed)


class _FakeMessages:
    def __init__(self, script):
        self.script = script
        self.calls = 0
        self.seen: list[dict] = []

    async def parse(self, **kwargs):
        self.seen.append(kwargs)
        index = self.calls
        self.calls += 1
        await asyncio.sleep(0)
        return self.script[index]


class FakeClient:
    """Stands in for AsyncAnthropic — records the request, returns a scripted reply."""

    def __init__(self, script):
        self.messages = _FakeMessages(script)


def build_contract_pdf() -> bytes:
    """Six pages; page 5 is a scanned exhibit with no text layer."""
    bodies: list[str | None] = []
    for i in range(4):
        bodies.append("\n\n".join(CLAUSES[j % len(CLAUSES)] for j in range(i * 3, i * 3 + 6)))
    bodies.append(None)
    bodies.append("\n\n".join(CLAUSES))
    return make_mixed_pdf(bodies)


async def main() -> int:
    r = Results("pipeline")

    r.section("parse")
    doc = await parse_pdf(build_contract_pdf(), filename="nda_with_exhibit.pdf")
    r.check("six pages parsed", doc.page_count == 6, str(doc.page_count))
    r.check("scanned exhibit has no text", not doc.pages[4].text.strip())
    r.check("every other page has text",
            all(doc.pages[i].text.strip() for i in (0, 1, 2, 3, 5)))

    r.section("chunk")
    chunks = await chunk_document_async(doc, max_tokens=600, overlap_tokens=80)
    for c in chunks:
        print(f"      chunk {c.index}: ~{c.token_estimate:4d} tok, pages {c.page_numbers}, "
              f"contiguous={c.has_contiguous_pages}")
    r.check("chunks produced", len(chunks) > 1, f"{len(chunks)} chunks")
    r.check("no chunk over budget", all(c.token_estimate <= 600 for c in chunks))
    pages = sorted({p for c in chunks for p in c.page_numbers})
    r.check("scanned page never citable", 5 not in pages, f"pages={pages}")
    r.check("page after the gap is citable", 6 in pages, f"pages={pages}")

    r.section("prompt page-scoping")
    wrong = []
    for c in chunks:
        first_line = build_chunk_prompt(c).splitlines()[0]
        if not c.has_contiguous_pages:
            ok = "only" in first_line and all(str(p) in first_line for p in c.page_numbers)
        elif len(c.page_numbers) == 1:
            ok = f"on page {c.page_numbers[0]}" in first_line
        else:
            ok = "spans pages" in first_line
        if not ok:
            wrong.append(c.index)
    r.check("page scope wording matches chunk shape", not wrong, f"wrong={wrong}")

    gapped = [c for c in chunks if not c.has_contiguous_pages]
    if gapped:
        line = build_chunk_prompt(gapped[0]).splitlines()[0]
        r.check("gapped chunk enumerates rather than ranging", "only" in line, line[:70])
        r.check("gapped chunk omits the skipped page",
                not any(f" {p}" in line for p in [5] if p not in gapped[0].page_numbers),
                line[:70])

    r.section("prompt structure")
    prompt = build_chunk_prompt(chunks[0])
    r.check("section delimiters present", "<section>" in prompt and "</section>" in prompt)
    r.check("chunk text embedded", chunks[0].text.splitlines()[0][:30] in prompt)
    r.check("document_type_hint threads through",
            "NDA" in build_chunk_prompt(chunks[0], document_type_hint="NDA"))

    r.section("analyzer request contract")
    script = [stub_response("end_turn", GOOD) for _ in chunks]
    client = FakeClient(script)
    run = await analyzer.analyze_document(list(chunks), client=client, max_concurrency=2)
    sent = client.messages.seen[0]
    r.check("model pinned to sonnet 5", sent["model"] == "claude-sonnet-5", sent["model"])
    r.check("max_tokens is 4000", sent["max_tokens"] == 4000, str(sent["max_tokens"]))
    r.check("thinking set explicitly", sent["thinking"] == {"type": "adaptive"}, str(sent["thinking"]))
    r.check("effort is low", sent["output_config"] == {"effort": "low"}, str(sent["output_config"]))
    r.check("structured output bound to ChunkAnalysis", sent["output_format"] is ChunkAnalysis)
    r.check("no sampling parameters sent",
            not any(k in sent for k in ("temperature", "top_p", "top_k")))
    r.check("every chunk analyzed", len(run.analyzed) == len(chunks))
    r.check("no failures on the happy path", not run.failures)
    r.check("run is not partial", run.is_partial is False)

    r.section("failure handling")
    mixed = FakeClient([
        stub_response("end_turn", GOOD),
        stub_response("max_tokens", None),
        stub_response("refusal", None),
    ])
    three = [DocumentChunk(index=i, text=f"c{i}", page_numbers=[i + 1]) for i in range(3)]
    run = await analyzer.analyze_document(three, client=mixed, max_concurrency=3)
    r.check("successes collected", len(run.analyzed) == 1)
    r.check("failures collected, not dropped", len(run.failures) == 2)
    r.check("run reports partial", run.is_partial is True)
    r.check("total accounts for every chunk", run.total_chunks == 3)
    reasons = sorted(f.reason.value for f in run.failures)
    r.check("truncation and refusal kept distinct", reasons == ["REFUSED", "TRUNCATED"], str(reasons))
    r.check("user messages carry no diagnostics",
            all("stop_reason" not in f.user_message for f in run.failures))

    r.section("interpret_response branches")
    for label, resp, expected in [
        ("success", stub_response("end_turn", GOOD), AnalyzedChunk),
        ("refusal", stub_response("refusal", None), ChunkFailure),
        ("truncation", stub_response("max_tokens", None), ChunkFailure),
        ("truncation despite parsed output", stub_response("max_tokens", GOOD), ChunkFailure),
        ("missing parsed output", stub_response("end_turn", None), ChunkFailure),
    ]:
        got = analyzer.interpret_response(resp, 0)
        r.check(label, isinstance(got, expected), type(got).__name__)

    return r.finish()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
