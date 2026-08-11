"""PDF text extraction.

pdfplumber is the primary extractor; PyMuPDF is the fallback for layout-heavy
documents pdfplumber handles poorly. Rather than guessing in advance which will
win, we run the primary, and only if its yield looks poor do we run the fallback
and keep whichever produced more text. That costs one extra pass on bad PDFs and
nothing on good ones.

This module is the sole origin of page numbers in the pipeline. Everything
downstream — chunk page ranges, the analyzer's page-bounding prompt, the UI's
citation affordance — inherits from what is extracted here. A page number that is
wrong here is wrong everywhere, and looks verified.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from models.schemas import ExtractionMethod, PageText, ParsedDocument

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"

# Below this many non-whitespace characters per page, the primary extractor is
# considered to have done badly and the fallback is tried. Chosen well under a
# sparse title or signature page (~100+ chars) so we do not thrash on documents
# that are simply short.
MIN_CHARS_PER_PAGE_BEFORE_FALLBACK = 40

# Collapse 3+ newlines to exactly 2. Preserves paragraph breaks — which the
# chunker splits on — while removing the ragged vertical whitespace PDF
# extraction produces.
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")


class ParserError(Exception):
    """A parse failure with a message that is safe to show the user.

    Route handlers should surface `user_message` and log `detail`. Never return
    `detail` or a traceback to the frontend (CLAUDE.md, Error Handling Rules).
    """

    def __init__(self, user_message: str, detail: str) -> None:
        super().__init__(detail)
        self.user_message = user_message
        self.detail = detail


def _normalize(raw: str | None) -> str:
    """Tidy extracted page text without destroying paragraph structure."""
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_SPACES.sub("\n", text)
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def _extract_pdfplumber(data: bytes) -> list[PageText]:
    pages: list[PageText] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            pages.append(PageText(page_number=i, text=_normalize(page.extract_text())))
    return pages


def _extract_pymupdf(data: bytes) -> list[PageText]:
    pages: list[PageText] = []
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for i, page in enumerate(doc, start=1):
            pages.append(PageText(page_number=i, text=_normalize(page.get_text())))
    finally:
        doc.close()
    return pages


def _yield_chars(pages: list[PageText]) -> int:
    return sum(len(p.text.strip()) for p in pages)


def parse_pdf_bytes(data: bytes, *, filename: str = "document.pdf") -> ParsedDocument:
    """Extract per-page text from PDF bytes. Blocking — see `parse_pdf` for the
    async entry point.

    Raises ParserError, never a library-specific exception, so callers have one
    thing to catch and one message to show.
    """
    if not data:
        raise ParserError(
            "That file is empty. Upload a PDF that contains text.",
            "empty byte payload",
        )

    if not data.lstrip()[:5].startswith(PDF_MAGIC):
        # Caught here rather than at the library boundary so the message can name
        # the real problem — usually a .docx or a renamed file.
        raise ParserError(
            "That file is not a PDF. This tool accepts text-based PDF files only.",
            f"missing %PDF- magic bytes; first 8 bytes were {data[:8]!r}",
        )

    pages: list[PageText] = []
    method = ExtractionMethod.PDFPLUMBER
    primary_error: str | None = None

    try:
        pages = _extract_pdfplumber(data)
    except Exception as exc:  # noqa: BLE001 - library raises many unrelated types
        primary_error = f"{type(exc).__name__}: {exc}"
        logger.warning("pdfplumber failed on %s: %s", filename, primary_error)
        if _is_encrypted_error(exc):
            raise ParserError(
                "This PDF is password-protected. Remove the password and upload it again.",
                f"encrypted PDF: {primary_error}",
            ) from exc

    page_count = len(pages)
    needs_fallback = page_count == 0 or (
        _yield_chars(pages) < MIN_CHARS_PER_PAGE_BEFORE_FALLBACK * max(page_count, 1)
    )

    if needs_fallback:
        logger.info(
            "pdfplumber yield was low for %s (%s chars over %s pages) — trying PyMuPDF",
            filename,
            _yield_chars(pages),
            page_count,
        )
        try:
            fallback_pages = _extract_pymupdf(data)
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            logger.warning("PyMuPDF also failed on %s: %s", filename, detail)
            if not pages:
                raise ParserError(
                    "This PDF could not be read. It may be corrupted or use an "
                    "unsupported format.",
                    f"both extractors failed; pdfplumber={primary_error}; pymupdf={detail}",
                ) from exc
        else:
            # Keep whichever extractor actually produced more text. Doing this by
            # measurement rather than by rule avoids the failure mode where the
            # fallback is "tried" but silently returns less than the primary.
            if _yield_chars(fallback_pages) > _yield_chars(pages):
                pages = fallback_pages
                method = ExtractionMethod.PYMUPDF

    if not pages:
        raise ParserError(
            "This PDF could not be read. It may be corrupted or use an unsupported format.",
            f"no pages extracted; pdfplumber={primary_error}",
        )

    if _yield_chars(pages) == 0:
        # Both extractors ran and found nothing. This is the scanned-image case:
        # the pages exist and render, but carry no text layer.
        raise ParserError(
            "This PDF appears to be a scanned image with no extractable text. "
            "Try a text-based PDF, or run it through OCR first.",
            f"{len(pages)} pages extracted, 0 characters of text",
        )

    document = ParsedDocument(filename=filename, pages=pages, extraction_method=method)

    if document.pages_with_text < document.page_count:
        # Not fatal — a legitimately blank page or a full-page diagram. Logged so a
        # partial-extraction complaint is diagnosable rather than mysterious.
        logger.info(
            "%s: %s of %s pages yielded text (method=%s)",
            filename,
            document.pages_with_text,
            document.page_count,
            method.value,
        )

    return document


def _is_encrypted_error(exc: Exception) -> bool:
    """Detect the password-protected case across both libraries.

    Matched on message text because neither library exposes a dedicated
    exception type for it.
    """
    text = f"{type(exc).__name__} {exc}".lower()
    return any(k in text for k in ("password", "encrypt", "decrypt"))


async def parse_pdf(data: bytes, *, filename: str = "document.pdf") -> ParsedDocument:
    """Async entry point.

    Both PDF libraries are synchronous and CPU-bound; calling them directly from
    a FastAPI route would block the event loop for the whole extraction. Offloaded
    to a worker thread instead (CLAUDE.md: no blocking calls in routes).
    """
    return await asyncio.to_thread(parse_pdf_bytes, data, filename=filename)


async def parse_pdf_path(path: str | Path) -> ParsedDocument:
    """Convenience wrapper for local files — tests and CLI use, not the upload path."""
    p = Path(path)
    try:
        data = await asyncio.to_thread(p.read_bytes)
    except OSError as exc:
        raise ParserError(
            "That file could not be opened.", f"OSError reading {p}: {exc}"
        ) from exc
    return await parse_pdf(data, filename=p.name)
