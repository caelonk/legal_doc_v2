"""Parser: extraction, page attribution, and every failure mode.

Run: python backend/tests/test_parser.py
"""

from __future__ import annotations

import asyncio
import sys

from _harness import Results, make_image_only_pdf, make_mixed_pdf, make_text_pdf

from services.parser import ParserError, parse_pdf

CLAUSE = (
    "CONFIDENTIALITY AGREEMENT\n\n"
    "1. The Receiving Party shall hold all Confidential Information in strict confidence.\n\n"
    "2. This Agreement shall be governed by the laws of the State of Delaware.\n"
)


async def expect_error(r: Results, label: str, data: bytes, fragment: str) -> None:
    try:
        await parse_pdf(data, filename="x.pdf")
        r.check(label, False, "no ParserError raised")
    except ParserError as exc:
        r.check(label, fragment.lower() in exc.user_message.lower(), exc.user_message)
        r.check(f"{label}: detail kept off user message", exc.detail != exc.user_message)


async def main() -> int:
    r = Results("parser")

    r.section("extraction")
    doc = await parse_pdf(make_text_pdf([CLAUSE] * 3), filename="nda.pdf")
    r.check("all pages returned", doc.page_count == 3, str(doc.page_count))
    r.check("all pages have text", doc.pages_with_text == 3)
    r.check("text was extracted", doc.total_characters > 100, str(doc.total_characters))
    r.check("filename preserved", doc.filename == "nda.pdf")

    r.section("page attribution")
    doc = await parse_pdf(
        make_text_pdf(["ALPHA only here.", "BETA only here.", "GAMMA only here."]),
        filename="pages.pdf",
    )
    r.check("page numbers are 1-indexed and ordered",
            [p.page_number for p in doc.pages] == [1, 2, 3])
    r.check("page 1 holds only its own text", "ALPHA" in doc.pages[0].text and "BETA" not in doc.pages[0].text)
    r.check("page 2 holds only its own text", "BETA" in doc.pages[1].text and "GAMMA" not in doc.pages[1].text)
    r.check("page 3 holds only its own text", "GAMMA" in doc.pages[2].text and "ALPHA" not in doc.pages[2].text)

    r.section("partial text layer is non-fatal")
    doc = await parse_pdf(make_mixed_pdf(["Page one.", None, "Page three."]), filename="mixed.pdf")
    r.check("all pages still returned", doc.page_count == 3)
    r.check("empty page reported as empty", not doc.pages[1].text.strip())
    r.check("pages_with_text excludes it", doc.pages_with_text == 2, str(doc.pages_with_text))

    r.section("failure modes")
    await expect_error(r, "scanned image", make_image_only_pdf(), "scanned image")
    await expect_error(r, "not a PDF", b"PK\x03\x04 fake docx payload", "not a PDF")
    await expect_error(r, "empty file", b"", "empty")
    await expect_error(r, "corrupt PDF", b"%PDF-1.7\ngarbage not a real pdf", "could not be read")

    r.section("no raw tracebacks reach the user")
    try:
        await parse_pdf(b"%PDF-1.7\nbroken", filename="b.pdf")
    except ParserError as exc:
        for token in ("Traceback", "File \"", "line ", "Exception:"):
            r.check(f"user_message free of {token!r}", token not in exc.user_message)

    return r.finish()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
