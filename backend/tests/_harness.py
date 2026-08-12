"""Minimal test harness.

Deliberately dependency-free — these run with plain `python`, no pytest, so the
suite adds nothing to the project's dependency list. If pytest is adopted later
the check() calls can be swapped for bare asserts without restructuring.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `models`, `services`, and `prompts` importable regardless of cwd.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from models.schemas import ExtractionMethod, PageText, ParsedDocument  # noqa: E402

# Every credential the app reads at startup. Listed here so adding a service means
# adding one line in one place, rather than remembering to scrub it in each test
# module that builds an app.
LIVE_CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
)


def scrub_live_credentials() -> None:
    """Remove real credentials from the environment before any app is started.

    CALL THIS AFTER `import main`, never before. main.py runs load_dotenv() at
    import time, which reads the developer's real .env — popping first just lets it
    put everything back.

    Without this, a test that starts the app builds live clients: the Anthropic one
    spends money, and the Supabase one writes rows into the developer's actual
    project every time the suite runs. Tests must not touch either.
    """
    for name in LIVE_CREDENTIALS:
        os.environ.pop(name, None)


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


def _insert_or_raise(page, body: str, index: int) -> None:
    """Write `body` onto `page`, refusing to continue if it did not fit.

    insert_textbox returns the leftover vertical space, or a NEGATIVE number when
    the text was too tall — and in that case it writes NOTHING. Silently, so a
    fixture that overruns the page produces a valid PDF with an empty text layer,
    and the test that depends on it fails somewhere far away with a misleading
    message. Ask how much text a page holds instead of assuming; this raises so
    the answer is "your fixture is too long", not "the parser is broken".
    """
    import fitz

    overflow = page.insert_textbox(fitz.Rect(50, 50, 550, 780), body, fontsize=9)
    if overflow < 0:
        raise ValueError(
            f"fixture page {index} is {len(body)} characters, which overflows one "
            f"page by {abs(overflow):.0f}pt and would silently produce a blank "
            f"page. Split it across pages."
        )


def make_text_pdf(pages_text: list[str]) -> bytes:
    """A real PDF with a text layer on every page."""
    import fitz

    doc = fitz.open()
    for i, body in enumerate(pages_text):
        _insert_or_raise(doc.new_page(), body, i)
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
    for i, body in enumerate(bodies):
        page = doc.new_page()
        if body is None:
            page.draw_rect(fitz.Rect(80, 80, 500, 600), fill=(0.75, 0.75, 0.75))
        else:
            _insert_or_raise(page, body, i)
    data = doc.tobytes()
    doc.close()
    return data
