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
