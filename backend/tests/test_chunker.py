"""Chunker: budget invariants, page attribution, termination, content preservation.

Run: python backend/tests/test_chunker.py
"""

from __future__ import annotations

import sys

from _harness import Results, make_document

from services import chunker
from services.chunker import DEFAULT_CHUNK_TOKENS, chunk_document, estimate_tokens

PARA = (
    "The Receiving Party shall hold and maintain the Confidential Information in "
    "strictest confidence for the sole and exclusive benefit of the Disclosing Party, "
    "and shall not without prior written approval use it for its own benefit. "
)

# Counters deliberately unlike the character heuristic. Budget correctness must not
# depend on CHARS_PER_TOKEN happening to match the counter in use.
COUNTERS = {
    "default estimate": estimate_tokens,
    "1 token per char": lambda t: max(1, len(t)),
    "1 token per 10 chars": lambda t: max(1, len(t) // 10),
    "word count": lambda t: max(1, len(t.split())),
}


def main() -> int:
    r = Results("chunker")

    r.section("packing")
    pages = [(n, "\n\n".join(f"[p{n}s{i}] {PARA}" for i in range(12))) for n in range(1, 7)]
    chunks = chunk_document(make_document(pages))
    r.check("multiple chunks produced", len(chunks) > 1, f"{len(chunks)} chunks")
    r.check("indices sequential from zero",
            [c.index for c in chunks] == list(range(len(chunks))))
    r.check("no chunk exceeds the budget",
            all(c.token_estimate <= DEFAULT_CHUNK_TOKENS for c in chunks))
    r.check("re-measured text stays within budget",
            all(estimate_tokens(c.text) <= DEFAULT_CHUNK_TOKENS * 1.05 for c in chunks))
    r.check("every chunk carries pages", all(c.page_numbers for c in chunks))
    r.check("pages ascend within a chunk",
            all(c.page_numbers == sorted(c.page_numbers) for c in chunks))
    r.check("pages advance across chunks",
            all(chunks[i].start_page <= chunks[i + 1].start_page for i in range(len(chunks) - 1)))

    r.section("content preservation")
    markers = {f"[p{n}s{i}]" for n in range(1, 7) for i in range(12)}
    joined = "\n".join(c.text for c in chunks)
    missing = sorted(m for m in markers if m not in joined)
    r.check("no source paragraph is dropped", not missing, f"missing={missing[:5]}")

    r.section("overlap")
    shared = sum(1 for a, b in zip(chunks, chunks[1:]) if a.text[-80:] in b.text)
    r.check("consecutive chunks share trailing text",
            shared >= len(chunks) - 2, f"{shared}/{max(len(chunks) - 1, 1)} boundaries")
    no_overlap = chunk_document(make_document(pages), overlap_tokens=0)
    r.check("zero overlap is allowed", len(no_overlap) > 1)

    r.section("page attribution across a text-layer gap")
    gap = chunk_document(make_document([(1, PARA), (2, "   "), (3, PARA)]),
                         max_tokens=400, overlap_tokens=50)
    seen = sorted({p for c in gap for p in c.page_numbers})
    r.check("page with no text is never citable", 2 not in seen, f"pages={seen}")
    r.check("pages that do have text remain citable", seen == [1, 3], f"pages={seen}")
    spanning = [c for c in gap if len(c.page_numbers) > 1]
    if spanning:
        r.check("gap flagged via has_contiguous_pages",
                all(not c.has_contiguous_pages for c in spanning))

    r.section("inline page markers")
    # The model reads these to attribute a finding to a page. Before they existed
    # it was told the page range and left to guess position within it, which put
    # 11 of 13 citations on the wrong page in a live run — all inside the allowed
    # range, so no range check could catch them.
    marked = chunk_document(make_document(pages))
    for chunk in marked:
        present = {n for n in range(1, 8) if f"[page {n}]" in chunk.text}
        if not r.check(
            f"chunk {chunk.index} markers match its page_numbers",
            present == set(chunk.page_numbers),
            f"markers={sorted(present)} pages={chunk.page_numbers}",
        ):
            break

    r.check(
        "every chunk opens with a marker",
        all(c.text.startswith("[page ") for c in marked),
    )
    r.check(
        "a marker precedes every page transition, not just the first",
        all(
            c.text.count("[page ") == len(c.page_numbers)
            for c in marked
        ),
    )

    # A chunk drawn from one page needs exactly one marker; the model should not
    # have to read a marker per paragraph.
    single = chunk_document(make_document([(4, "\n\n".join([PARA] * 5))]))
    r.check("single-page chunk carries one marker", single[0].text.count("[page ") == 1)
    r.check("marker names the real page", single[0].text.startswith("[page 4]"))

    # The gap document again: page 2 has no text, so no marker may name it.
    gap_marked = chunk_document(
        make_document([(1, PARA), (2, "   "), (3, PARA)]), max_tokens=400, overlap_tokens=50
    )
    r.check(
        "a page with no text layer is never marked",
        all("[page 2]" not in c.text for c in gap_marked),
    )

    r.check(
        "markers do not push a chunk over budget",
        all(estimate_tokens(c.text) <= DEFAULT_CHUNK_TOKENS for c in marked),
        f"max={max(estimate_tokens(c.text) for c in marked)}",
    )

    r.section("budget invariants under adversarial counters")
    body = [(1, PARA * 40), (2, "Q" * 5000), (3, PARA * 40)]
    for name, fn in COUNTERS.items():
        for max_tokens, overlap in [(300, 40), (1000, 100)]:
            cs = chunk_document(make_document(body), max_tokens=max_tokens,
                                overlap_tokens=overlap, token_counter=fn)
            over = [(c.index, fn(c.text)) for c in cs if fn(c.text) > max_tokens]
            r.check(f"{name} @ max={max_tokens}", not over, f"offenders={over[:3]}")

    r.section("segment cap: overlap + one segment can never exceed the budget")
    for max_tokens, overlap in [(500, 50), (3000, 200), (120, 20), (64, 1)]:
        limit = max_tokens - overlap
        segs = chunker._build_segments(make_document([(1, "Z" * 20000)]), limit, estimate_tokens)
        worst = max((s.tokens for s in segs), default=0)
        r.check(f"segments <= {limit} (max={max_tokens}, overlap={overlap})",
                worst <= limit, f"worst={worst}")

    r.section("termination")
    blob = chunk_document(make_document([(1, "A" * 60000)]), max_tokens=500, overlap_tokens=50)
    r.check("unbroken blob terminates", len(blob) > 0, f"{len(blob)} chunks")
    r.check("blob chunks respect budget", all(c.token_estimate <= 500 for c in blob))
    r.check("blob content preserved", sum(c.text.count("A") for c in blob) >= 60000)

    r.section("forward progress")
    uniq = "\n\n".join(f"Clause-{i:03d} obligations under this agreement." for i in range(80))
    cs = chunk_document(make_document([(1, uniq)]), max_tokens=250, overlap_tokens=60)
    tags = lambda t: {w for w in t.split() if w.startswith("Clause-")}  # noqa: E731
    stalled = [i + 1 for i, (a, b) in enumerate(zip(cs, cs[1:])) if not (tags(b.text) - tags(a.text))]
    r.check("every chunk introduces new content", not stalled, f"stalled={stalled[:5]}")
    r.check("all clauses covered", len({w for c in cs for w in tags(c.text)}) == 80)
    r.check("chunk count stays sane", 1 < len(cs) < 500, f"{len(cs)} chunks")

    r.section("edge cases")
    r.check("empty document yields no chunks", chunk_document(make_document([])) == [])
    r.check("whitespace-only document yields no chunks",
            chunk_document(make_document([(1, "  \n\n ")])) == [])
    tiny = chunk_document(make_document([(1, "Short clause.")]))
    r.check("tiny document yields one chunk", len(tiny) == 1)
    r.check("tiny chunk still carries its page", tiny and tiny[0].page_numbers == [1])

    r.section("configuration validation")
    for label, kwargs in [
        ("overlap equal to max is rejected", {"max_tokens": 100, "overlap_tokens": 100}),
        ("overlap above max is rejected", {"max_tokens": 100, "overlap_tokens": 200}),
        ("negative overlap is rejected", {"max_tokens": 100, "overlap_tokens": -1}),
        ("zero max_tokens is rejected", {"max_tokens": 0}),
    ]:
        try:
            chunk_document(make_document(pages), **kwargs)
            r.check(label, False, "no ValueError raised")
        except ValueError:
            r.check(label, True)

    return r.finish()


if __name__ == "__main__":
    sys.exit(main())
