"""Identify SEC filing sections via regex and map them to page ranges."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdf_extract import PageData

# Keys used throughout the pipeline
COVER_PAGE = "cover_page"
INCOME_STATEMENT = "income_statement"
BALANCE_SHEET = "balance_sheet"
CASH_FLOW = "cash_flow"
STOCKHOLDERS_EQUITY = "stockholders_equity"
COMPREHENSIVE_INCOME = "comprehensive_income"
NOTES = "notes"
MDA = "mda"
MARKET_RISK = "market_risk"
CONTROLS = "controls"
LEGAL_PROCEEDINGS = "legal_proceedings"
RISK_FACTORS = "risk_factors"
EXHIBITS = "exhibits"
SIGNATURES = "signatures"

# Display names for section headings
SECTION_TITLES = {
    COVER_PAGE: "Cover Page",
    INCOME_STATEMENT: "Consolidated Statements of Income",
    BALANCE_SHEET: "Consolidated Balance Sheets",
    CASH_FLOW: "Consolidated Statements of Cash Flows",
    STOCKHOLDERS_EQUITY: "Consolidated Statements of Stockholders' Equity",
    COMPREHENSIVE_INCOME: "Consolidated Statements of Comprehensive Income",
    NOTES: "Notes to Financial Statements",
    MDA: "Management's Discussion and Analysis",
    MARKET_RISK: "Quantitative and Qualitative Disclosures About Market Risk",
    CONTROLS: "Controls and Procedures",
    LEGAL_PROCEEDINGS: "Legal Proceedings",
    RISK_FACTORS: "Risk Factors",
    EXHIBITS: "Exhibits",
    SIGNATURES: "Signatures",
}

# Ordered list — order matters for boundary detection
SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        INCOME_STATEMENT,
        re.compile(
            r"(?:CONDENSED\s+)?CONSOLIDATED\s+STATEMENTS?\s+OF\s+(?:INCOME|OPERATIONS|EARNINGS)"
            r"(?:\s+AND\s+COMPREHENSIVE\s+(?:INCOME|LOSS)(?:\s*\(LOSS\))?)?",
            re.IGNORECASE,
        ),
    ),
    (
        COMPREHENSIVE_INCOME,
        re.compile(
            r"(?:CONDENSED\s+)?CONSOLIDATED\s+STATEMENTS?\s+OF\s+COMPREHENSIVE\s+(?:INCOME|LOSS)(?:\s*\(LOSS\))?",
            re.IGNORECASE,
        ),
    ),
    (
        BALANCE_SHEET,
        re.compile(
            r"(?:CONDENSED\s+)?CONSOLIDATED\s+(?:BALANCE\s+SHEETS?|STATEMENTS?\s+OF\s+FINANCIAL\s+CONDITION)",
            re.IGNORECASE,
        ),
    ),
    (
        CASH_FLOW,
        re.compile(
            r"(?:CONDENSED\s+)?CONSOLIDATED\s+STATEMENTS?\s+OF\s+CASH\s+FLOWS?",
            re.IGNORECASE,
        ),
    ),
    (
        STOCKHOLDERS_EQUITY,
        re.compile(
            r"(?:CONDENSED\s+)?CONSOLIDATED\s+STATEMENTS?\s+OF\s+"
            r"(?:"
            r"(?:STOCKHOLDERS|SHAREHOLDERS|CHANGES\s+IN\s+(?:STOCKHOLDERS|SHAREHOLDERS))['\u2019]?\s*(?:EQUITY|DEFICIT)"
            r"|CHANGES\s+IN\s+EQUITY"
            r")",
            re.IGNORECASE,
        ),
    ),
    (
        NOTES,
        re.compile(
            r"NOTES\s+TO\s+(?:THE\s+)?(?:CONDENSED\s+)?(?:CONSOLIDATED\s+)?(?:CONDENSED\s+)?(?:INTERIM\s+)?FINANCIAL\s+STATEMENTS",
            re.IGNORECASE,
        ),
    ),
    (
        MDA,
        re.compile(
            r"(?:Item\s+(?:2|7)[.\s]*)?MANAGEMENT['\u2019]?S\s+DISCUSSION\s+AND\s+ANALYSIS"
            r"(?:\s+OF\s+FINANCIAL\s+CONDITION\s+AND\s+RESULTS\s+OF\s+OPERATIONS)?",
            re.IGNORECASE,
        ),
    ),
    (
        MARKET_RISK,
        re.compile(
            r"QUANTITATIVE\s+AND\s+QUALITATIVE\s+DISCLOSURES?\s+ABOUT\s+MARKET\s+RISK",
            re.IGNORECASE,
        ),
    ),
    (
        CONTROLS,
        re.compile(
            r"(?:Item\s+4[.\s]*)?CONTROLS\s+AND\s+PROCEDURES",
            re.IGNORECASE,
        ),
    ),
    (
        LEGAL_PROCEEDINGS,
        re.compile(
            r"Item\s+(?:1|3)[.\s]+LEGAL\s+PROCEEDINGS",
            re.IGNORECASE,
        ),
    ),
    (
        RISK_FACTORS,
        re.compile(
            r"Item\s+1A[.\s]+RISK\s+FACTORS",
            re.IGNORECASE,
        ),
    ),
    (
        EXHIBITS,
        re.compile(
            r"Item\s+(?:6|15|16)[.\s]+EXHIBITS",
            re.IGNORECASE,
        ),
    ),
    (
        SIGNATURES,
        re.compile(
            r"^SIGNATURES?\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
]


@dataclass
class SectionData:
    name: str
    start_page: int  # 1-indexed inclusive
    end_page: int  # 1-indexed inclusive
    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)


_TOC_PATTERN = re.compile(
    r"TABLE\s+OF\s+CONTENTS", re.IGNORECASE
)

# Matches a trailing bare page number at end of a line (TOC entry)
_TOC_LINE_NUMBER = re.compile(r"\s+\d{1,3}\s*$")


def _is_heading_match(page_text: str, match: re.Match[str]) -> bool:
    """Check that a regex match falls on a standalone heading line.

    A valid heading line must be:
    - ≤120 characters long
    - The match starts within the first 10 characters of the line
    - The line does NOT end with a bare page number (TOC entry heuristic)
    - After the match, the remaining text on the line is short (not prose)
    """
    # Find the line containing the match
    line_start = page_text.rfind("\n", 0, match.start())
    line_start = 0 if line_start == -1 else line_start + 1
    line_end = page_text.find("\n", match.end())
    if line_end == -1:
        line_end = len(page_text)
    line = page_text[line_start:line_end]

    if len(line) > 120:
        return False
    if match.start() - line_start > 10:
        return False
    if _TOC_LINE_NUMBER.search(line):
        return False
    # Reject lines that start with a lowercase word or conjunction — these are
    # mid-sentence references (e.g. "and the Consolidated Statements of Cash
    # Flows on" or "Refer to Consolidated Statements of...").
    line_stripped = line.lstrip()
    if line_stripped and line_stripped[0].islower():
        return False
    # Reject lines starting with "Refer", "and", "or", "the", "See" — references
    prefix_word = line_stripped.split()[0] if line_stripped.split() else ""
    if prefix_word.lower() in ("and", "or", "the", "refer", "see", "selected"):
        return False
    # Reject lines where the pattern is followed by significant trailing prose
    # (e.g. "Notes to Financial Statements included in Item 8 of this...")
    trailing = page_text[match.end():line_end].strip()
    if len(trailing) > 50:
        return False
    # Reject headings that are about *analysis/discussion* of statements rather
    # than the actual statements (e.g. "Consolidated Balance Sheets and Cash
    # Flows Analysis" in JPM combined annual report).
    if trailing and re.search(
        r"\b(?:ANALYSIS|DISCUSSION|SUMMARY|HIGHLIGHTS?|OVERVIEW|SELECTED|DATA)\b",
        trailing,
        re.IGNORECASE,
    ):
        return False
    # Reject lines where the matched heading is followed by punctuation that
    # indicates it's a mid-sentence reference rather than a standalone heading
    # (e.g. "Consolidated balance sheets." or "Consolidated balance sheets,")
    if trailing and trailing[0] in ".;,":
        return False
    # Reject lines with trailing content starting with lowercase or "at"/"as"
    # (e.g. "Consolidated balance sheets at fair value")
    if trailing:
        first_trailing_word = trailing.split()[0] if trailing.split() else ""
        if first_trailing_word and first_trailing_word[0].islower():
            return False
        if first_trailing_word.lower() in ("at", "as"):
            return False
    return True


def _has_toc_entries(text: str) -> bool:
    """Check if the page has multiple lines with page numbers (TOC entries).

    Recognizes two formats:
    - Trailing page numbers: "Item 1. Business ........... 5"
    - Leading page numbers (two-column layout): "52 Introduction"
    """
    lines = text.split("\n")
    # Trailing page numbers (original check)
    trailing_count = sum(1 for line in lines if _TOC_LINE_NUMBER.search(line))
    if trailing_count >= 3:
        return True
    # Leading page numbers: lines starting with 1-3 digit number followed by text
    # e.g. "52 Introduction" or "172 Consolidated Financial Statements"
    _LEADING_PAGE_NUM = re.compile(r"^\s*\d{1,3}\s+[A-Z]")
    leading_count = sum(1 for line in lines if _LEADING_PAGE_NUM.search(line))
    return leading_count >= 5


def _is_toc_page(page: PageData) -> bool:
    """Detect Table of Contents pages — these list section names with page numbers."""
    text = page.text
    has_toc_heading = bool(_TOC_PATTERN.search(text))

    if has_toc_heading and _has_toc_entries(text):
        # Check if "TABLE OF CONTENTS" is a running header vs a real TOC heading.
        # Running headers appear on the first few lines of many pages (e.g. XOM
        # has "Table of Contents Financial Table of Contents" on every page).
        lines = text.strip().splitlines()
        toc_in_header_area = any(
            _TOC_PATTERN.search(line) and len(line.strip()) < 60
            for line in lines[:3]
        )

        # Check if the page has actual financial data (not just section titles
        # that mention financial terms, which is common in TOC entries like
        # "stockholders' equity; interest rates and interest differentials").
        # Require dollar amounts or aggregated totals with numbers nearby.
        financial_patterns = re.compile(
            r"(?:total\s+(?:assets|liabilities|revenue|equity|current)\s.*[\d,]+|"
            r"net\s+(?:income|loss|cash)\s.*[\d,]+|"
            r"operating\s+(?:income|loss|expenses)\s.*[\d,]+|"
            r"\$\s*[\d,]+)",
            re.IGNORECASE,
        )
        has_financial = financial_patterns.search(text)

        if toc_in_header_area and has_financial:
            # TOC text is in the header area BUT page has financial data —
            # this is a financial page with a running TOC header, not a real TOC
            return False

        if not toc_in_header_area and has_financial:
            # TOC text is buried in the page (not a heading) and page has
            # financial data — not a TOC page
            return False

        # Check for dotted-leader TOC entry pattern (real TOC pages typically
        # have entries like "Item 1. Business .............. 5")
        dotted_leader = re.compile(r"\.{3,}\s*\d{1,3}\s*$")
        dotted_count = sum(1 for line in lines if dotted_leader.search(line))
        if dotted_count >= 2:
            return True  # definite TOC page with dotted leaders

        # If TOC is in header area but no financial data, it's a real TOC
        if toc_in_header_area:
            return True

        # TOC text not in header, no financial data — likely a real TOC
        return True

    # Heuristic: if 4+ section patterns match on a single page, it's likely a TOC
    matches = sum(1 for _, pat in SECTION_PATTERNS if pat.search(text))
    return matches >= 4


def _find_section_starts(pages: list[PageData]) -> list[tuple[str, int]]:
    """Return (section_key, page_number) for the first match of each pattern."""
    found: list[tuple[str, int]] = []
    seen_keys: set[str] = set()

    for page in pages:
        if _is_toc_page(page):
            continue
        for key, pattern in SECTION_PATTERNS:
            if key in seen_keys:
                continue
            for m in pattern.finditer(page.text):
                if _is_heading_match(page.text, m):
                    found.append((key, page.page_number))
                    seen_keys.add(key)
                    break

    # Sort by page number so boundary logic works correctly
    found.sort(key=lambda x: x[1])
    return found


def _detect_cover_page(
    pages: list[PageData], starts: list[tuple[str, int]]
) -> SectionData | None:
    """Everything before the first detected section becomes the cover page."""
    if not starts or not pages:
        return None

    first_section_page = starts[0][1]
    if first_section_page <= pages[0].page_number:
        return None  # no pages before first section

    text_parts: list[str] = []
    tables: list[list[list[str]]] = []
    for page in pages:
        if page.page_number < first_section_page:
            text_parts.append(page.text)
            tables.extend(page.tables)

    if not text_parts:
        return None

    return SectionData(
        name=COVER_PAGE,
        start_page=pages[0].page_number,
        end_page=first_section_page - 1,
        text="\n\n".join(text_parts),
        tables=tables,
    )


def _split_page_text_at_header(
    page_text: str, pattern: re.Pattern[str]
) -> tuple[str, str]:
    """Split page text at a section header match.

    Returns (text_before, text_from_header).
    If no match, returns (page_text, "").
    """
    m = pattern.search(page_text)
    if not m:
        return page_text, ""
    # Find the start of the line containing the match
    line_start = page_text.rfind("\n", 0, m.start())
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1  # skip the newline itself
    return page_text[:line_start], page_text[line_start:]


def split_sections(pages: list[PageData]) -> dict[str, SectionData]:
    """Split extracted pages into SEC filing sections.

    Returns a dict keyed by section name. Missing sections are omitted.
    When sections share a start page, text is split at the header boundary
    to avoid duplicating content.
    """
    if not pages:
        return {}

    last_page = pages[-1].page_number
    starts = _find_section_starts(pages)

    # Fix: when MDA is detected but covers ≤1 page before the next section,
    # it may be a "reference forward" stub (e.g. XOM: "Item 7. MDA — see
    # Financial Section"). Look for a second MDA heading later and use that.
    mda_idx = next((i for i, (k, _) in enumerate(starts) if k == MDA), None)
    if mda_idx is not None:
        mda_pg = starts[mda_idx][1]
        next_pg = starts[mda_idx + 1][1] if mda_idx + 1 < len(starts) else last_page + 1
        if next_pg - mda_pg <= 1:
            # MDA is a stub — search for a second heading match
            mda_pattern = next(pat for k, pat in SECTION_PATTERNS if k == MDA)
            for page in pages:
                if page.page_number <= mda_pg:
                    continue
                if _is_toc_page(page):
                    continue
                for m in mda_pattern.finditer(page.text):
                    if _is_heading_match(page.text, m):
                        starts[mda_idx] = (MDA, page.page_number)
                        starts.sort(key=lambda x: x[1])
                        break
                else:
                    continue
                break

    # Build a lookup: page_number -> PageData
    page_by_num: dict[int, PageData] = {p.page_number: p for p in pages}

    # Build a lookup: section key -> pattern (for text splitting)
    pattern_by_key: dict[str, re.Pattern[str]] = {
        key: pat for key, pat in SECTION_PATTERNS
    }

    sections: dict[str, SectionData] = {}

    # Detect cover page (everything before first section)
    cover = _detect_cover_page(pages, starts)
    if cover:
        sections[COVER_PAGE] = cover

    # Financial statement sections rarely exceed a few pages each.
    # Cap them to avoid absorbing unrelated trailing content.
    _MAX_PAGES: dict[str, int] = {
        INCOME_STATEMENT: 5,
        COMPREHENSIVE_INCOME: 5,
        BALANCE_SHEET: 5,
        CASH_FLOW: 5,
        STOCKHOLDERS_EQUITY: 5,
    }

    for i, (key, start_pg) in enumerate(starts):
        # End page is one before the next section start, or the last page.
        if i + 1 < len(starts):
            end_pg = max(start_pg, starts[i + 1][1] - 1)
        else:
            end_pg = last_page

        # Cap financial statement sections to avoid absorbing unrelated pages
        max_pg = _MAX_PAGES.get(key)
        if max_pg and end_pg - start_pg >= max_pg:
            end_pg = start_pg + max_pg - 1

        # Determine if we need to split text on the start/end pages
        next_key = starts[i + 1][0] if i + 1 < len(starts) else None
        next_start_pg = starts[i + 1][1] if i + 1 < len(starts) else None

        # Collect text and tables for the page range
        section_text_parts: list[str] = []
        section_tables: list[list[list[str]]] = []
        for page in pages:
            if start_pg <= page.page_number <= end_pg:
                text = page.text

                # On the start page, if a previous section also ends here,
                # trim text to start from this section's header
                if page.page_number == start_pg and i > 0:
                    prev_key, prev_pg = starts[i - 1]
                    if prev_pg == start_pg or (prev_pg < start_pg and start_pg <= max(prev_pg, start_pg)):
                        # Previous section also touches this page — trim from our header
                        pat = pattern_by_key.get(key)
                        if pat:
                            _, text_from_header = _split_page_text_at_header(text, pat)
                            if text_from_header:
                                text = text_from_header

                # On the end page, if the next section starts here too,
                # trim text to end before the next section's header
                if (
                    next_key
                    and next_start_pg == page.page_number
                    and next_start_pg == end_pg
                ):
                    next_pat = pattern_by_key.get(next_key)
                    if next_pat:
                        text_before, _ = _split_page_text_at_header(text, next_pat)
                        if text_before.strip():
                            text = text_before

                section_text_parts.append(text)
                section_tables.extend(page.tables)

        sections[key] = SectionData(
            name=key,
            start_page=start_pg,
            end_page=end_pg,
            text="\n\n".join(section_text_parts),
            tables=section_tables,
        )

    return sections
