"""Extract text and tables from PDF pages using pdfplumber."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


@dataclass
class PageData:
    page_number: int
    text: str
    tables: list[list[list[str]]] = field(default_factory=list)


# Patterns suggesting a page contains financial statement data
_FINANCIAL_HINT = re.compile(
    r"(?:total\s+(?:assets|liabilities|revenue|equity)|"
    r"net\s+(?:income|loss|cash)|"
    r"operating\s+(?:income|expenses|activities)|"
    r"cash\s+and\s+cash\s+equivalents|"
    r"balance\s+sheets?|"
    r"statements?\s+of\s+(?:income|operations|cash\s+flows?))",
    re.IGNORECASE,
)

_TEXT_TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
}


def _clean_tables(raw_tables: list) -> list[list[list[str]]]:
    """Replace None cells with empty strings in raw pdfplumber tables."""
    return [
        [[cell if cell is not None else "" for cell in row] for row in table]
        for table in raw_tables
    ]


def extract_pdf(path: Path) -> list[PageData]:
    """Extract text and tables from every page of a PDF.

    Uses pdfplumber's default (line-based) table detection first.  When that
    finds no tables on a page whose text hints at financial data, retries with
    text-based table detection as a fallback.
    """
    pages: list[PageData] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            raw_tables = page.extract_tables() or []
            tables = _clean_tables(raw_tables)

            # Fallback: if default strategy found nothing and the page looks
            # like it contains financial data, retry with text-based strategy
            if not tables and _FINANCIAL_HINT.search(text):
                raw_tables = page.extract_tables(_TEXT_TABLE_SETTINGS) or []
                tables = _clean_tables(raw_tables)

            pages.append(PageData(page_number=i + 1, text=text, tables=tables))
    return pages


def detect_scanned(pages: list[PageData], threshold: float = 0.8, min_chars: int = 50) -> None:
    """Raise RuntimeError if the PDF appears to be scanned (image-based).

    A PDF is considered scanned if more than *threshold* fraction of pages
    contain fewer than *min_chars* characters of extracted text.
    """
    if not pages:
        return
    sparse_count = sum(1 for p in pages if len(p.text.strip()) < min_chars)
    if sparse_count / len(pages) > threshold:
        raise RuntimeError(
            f"PDF appears to be scanned ({sparse_count}/{len(pages)} pages have <{min_chars} chars). "
            "OCR support is not implemented yet."
        )
