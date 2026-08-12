"""Minimal test harness.

Deliberately dependency-free — these run with plain `python`, no pytest, so the
suite adds nothing to the project's dependency list. If pytest is adopted later
the check() calls can be swapped for bare asserts without restructuring.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `models`, `services`, and `prompts` importable regardless of cwd.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from models.schemas import ExtractionMethod, PageText, ParsedDocument  # noqa: E402


class Results:
    def __init__(self, title: str) -> None:
        self.title = title
        self.passed = 0
        self.failures: list[str] = []
        print(f"\n=== {title} ===")

    def section(self, name: str) -> None:
        print(f"\n-- {name} --")

    def check(self, label: str, condition: bool, extra: str = "") -> bool:
        if condition:
            self.passed += 1
        else:
            self.failures.append(label)
        tag = "PASS" if condition else "FAIL"
        suffix = f" - {extra}" if extra else ""
        print(f"  [{tag}] {label}{suffix}")
        return condition

    def finish(self) -> int:
        print()
        if self.failures:
            print(f"{self.title}: {len(self.failures)} FAILED, {self.passed} passed")
            for f in self.failures:
                print(f"   - {f}")
            return 1
        print(f"{self.title}: all {self.passed} checks passed")
        return 0


def make_document(pages: list[tuple[int, str]], name: str = "test.pdf") -> ParsedDocument:
    """Build a ParsedDocument directly, bypassing PDF generation."""
    return ParsedDocument(
        filename=name,
        pages=[PageText(page_number=n, text=t) for n, t in pages],
        extraction_method=ExtractionMethod.PDFPLUMBER,
    )


def make_text_pdf(pages_text: list[str]) -> bytes:
    """A real PDF with a text layer on every page."""
    import fitz

    doc = fitz.open()
    for body in pages_text:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 550, 780), body, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def make_image_only_pdf(page_count: int = 2) -> bytes:
    """Pages that render but carry no text layer — the scanned-document case."""
    import fitz

    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page()
        page.draw_rect(fitz.Rect(100, 100, 400, 400), fill=(0.6, 0.6, 0.6))
    data = doc.tobytes()
    doc.close()
    return data


def make_mixed_pdf(bodies: list[str | None]) -> bytes:
    """`None` produces a page with no text layer, at that exact position."""
    import fitz

    doc = fitz.open()
    for body in bodies:
        page = doc.new_page()
        if body is None:
            page.draw_rect(fitz.Rect(80, 80, 500, 600), fill=(0.75, 0.75, 0.75))
        else:
            page.insert_textbox(fitz.Rect(50, 50, 550, 780), body, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data
