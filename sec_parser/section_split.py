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
            r"(?:CONDENSED\s+)?CONSOLIDATED\s+STATEMENTS?\s+OF\s+(?:INCOME|OPERATIONS|EARNINGS)",
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
            r"(?:STOCKHOLDERS|SHAREHOLDERS|CHANGES\s+IN\s+(?:STOCKHOLDERS|SHAREHOLDERS))['\u2019]?\s*"
            r"(?:EQUITY|DEFICIT)",
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
            r"(?:Item\s+2[.\s]*)?MANAGEMENT['\u2019]?S\s+DISCUSSION\s+AND\s+ANALYSIS",
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
            r"Item\s+1[.\s]+LEGAL\s+PROCEEDINGS",
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
            r"Item\s+6[.\s]+EXHIBITS",
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


def _is_toc_page(page: PageData) -> bool:
    """Detect Table of Contents pages — these list section names with page numbers."""
    if _TOC_PATTERN.search(page.text):
        return True
    # Heuristic: if 4+ section patterns match on a single page, it's likely a TOC
    matches = sum(1 for _, pat in SECTION_PATTERNS if pat.search(page.text))
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
            m = pattern.search(page.text)
            if m:
                # Verify the match is on a standalone heading line,
                # not embedded in a long prose sentence.
                line_start = page.text.rfind('\n', 0, m.start()) + 1
                line_end = page.text.find('\n', m.end())
                if line_end == -1:
                    line_end = len(page.text)
                matched_line = page.text[line_start:line_end].strip()
                if len(matched_line) > 120:
                    continue  # embedded in prose, not a heading
                # If there's significant text before the match on the
                # same line, it's mid-sentence, not a heading.
                prefix = page.text[line_start:m.start()].strip()
                if len(prefix) > 10:
                    continue
                found.append((key, page.page_number))
                seen_keys.add(key)

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

    for i, (key, start_pg) in enumerate(starts):
        # End page is one before the next section start, or the last page.
        if i + 1 < len(starts):
            end_pg = max(start_pg, starts[i + 1][1] - 1)
        else:
            end_pg = last_page

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
