"""Auto-detect whether a PDF is a US SEC filing or an IFRS report."""

from __future__ import annotations

import re

from .pdf_extract import PageData

# SEC markers — typically found on cover pages
_SEC_PATTERNS = [
    re.compile(r"FORM\s+10-[KQ]", re.IGNORECASE),
    re.compile(r"SECURITIES\s+AND\s+EXCHANGE\s+COMMISSION", re.IGNORECASE),
    re.compile(r"Central\s+Index\s+Key", re.IGNORECASE),
]

# IFRS markers — found in European/Scandinavian reports
_IFRS_PATTERNS = [
    re.compile(r"(?:EUR|NOK|DKK|SEK|GBP)['\u2019]?000", re.IGNORECASE),
    re.compile(r"\bIFRS\b"),
    re.compile(r"(?:CVR|Org\.?\s*(?:nr|no|number))[.\s:]+[\d\s]+", re.IGNORECASE),
    re.compile(r"Statement\s+of\s+Profit\s+or\s+Loss", re.IGNORECASE),
    re.compile(r"Statement\s+of\s+Financial\s+Position", re.IGNORECASE),
    re.compile(r"Oslo\s+B.rs|Oslo\s+Stock\s+Exchange|Euronext", re.IGNORECASE),
]


def _is_toc_page(text: str) -> bool:
    """Check if a page is a table of contents page.

    A page is TOC if it contains "TABLE OF CONTENTS" AND has multiple lines
    ending with page numbers, or if many section-like headings appear.
    Also matches lowercase "Table of contents" variants.
    """
    if "TABLE OF CONTENTS" not in text.upper():
        return False
    # Count lines ending with page numbers (e.g., "... 42" or "...42")
    page_num_lines = sum(
        1 for line in text.split("\n")
        if re.search(r"\.{2,}\s*\d+\s*$", line) or re.search(r"\s{3,}\d+\s*$", line)
    )
    return page_num_lines >= 3


# Patterns for detecting the start of a 10-K/10-Q filing in combined documents
_FORM_10K_PATTERN = re.compile(r"FORM\s+10-[KQ]", re.IGNORECASE)
_SEC_COMMISSION_PATTERN = re.compile(
    r"UNITED\s+STATES\s+SECURITIES\s+AND\s+EXCHANGE\s+COMMISSION", re.IGNORECASE
)
_REGISTRANT_PATTERN = re.compile(
    r"\(Exact\s+name\s+of\s+registrant", re.IGNORECASE
)

# Footer/header pattern used by combined annual reports that embed 10-K pages.
# Matches patterns like "JPMorgan Chase & Co./2024 Form 10-K 49" or
# "50 JPMorgan Chase & Co./2024 Form 10-K"
_FORM_10K_FOOTER = re.compile(
    r"(?:^|\n)\s*(?:\d+\s+)?.{3,60}/\d{4}\s+Form\s+10-[KQ](?:\s+\d+)?\s*(?:$|\n)",
    re.IGNORECASE,
)


def detect_10k_start_page(pages: list[PageData]) -> int:
    """Find the page where the 10-K/10-Q filing begins in a combined document.

    Combined annual reports (like JPM) include shareholder letters, commentary,
    and other material before the SEC filing. This function identifies the first
    page of the actual 10-K/10-Q by looking for SEC cover page markers.

    Detection strategy (in priority order):
    1. SEC cover page: "UNITED STATES SECURITIES AND EXCHANGE COMMISSION" AND
       "FORM 10-K"/"FORM 10-Q" on the same page.
    2. Registrant line: "(Exact name of registrant...)" on a page.
    3. Form footer: "Company/Year Form 10-K <page>" footer pattern, which
       indicates embedded 10-K pages in a combined annual report.

    Returns the 1-indexed page number of the filing start. Returns 1 if no
    start page is detected (entire document is the filing).
    """
    # Pass 1: Look for SEC cover page markers (highest confidence)
    for page in pages:
        text = page.text

        # Skip TOC pages — they may reference "FORM 10-K" in listings
        if _is_toc_page(text):
            continue

        # Primary signal: both SEC commission header AND form type on same page
        has_commission = bool(_SEC_COMMISSION_PATTERN.search(text))
        has_form = bool(_FORM_10K_PATTERN.search(text))

        if has_commission and has_form:
            return page.page_number

        # Secondary signal: "(Exact name of registrant..." line
        if _REGISTRANT_PATTERN.search(text):
            return page.page_number

    # Pass 2: Look for Form 10-K footer pattern (for combined annual reports
    # where the SEC cover page is omitted, e.g. JPM)
    for page in pages:
        if _FORM_10K_FOOTER.search(page.text):
            # Only treat as combined document if this isn't the first page
            if page.page_number > 1:
                return page.page_number
            break  # Footer on page 1 means no prefix to skip

    # No clear start page found — treat entire document as the filing
    return 1


def detect_report_type(pages: list[PageData], scan_pages: int = 10) -> str:
    """Scan the first N pages and return 'sec' or 'ifrs'.

    Scores each unique pattern matched (not per-page occurrence).
    The higher score wins. Defaults to 'sec' for backward compatibility.
    """
    sec_matched: set[int] = set()
    ifrs_matched: set[int] = set()

    for page in pages[:scan_pages]:
        text = page.text
        for i, pat in enumerate(_SEC_PATTERNS):
            if pat.search(text):
                sec_matched.add(i)
        for i, pat in enumerate(_IFRS_PATTERNS):
            if pat.search(text):
                ifrs_matched.add(i)

    return "ifrs" if len(ifrs_matched) > len(sec_matched) else "sec"
