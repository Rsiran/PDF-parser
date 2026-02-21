# IFRS Report Parsing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add auto-detection and parsing of IFRS financial reports (Oslo Stock Exchange style) alongside existing SEC pipeline.

**Architecture:** Parallel pipeline approach — a new `ifrs_section_split.py` handles IFRS section detection while sharing `pdf_extract.py`, `programmatic.py`, and `gemini_client.py`. A `detect_report_type()` function in `section_split.py` routes to the correct splitter. `pipeline.py` dispatches based on report type.

**Tech Stack:** pdfplumber (existing), pytest (new dev dependency)

**Test PDFs:** `/Users/jonas/Library/CloudStorage/OneDrive-Personal/Desktop/Investering/Cadeler/Reports/` contains quarterly (14pp) and annual (270pp) reports from Cadeler A/S.

---

### Task 1: Add pytest and create test infrastructure

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_detect.py`

**Step 1: Add pytest to dev dependencies and test config**

In `pyproject.toml`, add:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 2: Create test infrastructure**

Create empty `tests/__init__.py`.

Create `tests/conftest.py`:

```python
"""Shared test fixtures."""

from __future__ import annotations

import pytest
from pathlib import Path

CADELER_REPORTS = Path(
    "/Users/jonas/Library/CloudStorage/OneDrive-Personal"
    "/Desktop/Investering/Cadeler/Reports"
)


@pytest.fixture
def cadeler_1q25():
    """Cadeler Q1 2025 quarterly report (14 pages)."""
    path = CADELER_REPORTS / "1Q25.pdf"
    if not path.exists():
        pytest.skip("Cadeler 1Q25.pdf not available")
    return path


@pytest.fixture
def cadeler_ar24():
    """Cadeler Annual Report 2024 (270 pages)."""
    path = CADELER_REPORTS / "AR24.pdf"
    if not path.exists():
        pytest.skip("Cadeler AR24.pdf not available")
    return path
```

**Step 3: Write failing test for report type detection**

Create `tests/test_detect.py`:

```python
"""Tests for report type auto-detection."""

from sec_parser.pdf_extract import extract_pdf
from sec_parser.detect import detect_report_type


def test_detect_ifrs_quarterly(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    assert detect_report_type(pages) == "ifrs"


def test_detect_ifrs_annual(cadeler_ar24):
    pages = extract_pdf(cadeler_ar24)
    assert detect_report_type(pages) == "ifrs"
```

**Step 4: Run test to verify it fails**

Run: `pytest tests/test_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sec_parser.detect'`

**Step 5: Commit**

```bash
git add pyproject.toml tests/
git commit -m "Add pytest infrastructure and failing detection tests"
```

---

### Task 2: Implement report type detection

**Files:**
- Create: `sec_parser/detect.py`

**Step 1: Implement `detect_report_type()`**

Create `sec_parser/detect.py`:

```python
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

    Scores each marker found. SEC markers get +1 for SEC, IFRS markers +1
    for IFRS. The higher score wins. Defaults to 'ifrs' on a tie.
    """
    sec_score = 0
    ifrs_score = 0

    for page in pages[:scan_pages]:
        text = page.text
        for pat in _SEC_PATTERNS:
            if pat.search(text):
                sec_score += 1
        for pat in _IFRS_PATTERNS:
            if pat.search(text):
                ifrs_score += 1

    return "sec" if sec_score > ifrs_score else "ifrs"
```

**Step 2: Run tests**

Run: `pytest tests/test_detect.py -v`
Expected: PASS — both Cadeler reports detected as `"ifrs"`

**Step 3: Commit**

```bash
git add sec_parser/detect.py
git commit -m "Add report type auto-detection (SEC vs IFRS)"
```

---

### Task 3: Write failing tests for IFRS section splitting

**Files:**
- Create: `tests/test_ifrs_sections.py`

**Step 1: Write failing tests**

Create `tests/test_ifrs_sections.py`:

```python
"""Tests for IFRS section splitting."""

from sec_parser.pdf_extract import extract_pdf
from sec_parser.ifrs_section_split import (
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_NOTES,
    split_ifrs_sections,
)


def test_quarterly_finds_all_sections(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)

    # Quarterly report should have all financial statement sections
    assert IFRS_INCOME_STATEMENT in sections
    assert IFRS_BALANCE_SHEET in sections
    assert IFRS_CASH_FLOW in sections
    assert IFRS_EQUITY_CHANGES in sections


def test_annual_finds_all_sections(cadeler_ar24):
    pages = extract_pdf(cadeler_ar24)
    sections = split_ifrs_sections(pages)

    assert IFRS_INCOME_STATEMENT in sections
    assert IFRS_BALANCE_SHEET in sections
    assert IFRS_CASH_FLOW in sections
    assert IFRS_EQUITY_CHANGES in sections
    assert IFRS_NOTES in sections


def test_income_statement_has_revenue(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)
    text = sections[IFRS_INCOME_STATEMENT].text
    assert "Revenue" in text or "revenue" in text


def test_balance_sheet_has_assets(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)
    text = sections[IFRS_BALANCE_SHEET].text
    assert "Total" in text and "assets" in text.lower()


def test_sections_have_tables(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)

    # Financial statements should have extracted tables
    for key in [IFRS_INCOME_STATEMENT, IFRS_BALANCE_SHEET, IFRS_CASH_FLOW]:
        assert sections[key].tables, f"{key} should have tables"


def test_ignores_parent_company_financials(cadeler_ar24):
    """Should pick consolidated statements, not parent company."""
    pages = extract_pdf(cadeler_ar24)
    sections = split_ifrs_sections(pages)

    # Income statement should be the consolidated one (page ~143),
    # not the parent company one (page ~226)
    assert sections[IFRS_INCOME_STATEMENT].start_page < 200
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_ifrs_sections.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sec_parser.ifrs_section_split'`

**Step 3: Commit**

```bash
git add tests/test_ifrs_sections.py
git commit -m "Add failing tests for IFRS section splitting"
```

---

### Task 4: Implement IFRS section splitter

**Files:**
- Create: `sec_parser/ifrs_section_split.py`

**Step 1: Implement the IFRS section splitter**

Create `sec_parser/ifrs_section_split.py`:

```python
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

# Table of Contents / section divider pages
_TOC_PATTERN = re.compile(r"(?:Table\s+of\s+)?Contents", re.IGNORECASE)


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

    page_by_num: dict[int, PageData] = {p.page_number: p for p in pages}
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
```

**Step 2: Run tests**

Run: `pytest tests/test_ifrs_sections.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add sec_parser/ifrs_section_split.py
git commit -m "Implement IFRS section splitter with consolidated-only detection"
```

---

### Task 5: Write failing tests for IFRS pipeline integration

**Files:**
- Create: `tests/test_pipeline_ifrs.py`

**Step 1: Write failing integration tests**

Create `tests/test_pipeline_ifrs.py`:

```python
"""Integration tests for IFRS pipeline."""

import pytest
from pathlib import Path

from sec_parser.pipeline import process_pdf


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


def test_quarterly_produces_markdown(cadeler_1q25, output_dir):
    result = process_pdf(cadeler_1q25, output_dir, verbose=True)
    assert result.exists()
    content = result.read_text()
    assert "## Consolidated Statement of Profit or Loss" in content
    assert "## Consolidated Balance Sheet" in content
    assert "## Consolidated Statement of Cash Flows" in content


def test_quarterly_has_financial_data(cadeler_1q25, output_dir):
    result = process_pdf(cadeler_1q25, output_dir)
    content = result.read_text()
    # Should contain actual financial figures
    assert "Revenue" in content
    # Should have markdown table syntax
    assert "|" in content


def test_annual_produces_markdown(cadeler_ar24, output_dir):
    result = process_pdf(cadeler_ar24, output_dir, verbose=True)
    assert result.exists()
    content = result.read_text()
    assert "## Consolidated Statement of Profit or Loss" in content
    assert "## Consolidated Balance Sheet" in content
    assert "## Consolidated Statement of Cash Flows" in content
    assert "## Consolidated Statement of Changes in Equity" in content
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_pipeline_ifrs.py -v`
Expected: FAIL — `process_pdf` doesn't handle IFRS yet

**Step 3: Commit**

```bash
git add tests/test_pipeline_ifrs.py
git commit -m "Add failing integration tests for IFRS pipeline"
```

---

### Task 6: Integrate IFRS pipeline into `pipeline.py` and `markdown_writer.py`

**Files:**
- Modify: `sec_parser/pipeline.py`
- Modify: `sec_parser/markdown_writer.py`

**Step 1: Update `markdown_writer.py` to support IFRS section order**

Add IFRS section order and titles. Modify `assemble_markdown` to accept an optional `section_order` and `section_titles` parameter.

In `sec_parser/markdown_writer.py`, add these imports and constants at the top (after existing imports):

```python
from .ifrs_section_split import (
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_INCOME_STATEMENT,
    IFRS_NOTES,
    IFRS_SECTION_TITLES,
)
```

Add after `SECTION_ORDER`:

```python
IFRS_SECTION_ORDER = [
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_EQUITY_CHANGES,
    IFRS_CASH_FLOW,
    IFRS_NOTES,
]

IFRS_REQUIRED_SECTIONS = {
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_NOTES,
}
```

Modify `assemble_markdown` to accept optional parameters:

```python
def assemble_markdown(
    source_filename: str,
    processed: dict[str, str],
    section_order: list[str] | None = None,
    section_titles: dict[str, str] | None = None,
    required_sections: set[str] | None = None,
) -> str:
```

Replace the hardcoded references inside the function body:

```python
    order = section_order or SECTION_ORDER
    titles = section_titles or SECTION_TITLES
    required = required_sections or REQUIRED_SECTIONS
```

And use `order`, `titles`, `required` instead of the constants in the loop.

**Step 2: Update `pipeline.py` to dispatch based on report type**

Add a new `_process_ifrs` function and modify `process_pdf` to detect and dispatch.

At the top of `pipeline.py`, add imports:

```python
from .detect import detect_report_type
from .ifrs_section_split import (
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_INCOME_STATEMENT,
    IFRS_NOTES,
    IFRS_SECTION_TITLES,
    split_ifrs_sections,
)
from .markdown_writer import IFRS_REQUIRED_SECTIONS, IFRS_SECTION_ORDER
```

Add a new function `_process_ifrs`:

```python
IFRS_FINANCIAL_STATEMENTS = [
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
]


def _process_ifrs(
    pages: list,
    pdf_path: Path,
    output_dir: Path,
    verbose: bool,
) -> Path:
    """Process an IFRS report PDF into markdown."""
    sections = split_ifrs_sections(pages)

    if verbose:
        found = [IFRS_SECTION_TITLES.get(k, k) for k in sections]
        print(f"  Sections found: {', '.join(found)}", file=sys.stderr)

    required = [IFRS_INCOME_STATEMENT, IFRS_BALANCE_SHEET, IFRS_CASH_FLOW, IFRS_NOTES]
    for key in required:
        if key not in sections:
            print(
                f"  WARNING: {IFRS_SECTION_TITLES.get(key, key)} not found in {pdf_path.name}",
                file=sys.stderr,
            )

    processed: dict[str, str] = {}

    # Financial statements — programmatic table collapse
    for key in IFRS_FINANCIAL_STATEMENTS:
        if key in sections:
            section = sections[key]
            if verbose:
                print(f"  Processing {IFRS_SECTION_TITLES[key]}...", file=sys.stderr)
            processed[key] = tables_to_markdown(section.text, section.tables)

    # Notes — LLM if available, raw text fallback
    if IFRS_NOTES in sections:
        if verbose:
            print(f"  Processing {IFRS_SECTION_TITLES[IFRS_NOTES]}...", file=sys.stderr)
        try:
            processed[IFRS_NOTES] = extract_notes(
                sections[IFRS_NOTES].text, verbose=verbose
            )
        except Exception as exc:
            print(
                f"  WARNING: Notes extraction failed ({exc}), using raw text",
                file=sys.stderr,
            )
            processed[IFRS_NOTES] = sections[IFRS_NOTES].text

    # Assemble with IFRS ordering
    md_content = assemble_markdown(
        pdf_path.name,
        processed,
        section_order=IFRS_SECTION_ORDER,
        section_titles=IFRS_SECTION_TITLES,
        required_sections=IFRS_REQUIRED_SECTIONS,
    )
    output_path = output_dir / f"{pdf_path.stem}.md"
    write_markdown(output_path, md_content)

    if verbose:
        print(f"  Written to {output_path}", file=sys.stderr)

    return output_path
```

Modify `process_pdf` to detect and dispatch:

```python
def process_pdf(pdf_path: Path, output_dir: Path, verbose: bool = False) -> Path:
    """Process a financial report PDF into a structured markdown file.

    Auto-detects SEC vs IFRS report type.
    Returns the path to the output markdown file.
    """
    if verbose:
        print(f"Extracting text from {pdf_path.name}...", file=sys.stderr)

    pages = extract_pdf(pdf_path)
    detect_scanned(pages)

    if verbose:
        print(f"  {len(pages)} pages extracted", file=sys.stderr)

    report_type = detect_report_type(pages)
    if verbose:
        print(f"  Detected report type: {report_type.upper()}", file=sys.stderr)

    if report_type == "ifrs":
        return _process_ifrs(pages, pdf_path, output_dir, verbose)

    # Existing SEC pipeline below (unchanged)
    ...
```

Move the existing SEC logic into the else branch (keeping it intact).

**Step 3: Run tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add sec_parser/pipeline.py sec_parser/markdown_writer.py
git commit -m "Integrate IFRS pipeline with auto-detection dispatch"
```

---

### Task 7: Update CLI description and project metadata

**Files:**
- Modify: `sec_parser/cli.py:18-21` — update description
- Modify: `pyproject.toml:8` — update description

**Step 1: Update CLI description**

In `cli.py`, change the argparse description from:
```python
description="Batch-process SEC 10-K and 10-Q financial PDFs into structured markdown.",
```
to:
```python
description="Batch-process financial report PDFs (SEC 10-K/10-Q and IFRS) into structured markdown.",
```

Update the `input_folder` help text from `"Folder containing SEC filing PDFs"` to `"Folder containing financial report PDFs"`.

**Step 2: Update pyproject.toml description**

Change:
```toml
description = "Batch-process SEC 10-K and 10-Q financial PDFs into structured markdown"
```
to:
```toml
description = "Batch-process financial report PDFs (SEC and IFRS) into structured markdown"
```

**Step 3: Commit**

```bash
git add sec_parser/cli.py pyproject.toml
git commit -m "Update CLI and project descriptions for IFRS support"
```

---

### Task 8: End-to-end smoke test with real PDFs

**Step 1: Run the parser on the Cadeler reports folder**

```bash
cd /Users/jonas/Desktop/claude/PDF-parser/.claude/worktrees/lazy-chasing-starlight
python -m sec_parser.cli "/Users/jonas/Library/CloudStorage/OneDrive-Personal/Desktop/Investering/Cadeler/Reports" --verbose -o /tmp/cadeler-output
```

**Step 2: Inspect output quality**

Check that `/tmp/cadeler-output/1Q25.md` and `/tmp/cadeler-output/AR24.md`:
- Have all expected section headers
- Financial tables render as proper markdown tables
- Revenue and key figures are present and correct
- No parent company financials leaked in

**Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All PASS

**Step 4: Commit any fixes needed**

If adjustments were needed during smoke testing, commit them individually with descriptive messages.
