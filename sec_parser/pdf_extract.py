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


def _collapse_repeated_chars(text: str) -> str:
    """Collapse character-tripled/doubled text from bold PDF rendering.

    Some PDFs render bold by overlaying characters 2-3 times. pdfplumber
    extracts all copies, e.g. "YYYeeeaaarrr" instead of "Year".

    Detection: check if the text has a pattern where each character appears
    exactly N times consecutively (N=2 or N=3) for a significant portion.
    Only apply to lines where this pattern is dominant.
    """
    lines = text.split('\n')
    result = []
    for line in lines:
        collapsed = _try_collapse_line(line)
        result.append(collapsed)
    return '\n'.join(result)


def _try_collapse_line(line: str) -> str:
    """Try to collapse a single line of repeated characters.

    Tries multiple repeat factors (2-15) and picks the best one.
    Some PDFs overlay glyphs varying numbers of times for bold/emphasis.
    """
    if len(line) < 6:
        return line

    # Try each factor and collect candidates with their match quality
    best: tuple[float, int, str] | None = None  # (match_ratio, factor, result)
    for factor in range(2, 16):
        if len(line) < factor * 3:
            continue
        collapsed = _collapse_with_factor(line, factor)
        if collapsed is not None:
            # Score by compression ratio — real repeated text compresses a lot
            ratio = len(collapsed) / len(line)
            # Prefer higher factors when ratio is similar (more compression = more likely)
            score = ratio  # lower is better (more compression)
            if best is None or score < best[0]:
                best = (score, factor, collapsed)

    if best is not None:
        return best[2]
    return line


def _collapse_with_factor(line: str, factor: int) -> str | None:
    """Try to collapse a line assuming each char is repeated `factor` times.

    Returns the collapsed string if successful, None if the pattern doesn't match.
    """
    # Check if the line can be evenly divided
    # Build the collapsed version and verify it matches
    chars = list(line)
    if not chars:
        return None

    collapsed = []
    i = 0
    matches = 0
    total_groups = 0

    while i < len(chars):
        ch = chars[i]
        # Count consecutive occurrences of this character
        j = i
        while j < len(chars) and chars[j] == ch:
            j += 1
        run_length = j - i

        if ch == ' ':
            # Spaces may not be exactly repeated — be lenient
            collapsed.append(' ')
            i = j
            continue

        total_groups += 1
        if run_length == factor:
            matches += 1
            collapsed.append(ch)
            i = j
        elif run_length % factor == 0:
            # Multiple of factor — might be legitimate repeated chars
            matches += 1
            collapsed.append(ch * (run_length // factor))
            i = j
        else:
            # Doesn't match the pattern
            collapsed.append(ch * run_length)
            i = j

    # Only accept if a high proportion of character groups match the pattern
    if total_groups > 0 and matches / total_groups >= 0.7 and total_groups >= 3:
        return ''.join(collapsed)
    return None


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
            text = _collapse_repeated_chars(text)  # Fix character-tripled bold text
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
