"""Identify IFRS financial statement sections via regex and map them to page ranges."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdf_extract import PageData

# Section keys
IFRS_INCOME_STATEMENT = "ifrs_income_statement"
IFRS_BALANCE_SHEET = "ifrs_balance_sheet"
IFRS_CASH_FLOW = "ifrs_cash_flow"
IFRS_EQUITY_CHANGES = "ifrs_equity_changes"
IFRS_NOTES = "ifrs_notes"

# Display names
IFRS_SECTION_TITLES = {
    IFRS_INCOME_STATEMENT: "Consolidated Statement of Profit or Loss and Other Comprehensive Income",
    IFRS_BALANCE_SHEET: "Consolidated Balance Sheet",
    IFRS_CASH_FLOW: "Consolidated Statement of Cash Flows",
    IFRS_EQUITY_CHANGES: "Consolidated Statement of Changes in Equity",
    IFRS_NOTES: "Notes to the Consolidated Financial Statements",
}

# Patterns ordered by typical appearance in IFRS reports.
# "Condensed" and "Interim" prefixes are optional (quarterly reports use them).
_PREFIX = r"(?:(?:Interim\s+)?(?:Condensed\s+)?(?:Consolidated\s+)?)?"

IFRS_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        IFRS_INCOME_STATEMENT,
        re.compile(
            _PREFIX + r"Statement\s+of\s+Profit\s+or\s+Loss",
            re.IGNORECASE,
        ),
    ),
    (
        IFRS_BALANCE_SHEET,
        re.compile(
            _PREFIX + r"(?:Balance\s+Sheet|Statement\s+of\s+Financial\s+Position)",
            re.IGNORECASE,
        ),
    ),
    (
        IFRS_EQUITY_CHANGES,
        re.compile(
            _PREFIX + r"Statement\s+of\s+Changes\s+in\s+Equity",
            re.IGNORECASE,
        ),
    ),
    (
        IFRS_CASH_FLOW,
        re.compile(
            _PREFIX + r"Statement\s+of\s+Cash\s+Flows?",
            re.IGNORECASE,
        ),
    ),
    (
        IFRS_NOTES,
        re.compile(
            r"Notes\s+to\s+(?:the\s+)?(?:Condensed\s+)?(?:Consolidated\s+)?Financial\s+Statements",
            re.IGNORECASE,
        ),
    ),
]

# Pattern to detect "Parent Company" section headers — we skip these
_PARENT_COMPANY = re.compile(r"Parent\s+Company", re.IGNORECASE)


@dataclass
class IFRSSectionData:
    name: str
    start_page: int  # 1-indexed inclusive
    end_page: int  # 1-indexed inclusive
    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)


def _is_divider_page(page: PageData) -> bool:
    """Detect divider/title pages with minimal text."""
    return len(page.text.strip()) < 100


def _is_parent_company_page(page: PageData) -> bool:
    """Check if a page belongs to parent company financial statements."""
    return bool(_PARENT_COMPANY.search(page.text[:200]))


def _find_ifrs_section_starts(pages: list[PageData]) -> list[tuple[str, int]]:
    """Return (section_key, page_number) for the first consolidated match of each pattern."""
    found: list[tuple[str, int]] = []
    seen_keys: set[str] = set()

    for page in pages:
        # Skip divider pages and parent company sections
        if _is_divider_page(page):
            continue
        if _is_parent_company_page(page):
            continue

        for key, pattern in IFRS_SECTION_PATTERNS:
            if key in seen_keys:
                continue
            if pattern.search(page.text):
                found.append((key, page.page_number))
                seen_keys.add(key)

    found.sort(key=lambda x: x[1])
    return found


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
    line_start = page_text.rfind("\n", 0, m.start())
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    return page_text[:line_start], page_text[line_start:]


def split_ifrs_sections(pages: list[PageData]) -> dict[str, IFRSSectionData]:
    """Split extracted pages into IFRS financial statement sections.

    Returns a dict keyed by section name. Only returns consolidated
    financial statements — parent company financials are skipped.
    """
    if not pages:
        return {}

    last_page = pages[-1].page_number
    starts = _find_ifrs_section_starts(pages)

    pattern_by_key: dict[str, re.Pattern[str]] = {
        key: pat for key, pat in IFRS_SECTION_PATTERNS
    }

    sections: dict[str, IFRSSectionData] = {}

    for i, (key, start_pg) in enumerate(starts):
        # End page is one before the next section start, or last page
        if i + 1 < len(starts):
            end_pg = max(start_pg, starts[i + 1][1] - 1)
        else:
            # For the last section (Notes), extend to end of document
            # but stop at parent company financials
            end_pg = last_page
            for page in pages:
                if page.page_number > start_pg and _is_parent_company_page(page):
                    end_pg = page.page_number - 1
                    break

        next_key = starts[i + 1][0] if i + 1 < len(starts) else None
        next_start_pg = starts[i + 1][1] if i + 1 < len(starts) else None

        section_text_parts: list[str] = []
        section_tables: list[list[list[str]]] = []

        for page in pages:
            if start_pg <= page.page_number <= end_pg:
                text = page.text

                # Skip divider pages within the range
                if _is_divider_page(page) and page.page_number != start_pg:
                    continue

                # On start page, trim text to start from this section's header
                if page.page_number == start_pg and i > 0:
                    prev_key, prev_pg = starts[i - 1]
                    if prev_pg == start_pg:
                        pat = pattern_by_key.get(key)
                        if pat:
                            _, text_from_header = _split_page_text_at_header(text, pat)
                            if text_from_header:
                                text = text_from_header

                # On end page, trim before next section header
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

        sections[key] = IFRSSectionData(
            name=key,
            start_page=start_pg,
            end_page=end_pg,
            text="\n\n".join(section_text_parts),
            tables=section_tables,
        )

    return sections
