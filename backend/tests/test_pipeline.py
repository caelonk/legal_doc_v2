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

import anthropic
import httpx

from _harness import Results, make_mixed_pdf

from config import (
    CLASSIFICATION_SAMPLE_CHARS,
    MAX_TOKENS_PER_CHUNK,
    TRUNCATION_RETRY_MAX_TOKENS,
)

from pydantic import ValidationError

from models.schemas import (
    AnalyzedChunk,
    ChunkAnalysis,
    ChunkFailure,
    ChunkFailureReason,
    Confidence,
    DocumentChunk,
    DocumentTypeGuess,
)
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


WEAK_GUESS = DocumentTypeGuess(document_type="", confidence=Confidence.LOW)
STRONG_GUESS = DocumentTypeGuess(document_type="Commercial Lease", confidence=Confidence.HIGH)


class _FakeMessages:
    """Dispatches on output_format so classification and chunk calls stay separable."""

    def __init__(self, chunk_script, classification):
        self.chunk_script = chunk_script
        self.classification = classification
        self.chunk_calls = 0
        self.seen: list[dict] = []

    async def parse(self, **kwargs):
        self.seen.append(kwargs)
        await asyncio.sleep(0)
        if kwargs.get("output_format") is DocumentTypeGuess:
            if isinstance(self.classification, Exception):
                raise self.classification
            return self.classification
        index = self.chunk_calls
        self.chunk_calls += 1
        scripted = self.chunk_script[index]
        if isinstance(scripted, Exception):
            raise scripted
        return scripted

    @property
    def chunk_requests(self) -> list[dict]:
        return [k for k in self.seen if k.get("output_format") is ChunkAnalysis]

    @property
    def classification_requests(self) -> list[dict]:
        return [k for k in self.seen if k.get("output_format") is DocumentTypeGuess]


class FakeClient:
    """Stands in for AsyncAnthropic — records requests, returns scripted replies.

    Classification defaults to a LOW-confidence guess, i.e. no hint, so tests that
    are not about classification see unhinted chunk prompts.
    """

    def __init__(self, chunk_script, classification=None):
        if classification is None:
            classification = stub_response("end_turn", WEAK_GUESS)
        self.messages = _FakeMessages(chunk_script, classification)


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
    sent = client.messages.chunk_requests[0]
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
    # Retry disabled so the truncated chunk stays a failure — this section is about
    # how failures are collected and kept distinct, not about recovery.
    run = await analyzer.analyze_document(
        three, client=mixed, max_concurrency=3, retry_on_truncation=False
    )
    r.check("successes collected", len(run.analyzed) == 1)
    r.check("failures collected, not dropped", len(run.failures) == 2)
    r.check("run reports partial", run.is_partial is True)
    r.check("total accounts for every chunk", run.total_chunks == 3)
    reasons = sorted(f.reason.value for f in run.failures)
    r.check("truncation and refusal kept distinct", reasons == ["REFUSED", "TRUNCATED"], str(reasons))
    r.check("user messages carry no diagnostics",
            all("stop_reason" not in f.user_message for f in run.failures))

    r.section("document-type classification pre-pass")
    three = [DocumentChunk(index=i, text=f"clause text {i}", page_numbers=[i + 1])
             for i in range(3)]

    def fresh(classification=None):
        return FakeClient([stub_response("end_turn", GOOD) for _ in three], classification)

    # Confident guess reaches every chunk.
    client = fresh(stub_response("end_turn", STRONG_GUESS))
    await analyzer.analyze_document(three, client=client, max_concurrency=3)
    reqs = client.messages.chunk_requests
    prompts = [q["messages"][0]["content"] for q in reqs]
    r.check("classification call was made", len(client.messages.classification_requests) == 1)
    r.check("hint reaches every chunk",
            all("Commercial Lease" in p for p in prompts), f"{len(prompts)} prompts")
    r.check("hint is hedged, not asserted",
            all("appeared to be" in p for p in prompts))

    cls_req = client.messages.classification_requests[0]
    r.check("classifier uses the lightweight model",
            cls_req["model"] == "claude-haiku-4-5-20251001", cls_req["model"])
    r.check("chunks still use the analysis model", reqs[0]["model"] == "claude-sonnet-5")
    # Both verified against the live API for Haiku 4.5: effort 400s, adaptive
    # thinking 400s, disabled is accepted. See config.py.
    r.check("classifier sends no effort", "output_config" not in cls_req)
    r.check("classifier disables thinking explicitly",
            cls_req.get("thinking") == {"type": "disabled"}, str(cls_req.get("thinking")))
    r.check("classifier never sends adaptive thinking",
            cls_req.get("thinking", {}).get("type") != "adaptive")
    r.check("classifier sends no sampling params",
            not any(k in cls_req for k in ("temperature", "top_p", "top_k")))
    r.check("classifier bound to DocumentTypeGuess",
            cls_req["output_format"] is DocumentTypeGuess)

    # Weak guess must not propagate.
    client = fresh(stub_response("end_turn", WEAK_GUESS))
    await analyzer.analyze_document(three, client=client, max_concurrency=3)
    r.check("LOW confidence produces no hint",
            not any("appeared to be" in q["messages"][0]["content"]
                    for q in client.messages.chunk_requests))

    # A confident-but-empty type is still no answer.
    client = fresh(stub_response("end_turn",
                                 DocumentTypeGuess(document_type="  ",
                                                   confidence=Confidence.HIGH)))
    await analyzer.analyze_document(three, client=client, max_concurrency=3)
    r.check("blank type produces no hint",
            not any("appeared to be" in q["messages"][0]["content"]
                    for q in client.messages.chunk_requests))

    # Truncated classification is not trusted.
    client = fresh(stub_response("max_tokens", STRONG_GUESS))
    await analyzer.analyze_document(three, client=client, max_concurrency=3)
    r.check("truncated classification produces no hint",
            not any("Commercial Lease" in q["messages"][0]["content"]
                    for q in client.messages.chunk_requests))

    # Classification failure must never fail the document.
    boom = anthropic.APIStatusError(
        "boom", response=httpx.Response(500, request=httpx.Request("POST", "https://x")),
        body=None,
    )
    client = fresh(boom)
    run = await analyzer.analyze_document(three, client=client, max_concurrency=3)
    r.check("classification failure does not fail the run", len(run.analyzed) == 3)
    r.check("classification failure yields no hint",
            not any("appeared to be" in q["messages"][0]["content"]
                    for q in client.messages.chunk_requests))

    # Opt-outs.
    client = fresh(stub_response("end_turn", STRONG_GUESS))
    await analyzer.analyze_document(three, client=client, classify=False)
    r.check("classify=False skips the call",
            not client.messages.classification_requests)

    client = fresh(stub_response("end_turn", STRONG_GUESS))
    await analyzer.analyze_document(three, client=client, document_type_hint="Sublease")
    r.check("explicit hint skips classification",
            not client.messages.classification_requests)
    r.check("explicit hint is the one used",
            all("Sublease" in q["messages"][0]["content"]
                for q in client.messages.chunk_requests))

    r.section("classifier standalone contract")
    r.check("no chunks yields no classification",
            await analyzer.classify_document_type(fresh(), []) is None)
    blank = [DocumentChunk(index=0, text="   ", page_numbers=[1])]
    r.check("blank text yields no classification",
            await analyzer.classify_document_type(fresh(), blank) is None)
    sample = analyzer._classification_sample(
        [DocumentChunk(index=i, text="X" * 5000, page_numbers=[i + 1]) for i in range(4)]
    )
    r.check("sample is capped at the configured budget",
            len(sample) <= CLASSIFICATION_SAMPLE_CHARS + 8, f"{len(sample)} chars")
    r.check("sample draws from more than the first chunk",
            analyzer._classification_sample(
                [DocumentChunk(index=0, text="AAA", page_numbers=[1]),
                 DocumentChunk(index=1, text="BBB", page_numbers=[2])]
            ) == "AAA\n\nBBB")

    r.section("truncation surfacing as a parse failure")
    # The SDK validates while constructing the response, so a truncated payload
    # raises ValidationError and stop_reason never reaches interpret_response.
    # Both ValidationError shapes are produced by real pydantic, not hand-built,
    # so the branch is tested against the exception the SDK will actually raise.
    truncated_json = '{"summary":"This clause limits liability and'
    try:
        ChunkAnalysis.model_validate_json(truncated_json)
        cut_short = None
    except ValidationError as exc:
        cut_short = exc
    r.check("truncated JSON raises ValidationError", cut_short is not None)
    r.check("truncation is recognised", analyzer._is_truncated_json(cut_short) is True)

    try:
        ChunkAnalysis.model_validate_json(
            '{"summary":"s","risk_flags":[],"missing_clauses":[],"document_type":123}'
        )
        schema_violation = None
    except ValidationError as exc:
        schema_violation = exc
    r.check("schema violation raises ValidationError", schema_violation is not None)
    r.check("schema violation is NOT called truncation",
            analyzer._is_truncated_json(schema_violation) is False)

    # retry_on_truncation=False isolates the classification of a single attempt;
    # the retry behaviour itself is covered in its own section below.
    client = FakeClient([cut_short])
    outcome = await analyzer.analyze_chunk(
        client, DocumentChunk(index=7, text="t", page_numbers=[1]),
        retry_on_truncation=False,
    )
    r.check("truncated parse becomes a ChunkFailure", isinstance(outcome, ChunkFailure))
    r.check("classified TRUNCATED, not INVALID_OUTPUT",
            outcome.reason is ChunkFailureReason.TRUNCATED, outcome.reason.value)
    r.check("truncation user message matches the budget wording",
            "too long" in outcome.user_message, outcome.user_message)

    client = FakeClient([schema_violation])
    outcome = await analyzer.analyze_chunk(
        client, DocumentChunk(index=8, text="t", page_numbers=[1])
    )
    r.check("schema violation stays INVALID_OUTPUT",
            outcome.reason is ChunkFailureReason.INVALID_OUTPUT, outcome.reason.value)
    r.check("schema violation is not retried",
            len(client.messages.chunk_requests) == 1,
            f"{len(client.messages.chunk_requests)} calls")

    r.section("retry after truncation")
    c = DocumentChunk(index=4, text="t", page_numbers=[1])

    # json_invalid truncation, then success.
    client = FakeClient([cut_short, stub_response("end_turn", GOOD)])
    outcome = await analyzer.analyze_chunk(client, c)
    reqs = client.messages.chunk_requests
    r.check("truncated chunk is retried", len(reqs) == 2, f"{len(reqs)} calls")
    r.check("retry recovers the chunk", isinstance(outcome, AnalyzedChunk))
    r.check("first attempt uses the normal budget",
            reqs[0]["max_tokens"] == MAX_TOKENS_PER_CHUNK, str(reqs[0]["max_tokens"]))
    r.check("retry uses the larger budget",
            reqs[1]["max_tokens"] == TRUNCATION_RETRY_MAX_TOKENS, str(reqs[1]["max_tokens"]))
    r.check("retry keeps the same model", reqs[1]["model"] == reqs[0]["model"])
    r.check("retry keeps the same prompt",
            reqs[1]["messages"][0]["content"] == reqs[0]["messages"][0]["content"])

    # stop_reason truncation (parse succeeded but output was cut) also retries.
    client = FakeClient([stub_response("max_tokens", None), stub_response("end_turn", GOOD)])
    outcome = await analyzer.analyze_chunk(client, c)
    r.check("stop_reason truncation also retries",
            len(client.messages.chunk_requests) == 2)
    r.check("stop_reason truncation recovers", isinstance(outcome, AnalyzedChunk))

    # Truncating twice gives up rather than escalating.
    client = FakeClient([cut_short, cut_short])
    outcome = await analyzer.analyze_chunk(client, c)
    r.check("retries at most once", len(client.messages.chunk_requests) == 2)
    r.check("persistent truncation reported as TRUNCATED",
            outcome.reason is ChunkFailureReason.TRUNCATED, outcome.reason.value)
    r.check("detail records that a retry happened",
            "after truncation retry" in outcome.detail, outcome.detail[:60])
    r.check("detail names the retry budget",
            str(TRUNCATION_RETRY_MAX_TOKENS) in outcome.detail)
    r.check("user message stays plain",
            "max_tokens" not in outcome.user_message, outcome.user_message)

    # A different failure on the retry keeps its own reason.
    client = FakeClient([cut_short, schema_violation])
    outcome = await analyzer.analyze_chunk(client, c)
    r.check("retry failing differently keeps that reason",
            outcome.reason is ChunkFailureReason.INVALID_OUTPUT, outcome.reason.value)

    # Non-truncation failures are not retried.
    for label, first in [
        ("refusal", stub_response("refusal", None)),
        ("schema violation", schema_violation),
        ("rate limit", anthropic.RateLimitError(
            "slow down",
            response=httpx.Response(429, request=httpx.Request("POST", "https://x")),
            body=None)),
    ]:
        client = FakeClient([first, stub_response("end_turn", GOOD)])
        await analyzer.analyze_chunk(client, c)
        r.check(f"{label} is not retried",
                len(client.messages.chunk_requests) == 1,
                f"{len(client.messages.chunk_requests)} calls")

    # Opt-out.
    client = FakeClient([cut_short, stub_response("end_turn", GOOD)])
    outcome = await analyzer.analyze_chunk(client, c, retry_on_truncation=False)
    r.check("retry_on_truncation=False makes one call",
            len(client.messages.chunk_requests) == 1)
    r.check("retry_on_truncation=False still reports TRUNCATED",
            outcome.reason is ChunkFailureReason.TRUNCATED)

    # The flag threads through analyze_document.
    client = FakeClient([cut_short, stub_response("end_turn", GOOD)])
    run = await analyzer.analyze_document([c], client=client, classify=False)
    r.check("analyze_document retries by default", len(run.analyzed) == 1)
    client = FakeClient([cut_short])
    run = await analyzer.analyze_document(
        [c], client=client, classify=False, retry_on_truncation=False
    )
    r.check("analyze_document honours retry_on_truncation=False",
            len(run.failures) == 1 and len(client.messages.chunk_requests) == 1)

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
