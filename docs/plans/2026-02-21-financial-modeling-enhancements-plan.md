# Financial Modeling Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured YAML front-matter, hybrid line item normalization, and validation checks to the SEC filing parser so output is optimized for Claude in Excel to build 3-statement financial models with DCF valuations across multiple filings.

**Architecture:** Three new modules (`metadata.py`, `normalize.py`, `validate.py`) plus a `taxonomy.yaml` data file. The pipeline orchestrator (`pipeline.py`) gains a post-processing phase that normalizes line items and runs validation. The markdown writer (`markdown_writer.py`) emits YAML front-matter and a validation section. A multi-filing consistency pass in `cli.py` ensures the same line item mappings are used across all filings in a batch.

**Tech Stack:** Python 3.10+, pyyaml, difflib.SequenceMatcher (stdlib), existing Gemini client for LLM fallback.

---

### Task 1: Add pyyaml dependency

**Files:**
- Modify: `pyproject.toml:10-13`

**Step 1: Add pyyaml to dependencies**

In `pyproject.toml`, add `"pyyaml>=6.0"` to the dependencies list:

```toml
dependencies = [
    "pdfplumber>=0.11",
    "google-genai>=1.0",
    "pyyaml>=6.0",
]
```

**Step 2: Install updated dependencies**

Run: `pip install -e .`
Expected: Successfully installs pyyaml

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "Add pyyaml dependency for front-matter and taxonomy support"
```

---

### Task 2: Create the taxonomy file

**Files:**
- Create: `sec_parser/taxonomy.yaml`

**Step 1: Create taxonomy with canonical line items and aliases**

Create `sec_parser/taxonomy.yaml` with three top-level sections. Each item has a `canonical` name and `aliases` list. Cover the ~60 most common line items across SEC filings:

```yaml
income_statement:
  revenue:
    canonical: "Revenue"
    aliases:
      - "Net revenues"
      - "Total revenues"
      - "Net sales"
      - "Total net revenues"
      - "Revenue, net"
      - "Revenues"
      - "Total net sales"
      - "Net revenue"
      - "Sales"
      - "Total sales"
  cost_of_revenue:
    canonical: "Cost of Revenue"
    aliases:
      - "Cost of sales"
      - "Cost of goods sold"
      - "Cost of revenue"
      - "Cost of net revenues"
      - "Cost of products sold"
      - "Cost of revenues"
  gross_profit:
    canonical: "Gross Profit"
    aliases:
      - "Gross profit"
      - "Gross margin"
  research_and_development:
    canonical: "Research & Development"
    aliases:
      - "Research and development"
      - "Research and development expense"
      - "R&D expenses"
  selling_general_admin:
    canonical: "Selling, General & Administrative"
    aliases:
      - "Selling, general and administrative"
      - "Selling, general and administrative expenses"
      - "General and administrative"
      - "General and administrative expenses"
      - "SG&A"
      - "Selling and marketing"
  depreciation_amortization:
    canonical: "Depreciation & Amortization"
    aliases:
      - "Depreciation and amortization"
      - "Depreciation"
      - "Amortization"
      - "Amortization of intangible assets"
  total_operating_expenses:
    canonical: "Total Operating Expenses"
    aliases:
      - "Total operating expenses"
      - "Total costs and expenses"
      - "Total expenses"
  operating_income:
    canonical: "Operating Income"
    aliases:
      - "Operating income"
      - "Operating income (loss)"
      - "Income (loss) from operations"
      - "Loss from operations"
      - "Income from operations"
  interest_expense:
    canonical: "Interest Expense"
    aliases:
      - "Interest expense"
      - "Interest expense, net"
      - "Interest and debt expense"
  interest_income:
    canonical: "Interest Income"
    aliases:
      - "Interest income"
      - "Interest and other income"
  other_income_expense:
    canonical: "Other Income (Expense)"
    aliases:
      - "Other income (expense), net"
      - "Other income, net"
      - "Other expense, net"
      - "Other (expense) income"
      - "Non-operating income (expense)"
  income_before_tax:
    canonical: "Income Before Tax"
    aliases:
      - "Income before income taxes"
      - "Income (loss) before income taxes"
      - "Loss before income taxes"
      - "Income before provision for income taxes"
  income_tax_expense:
    canonical: "Income Tax Expense"
    aliases:
      - "Income tax expense"
      - "Income tax expense (benefit)"
      - "Provision for income taxes"
      - "Income tax provision"
      - "Income taxes"
  net_income:
    canonical: "Net Income"
    aliases:
      - "Net income"
      - "Net income (loss)"
      - "Net loss"
      - "Net income attributable to common stockholders"
      - "Net income (loss) attributable to common stockholders"
  eps_basic:
    canonical: "EPS - Basic"
    aliases:
      - "Basic net income (loss) per share"
      - "Basic earnings per share"
      - "Net income (loss) per share, basic"
      - "Basic net loss per share"
  eps_diluted:
    canonical: "EPS - Diluted"
    aliases:
      - "Diluted net income (loss) per share"
      - "Diluted earnings per share"
      - "Net income (loss) per share, diluted"
      - "Diluted net loss per share"
  shares_basic:
    canonical: "Shares Outstanding - Basic"
    aliases:
      - "Weighted average shares outstanding, basic"
      - "Weighted-average shares outstanding, basic"
      - "Basic weighted average shares outstanding"
      - "Weighted average common shares outstanding - basic"
  shares_diluted:
    canonical: "Shares Outstanding - Diluted"
    aliases:
      - "Weighted average shares outstanding, diluted"
      - "Weighted-average shares outstanding, diluted"
      - "Diluted weighted average shares outstanding"
      - "Weighted average common shares outstanding - diluted"

balance_sheet:
  cash:
    canonical: "Cash & Cash Equivalents"
    aliases:
      - "Cash and cash equivalents"
      - "Cash"
      - "Cash, cash equivalents and restricted cash"
  short_term_investments:
    canonical: "Short-Term Investments"
    aliases:
      - "Short-term investments"
      - "Marketable securities"
      - "Available-for-sale securities"
  accounts_receivable:
    canonical: "Accounts Receivable"
    aliases:
      - "Accounts receivable, net"
      - "Accounts receivable"
      - "Trade receivables"
      - "Trade accounts receivable"
      - "Receivables, net"
  inventory:
    canonical: "Inventory"
    aliases:
      - "Inventories"
      - "Inventories, net"
      - "Merchandise inventories"
  prepaid_expenses:
    canonical: "Prepaid Expenses"
    aliases:
      - "Prepaid expenses and other current assets"
      - "Prepaid expenses"
      - "Other current assets"
  total_current_assets:
    canonical: "Total Current Assets"
    aliases:
      - "Total current assets"
  property_plant_equipment:
    canonical: "Property, Plant & Equipment"
    aliases:
      - "Property and equipment, net"
      - "Property, plant and equipment, net"
      - "Property and equipment"
  goodwill:
    canonical: "Goodwill"
    aliases:
      - "Goodwill"
  intangible_assets:
    canonical: "Intangible Assets"
    aliases:
      - "Intangible assets, net"
      - "Intangible assets"
      - "Other intangible assets"
  total_assets:
    canonical: "Total Assets"
    aliases:
      - "Total assets"
      - "TOTAL ASSETS"
  accounts_payable:
    canonical: "Accounts Payable"
    aliases:
      - "Accounts payable"
      - "Trade accounts payable"
  accrued_liabilities:
    canonical: "Accrued Liabilities"
    aliases:
      - "Accrued liabilities"
      - "Accrued expenses"
      - "Accrued expenses and other current liabilities"
      - "Other accrued liabilities"
  short_term_debt:
    canonical: "Short-Term Debt"
    aliases:
      - "Short-term borrowings"
      - "Current portion of long-term debt"
      - "Current maturities of long-term debt"
      - "Short-term debt"
  total_current_liabilities:
    canonical: "Total Current Liabilities"
    aliases:
      - "Total current liabilities"
  long_term_debt:
    canonical: "Long-Term Debt"
    aliases:
      - "Long-term debt"
      - "Long-term debt, net of current portion"
      - "Long-term borrowings"
      - "Long-term debt, less current portion"
  total_liabilities:
    canonical: "Total Liabilities"
    aliases:
      - "Total liabilities"
      - "TOTAL LIABILITIES"
  common_stock:
    canonical: "Common Stock"
    aliases:
      - "Common stock"
      - "Common stock and additional paid-in capital"
  retained_earnings:
    canonical: "Retained Earnings"
    aliases:
      - "Retained earnings"
      - "Retained earnings (accumulated deficit)"
      - "Accumulated deficit"
  total_stockholders_equity:
    canonical: "Total Stockholders' Equity"
    aliases:
      - "Total stockholders' equity"
      - "Total shareholders' equity"
      - "Total equity"
      - "Total stockholders' equity (deficit)"
  total_liabilities_and_equity:
    canonical: "Total Liabilities & Stockholders' Equity"
    aliases:
      - "Total liabilities and stockholders' equity"
      - "Total liabilities and shareholders' equity"
      - "TOTAL LIABILITIES AND STOCKHOLDERS' EQUITY"

cash_flow:
  net_income_cf:
    canonical: "Net Income"
    aliases:
      - "Net income"
      - "Net income (loss)"
      - "Net loss"
  depreciation_amortization_cf:
    canonical: "Depreciation & Amortization"
    aliases:
      - "Depreciation and amortization"
      - "Depreciation"
  stock_based_compensation:
    canonical: "Stock-Based Compensation"
    aliases:
      - "Stock-based compensation"
      - "Stock-based compensation expense"
      - "Share-based compensation"
  changes_in_working_capital:
    canonical: "Changes in Working Capital"
    aliases:
      - "Changes in operating assets and liabilities"
      - "Changes in assets and liabilities"
  net_cash_operations:
    canonical: "Net Cash from Operations"
    aliases:
      - "Net cash provided by operating activities"
      - "Net cash used in operating activities"
      - "Net cash provided by (used in) operating activities"
      - "Cash flows from operating activities"
  capex:
    canonical: "Capital Expenditures"
    aliases:
      - "Purchases of property and equipment"
      - "Capital expenditures"
      - "Additions to property and equipment"
      - "Payments for property and equipment"
  acquisitions:
    canonical: "Acquisitions"
    aliases:
      - "Acquisitions, net of cash acquired"
      - "Business acquisitions"
      - "Payments for acquisitions"
  net_cash_investing:
    canonical: "Net Cash from Investing"
    aliases:
      - "Net cash provided by investing activities"
      - "Net cash used in investing activities"
      - "Net cash provided by (used in) investing activities"
      - "Cash flows from investing activities"
  debt_issued:
    canonical: "Debt Issued"
    aliases:
      - "Proceeds from borrowings"
      - "Proceeds from issuance of debt"
      - "Proceeds from long-term debt"
  debt_repaid:
    canonical: "Debt Repaid"
    aliases:
      - "Repayments of debt"
      - "Repayments of borrowings"
      - "Repayment of long-term debt"
  dividends_paid:
    canonical: "Dividends Paid"
    aliases:
      - "Dividends paid"
      - "Payment of dividends"
      - "Cash dividends paid"
  share_repurchases:
    canonical: "Share Repurchases"
    aliases:
      - "Repurchases of common stock"
      - "Treasury stock acquired"
      - "Share repurchases"
      - "Stock repurchases"
  net_cash_financing:
    canonical: "Net Cash from Financing"
    aliases:
      - "Net cash provided by financing activities"
      - "Net cash used in financing activities"
      - "Net cash provided by (used in) financing activities"
      - "Cash flows from financing activities"
  net_change_in_cash:
    canonical: "Net Change in Cash"
    aliases:
      - "Net increase (decrease) in cash"
      - "Net increase in cash"
      - "Net decrease in cash"
      - "Net change in cash and cash equivalents"
      - "Net increase (decrease) in cash, cash equivalents and restricted cash"
  beginning_cash:
    canonical: "Beginning Cash"
    aliases:
      - "Cash at beginning of period"
      - "Cash, cash equivalents and restricted cash, beginning of period"
      - "Cash and cash equivalents, beginning of period"
  ending_cash:
    canonical: "Ending Cash"
    aliases:
      - "Cash at end of period"
      - "Cash, cash equivalents and restricted cash, end of period"
      - "Cash and cash equivalents, end of period"
```

**Step 2: Commit**

```bash
git add sec_parser/taxonomy.yaml
git commit -m "Add financial line item taxonomy with ~60 canonical items and aliases"
```

---

### Task 3: Build the metadata module

**Files:**
- Create: `sec_parser/metadata.py`
- Create: `tests/test_metadata.py`

**Step 1: Write failing tests for metadata extraction**

Create `tests/test_metadata.py`:

```python
"""Tests for front-matter metadata extraction."""

import pytest
from datetime import date

from sec_parser.metadata import extract_metadata, infer_period_type, infer_scale


class TestInferPeriodType:
    def test_10k_is_fy(self):
        assert infer_period_type("10-K", "December 31, 2024") == "FY"

    def test_10k_a_is_fy(self):
        assert infer_period_type("10-K/A", "December 31, 2024") == "FY"

    def test_10q_q1(self):
        assert infer_period_type("10-Q", "March 31, 2025") == "Q1"

    def test_10q_q2(self):
        assert infer_period_type("10-Q", "June 30, 2025") == "Q2"

    def test_10q_q3(self):
        assert infer_period_type("10-Q", "September 30, 2025") == "Q3"

    def test_10q_unknown_month(self):
        # Fiscal year doesn't end in December — can't determine quarter
        assert infer_period_type("10-Q", "January 31, 2025") == "Q?"

    def test_missing_period(self):
        assert infer_period_type("10-Q", "") == "Q?"


class TestInferScale:
    def test_thousands(self):
        assert infer_scale("(in thousands, except share data)") == "thousands"

    def test_millions(self):
        assert infer_scale("(in millions)") == "millions"

    def test_billions(self):
        assert infer_scale("(in billions, except per share data)") == "billions"

    def test_no_scale(self):
        assert infer_scale("") == "units"

    def test_none(self):
        assert infer_scale(None) == "units"


class TestExtractMetadata:
    def test_basic_extraction(self):
        cover_fields = [
            ("Filing Type", "10-Q"),
            ("Company", "Strive Inc."),
            ("Period", "September 30, 2025"),
            ("Ticker", "STRV"),
            ("CIK", "0001234567"),
        ]
        result = extract_metadata(
            cover_fields=cover_fields,
            scale_hint="(in thousands)",
            source_pdf="strive-10q-2025-09-30.pdf",
        )
        assert result["company"] == "Strive Inc."
        assert result["ticker"] == "STRV"
        assert result["filing_type"] == "10-Q"
        assert result["period_end"] == "2025-09-30"
        assert result["period_type"] == "Q3"
        assert result["fiscal_year"] == 2025
        assert result["scale"] == "thousands"
        assert result["currency"] == "USD"
        assert result["audited"] is False
        assert result["source_pdf"] == "strive-10q-2025-09-30.pdf"

    def test_10k_is_audited(self):
        cover_fields = [
            ("Filing Type", "10-K"),
            ("Company", "Acme Corp"),
            ("Period", "December 31, 2024"),
        ]
        result = extract_metadata(
            cover_fields=cover_fields,
            scale_hint="(in millions)",
            source_pdf="acme-10k.pdf",
        )
        assert result["audited"] is True
        assert result["period_type"] == "FY"
        assert result["scale"] == "millions"

    def test_missing_fields_graceful(self):
        result = extract_metadata(
            cover_fields=[],
            scale_hint="",
            source_pdf="unknown.pdf",
        )
        assert result["company"] == ""
        assert result["filing_type"] == ""
        assert result["source_pdf"] == "unknown.pdf"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sec_parser.metadata'`

**Step 3: Implement metadata module**

Create `sec_parser/metadata.py`:

```python
"""Extract and assemble YAML front-matter metadata from parsed cover page fields."""

from __future__ import annotations

import re
from datetime import datetime


# Standard calendar quarter end months (assumes Dec fiscal year end)
_QUARTER_MONTHS = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_period_date(period_str: str) -> tuple[str, int, int]:
    """Parse 'September 30, 2025' into ('2025-09-30', month, year).

    Returns ('', 0, 0) if parsing fails.
    """
    if not period_str:
        return ("", 0, 0)
    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", period_str.strip())
    if not m:
        return ("", 0, 0)
    month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
    month = _MONTH_MAP.get(month_name, 0)
    if not month:
        return ("", 0, 0)
    return (f"{year}-{month:02d}-{day:02d}", month, year)


def infer_period_type(filing_type: str, period_str: str) -> str:
    """Infer Q1/Q2/Q3/Q4/FY from filing type and period end date."""
    ft = filing_type.upper().strip()
    if ft.startswith("10-K"):
        return "FY"
    _, month, _ = _parse_period_date(period_str)
    if not month:
        return "Q?"
    return _QUARTER_MONTHS.get(month, "Q?")


def infer_scale(scale_hint: str | None) -> str:
    """Infer scale from a metadata string like '(in thousands, except share data)'."""
    if not scale_hint:
        return "units"
    lower = scale_hint.lower()
    if "billion" in lower:
        return "billions"
    if "million" in lower:
        return "millions"
    if "thousand" in lower:
        return "thousands"
    return "units"


def extract_metadata(
    cover_fields: list[tuple[str, str]],
    scale_hint: str,
    source_pdf: str,
) -> dict[str, str | int | bool]:
    """Build metadata dict from parsed cover page fields.

    Args:
        cover_fields: List of (label, value) tuples from parse_cover_page.
        scale_hint: The "(in thousands...)" string from table headers.
        source_pdf: Original PDF filename.

    Returns:
        Dict with all front-matter fields.
    """
    fields = {label: value for label, value in cover_fields}

    filing_type = fields.get("Filing Type", "")
    period_str = fields.get("Period", "")
    period_iso, _, year = _parse_period_date(period_str)

    return {
        "company": fields.get("Company", ""),
        "ticker": fields.get("Ticker", ""),
        "cik": fields.get("CIK", ""),
        "filing_type": filing_type,
        "period_end": period_iso,
        "period_type": infer_period_type(filing_type, period_str),
        "fiscal_year": year,
        "scale": infer_scale(scale_hint),
        "currency": "USD",
        "audited": filing_type.upper().startswith("10-K"),
        "source_pdf": source_pdf,
        "parsed_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def metadata_to_yaml(meta: dict) -> str:
    """Render metadata dict as a YAML front-matter block.

    Uses manual formatting to avoid pyyaml dependency for this simple case.
    """
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        elif isinstance(value, str):
            # Quote strings that contain special chars
            if any(c in value for c in ":{}[],'\"&*?|>!%@`"):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metadata.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add sec_parser/metadata.py tests/test_metadata.py
git commit -m "Add metadata module for YAML front-matter extraction"
```

---

### Task 4: Refactor parse_cover_page to return structured data

The current `parse_cover_page()` in `programmatic.py:13-83` returns a markdown string directly. We need it to also return the raw field tuples so `metadata.py` can use them.

**Files:**
- Modify: `sec_parser/programmatic.py:13-83`
- Modify: `sec_parser/pipeline.py:68-71`

**Step 1: Add a new function that returns fields + markdown**

In `sec_parser/programmatic.py`, add a new function `extract_cover_fields` that returns the raw `(label, value)` list, and refactor `parse_cover_page` to call it:

```python
def extract_cover_fields(text: str) -> list[tuple[str, str]]:
    """Extract cover page metadata fields as (label, value) tuples."""
    fields: list[tuple[str, str]] = []

    # Filing type
    m = re.search(r"FORM\s+(10-[QK](?:/A)?)", text, re.IGNORECASE)
    if m:
        fields.append(("Filing Type", m.group(1).upper()))

    # Company name
    m = re.search(
        r"^(.+)\n\s*\((?:Exact|exact)\s+name\s+of\s+registrant",
        text,
        re.MULTILINE,
    )
    if m:
        name = m.group(1).strip()
        if not re.match(r"Commission|File\s+Number|\d+-\d+", name, re.IGNORECASE):
            fields.append(("Company", name))

    # Period of report
    m = re.search(
        r"(?:(?:quarterly|annual)\s+period\s+ended|period\s+of\s+report)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        fields.append(("Period", m.group(1).strip()))

    # Commission File Number
    m = re.search(r"Commission\s+File\s+Number[:\s]+([\d-]+)", text, re.IGNORECASE)
    if m:
        fields.append(("Commission File Number", m.group(1).strip()))

    # CIK
    m = re.search(r"(?:Central\s+Index\s+Key|CIK)[:\s]+(\d+)", text, re.IGNORECASE)
    if m:
        fields.append(("CIK", m.group(1).strip()))

    # Shares outstanding
    m = re.search(r"(\d[\d,]+)\s+shares\s+of\s+common\s+stock", text, re.IGNORECASE)
    if m:
        fields.append(("Shares Outstanding", m.group(1).strip()))

    # Ticker
    m = re.search(r"Trading\s+Symbol[:\s]+([A-Z]+)", text, re.IGNORECASE)
    if m:
        fields.append(("Ticker", m.group(1).strip()))

    # Exchange
    m = re.search(
        r"(?:Name\s+of\s+.*exchange|registered)[:\s]*((?:NYSE|NASDAQ|New\s+York\s+Stock\s+Exchange)[^\n]*)",
        text,
        re.IGNORECASE,
    )
    if m:
        exchange = m.group(1).strip().rstrip(".")
        fields.append(("Exchange", exchange))

    return fields


def parse_cover_page(text: str) -> str:
    """Extract cover page metadata via regex and return a markdown table."""
    fields = extract_cover_fields(text)

    if not fields:
        return text

    lines = ["| Field | Value |", "|-------|-------|"]
    for label, value in fields:
        lines.append(f"| {label} | {value} |")
    return "\n".join(lines)
```

**Step 2: Run existing tests to verify no regression**

Run: `pytest tests/ -v`
Expected: All existing tests still PASS

**Step 3: Commit**

```bash
git add sec_parser/programmatic.py
git commit -m "Refactor parse_cover_page to expose extract_cover_fields"
```

---

### Task 5: Build the normalize module

**Files:**
- Create: `sec_parser/normalize.py`
- Create: `tests/test_normalize.py`

**Step 1: Write failing tests**

Create `tests/test_normalize.py`:

```python
"""Tests for line item normalization."""

import pytest

from sec_parser.normalize import (
    load_taxonomy,
    match_line_item,
    normalize_table_rows,
    NormResult,
)


@pytest.fixture
def taxonomy():
    return load_taxonomy()


class TestLoadTaxonomy:
    def test_loads_three_sections(self, taxonomy):
        assert "income_statement" in taxonomy
        assert "balance_sheet" in taxonomy
        assert "cash_flow" in taxonomy

    def test_has_revenue(self, taxonomy):
        items = taxonomy["income_statement"]
        assert "revenue" in items
        assert items["revenue"]["canonical"] == "Revenue"
        assert "Net revenues" in items["revenue"]["aliases"]


class TestMatchLineItem:
    def test_exact_match(self, taxonomy):
        result = match_line_item("Net revenues", taxonomy)
        assert result.canonical == "Revenue"
        assert result.confidence >= 1.0
        assert result.method == "exact"

    def test_case_insensitive(self, taxonomy):
        result = match_line_item("NET REVENUES", taxonomy)
        assert result.canonical == "Revenue"

    def test_fuzzy_match(self, taxonomy):
        result = match_line_item("Net revenue, net of discounts", taxonomy)
        assert result.canonical == "Revenue"
        assert result.method == "fuzzy"
        assert result.confidence >= 0.85

    def test_no_match(self, taxonomy):
        result = match_line_item("Goodwill impairment charge adjustment", taxonomy)
        assert result.canonical is None
        assert result.method == "none"

    def test_balance_sheet_item(self, taxonomy):
        result = match_line_item("Total current assets", taxonomy)
        assert result.canonical == "Total Current Assets"

    def test_cash_flow_item(self, taxonomy):
        result = match_line_item("Net cash provided by operating activities", taxonomy)
        assert result.canonical == "Net Cash from Operations"


class TestNormalizeTableRows:
    def test_adds_canonical_column(self, taxonomy):
        rows = [
            ["Net revenues", "1,000", "900"],
            ["Cost of sales", "600", "500"],
        ]
        result = normalize_table_rows(rows, taxonomy)
        # Each row should now have 4 elements (original + canonical inserted at index 1)
        assert len(result[0]) == 4
        assert result[0][0] == "Net revenues"
        assert result[0][1] == "Revenue"
        assert result[1][1] == "Cost of Revenue"

    def test_unmapped_gets_empty_canonical(self, taxonomy):
        rows = [
            ["Some exotic line item", "100", "200"],
        ]
        result = normalize_table_rows(rows, taxonomy)
        assert result[0][1] == ""  # unmapped

    def test_numeric_only_rows_skipped(self, taxonomy):
        rows = [
            ["", "1,000", "900"],
        ]
        result = normalize_table_rows(rows, taxonomy)
        assert result[0][1] == ""  # no label to normalize
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement normalize module**

Create `sec_parser/normalize.py`:

```python
"""Hybrid line item normalization: exact match -> fuzzy match -> LLM fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import yaml


_TAXONOMY_PATH = Path(__file__).parent / "taxonomy.yaml"


@dataclass
class NormResult:
    canonical: str | None
    confidence: float
    method: str  # "exact", "fuzzy", "llm", "none"


def load_taxonomy(path: Path | None = None) -> dict:
    """Load the taxonomy YAML file."""
    p = path or _TAXONOMY_PATH
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_alias_index(taxonomy: dict) -> dict[str, str]:
    """Build a lowercase alias -> canonical name lookup."""
    index: dict[str, str] = {}
    for section in taxonomy.values():
        for item in section.values():
            canonical = item["canonical"]
            # Index the canonical name itself
            index[canonical.lower().strip()] = canonical
            for alias in item.get("aliases", []):
                index[alias.lower().strip()] = canonical
    return index


def _build_canonical_list(taxonomy: dict) -> list[str]:
    """Get all canonical names."""
    names = []
    for section in taxonomy.values():
        for item in section.values():
            names.append(item["canonical"])
    return names


def match_line_item(label: str, taxonomy: dict) -> NormResult:
    """Match a line item label to a canonical name.

    Pipeline: exact match -> fuzzy match (>= 0.85) -> no match.
    """
    if not label or not label.strip():
        return NormResult(canonical=None, confidence=0.0, method="none")

    cleaned = label.strip()
    alias_index = _build_alias_index(taxonomy)

    # 1. Exact match (case-insensitive)
    key = cleaned.lower().strip()
    if key in alias_index:
        return NormResult(
            canonical=alias_index[key],
            confidence=1.0,
            method="exact",
        )

    # 2. Fuzzy match against all aliases
    best_score = 0.0
    best_canonical = None
    for alias, canonical in alias_index.items():
        score = SequenceMatcher(None, key, alias).ratio()
        if score > best_score:
            best_score = score
            best_canonical = canonical

    if best_score >= 0.85:
        return NormResult(
            canonical=best_canonical,
            confidence=best_score,
            method="fuzzy",
        )

    # 3. No match
    return NormResult(canonical=None, confidence=best_score, method="none")


def normalize_table_rows(
    rows: list[list[str]],
    taxonomy: dict,
) -> list[list[str]]:
    """Add a 'Canonical' column (index 1) to each row.

    Only attempts normalization on rows where the first cell looks like a
    line item label (non-empty, non-numeric).
    """
    from .programmatic import _is_numeric

    result = []
    for row in rows:
        if not row:
            result.append(["", ""])
            continue

        label = row[0].strip() if row[0] else ""

        # Skip rows with no label or numeric-only first cell
        if not label or _is_numeric(label):
            result.append([row[0], ""] + row[1:])
            continue

        match = match_line_item(label, taxonomy)
        canonical = match.canonical or ""
        result.append([row[0], canonical] + row[1:])

    return result


def collect_unmapped(
    rows: list[list[str]],
    taxonomy: dict,
) -> list[str]:
    """Return line item labels that couldn't be mapped programmatically."""
    from .programmatic import _is_numeric

    unmapped = []
    for row in rows:
        if not row:
            continue
        label = row[0].strip() if row[0] else ""
        if not label or _is_numeric(label):
            continue
        match = match_line_item(label, taxonomy)
        if match.canonical is None:
            unmapped.append(label)
    return unmapped


def llm_normalize_batch(
    unmapped_labels: list[str],
    taxonomy: dict,
    verbose: bool = False,
) -> dict[str, str]:
    """Send unmapped labels to Gemini for classification.

    Returns dict mapping original label -> canonical name (or empty string if still unmapped).
    """
    if not unmapped_labels:
        return {}

    canonical_names = _build_canonical_list(taxonomy)

    # Build prompt
    labels_text = "\n".join(f"- {label}" for label in unmapped_labels)
    canonicals_text = "\n".join(f"- {name}" for name in canonical_names)

    prompt = (
        "You are a financial statement analyst. Map each line item label to the "
        "most appropriate canonical name from the list below. If no canonical name "
        "fits, respond with UNMAPPED.\n\n"
        f"## Canonical Names\n{canonicals_text}\n\n"
        f"## Line Items to Map\n{labels_text}\n\n"
        "Respond with one line per item in the format:\n"
        "original label -> canonical name\n"
        "or:\n"
        "original label -> UNMAPPED"
    )

    try:
        from .gemini_client import _get_client, _get_model
        from google.genai import types
        import sys

        client = _get_client()
        model = _get_model()

        if verbose:
            print(
                f"  [Gemini] Normalizing {len(unmapped_labels)} unmapped items with {model}...",
                file=sys.stderr,
            )

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a financial document processor.",
                max_output_tokens=4096,
            ),
        )

        # Parse response
        mappings: dict[str, str] = {}
        for line in response.text.strip().splitlines():
            if "->" in line:
                parts = line.split("->", 1)
                original = parts[0].strip().strip("- ")
                mapped = parts[1].strip()
                if mapped.upper() != "UNMAPPED" and mapped in canonical_names:
                    mappings[original] = mapped
        return mappings

    except Exception:
        # LLM unavailable — return empty mappings
        return {}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_normalize.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add sec_parser/normalize.py tests/test_normalize.py
git commit -m "Add hybrid line item normalization module"
```

---

### Task 6: Build the validate module

**Files:**
- Create: `sec_parser/validate.py`
- Create: `tests/test_validate.py`

**Step 1: Write failing tests**

Create `tests/test_validate.py`:

```python
"""Tests for financial statement validation checks."""

import pytest

from sec_parser.validate import (
    ValidationResult,
    validate_balance_sheet,
    validate_income_statement,
    validate_cash_flow,
    validate_cross_statement,
    run_all_checks,
    parse_numeric,
)


class TestParseNumeric:
    def test_simple_number(self):
        assert parse_numeric("1,234") == 1234.0

    def test_negative_parens(self):
        assert parse_numeric("(500)") == -500.0

    def test_with_dollar(self):
        assert parse_numeric("$ 1,234") == 1234.0

    def test_dash(self):
        assert parse_numeric("—") is None

    def test_empty(self):
        assert parse_numeric("") is None

    def test_negative_with_dollar(self):
        assert parse_numeric("$ (1,234)") == -1234.0


class TestValidateBalanceSheet:
    def test_balanced(self):
        data = {
            "Total Assets": [5000.0],
            "Total Liabilities": [3000.0],
            "Total Stockholders' Equity": [2000.0],
        }
        results = validate_balance_sheet(data)
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_off_by_rounding(self):
        data = {
            "Total Assets": [5000.0],
            "Total Liabilities": [3000.0],
            "Total Stockholders' Equity": [2001.0],
        }
        results = validate_balance_sheet(data)
        assert results[0].status == "WARN"

    def test_material_mismatch(self):
        data = {
            "Total Assets": [5000.0],
            "Total Liabilities": [3000.0],
            "Total Stockholders' Equity": [1500.0],
        }
        results = validate_balance_sheet(data)
        assert results[0].status == "FAIL"

    def test_missing_item(self):
        data = {
            "Total Assets": [5000.0],
        }
        results = validate_balance_sheet(data)
        assert results[0].status == "SKIP"


class TestValidateIncomeStatement:
    def test_gross_profit_ties(self):
        data = {
            "Revenue": [1000.0],
            "Cost of Revenue": [600.0],
            "Gross Profit": [400.0],
        }
        results = validate_income_statement(data)
        gp_check = [r for r in results if "Gross profit" in r.check]
        assert gp_check[0].status == "PASS"

    def test_net_income_present(self):
        data = {
            "Net Income": [100.0],
        }
        results = validate_income_statement(data)
        ni_check = [r for r in results if "Net income" in r.check.lower() or "Net Income" in r.check]
        assert any(r.status == "PASS" for r in ni_check)


class TestValidateCashFlow:
    def test_cash_reconciles(self):
        data = {
            "Beginning Cash": [100.0],
            "Net Change in Cash": [50.0],
            "Ending Cash": [150.0],
        }
        results = validate_cash_flow(data)
        recon = [r for r in results if "reconcil" in r.check.lower()]
        assert recon[0].status == "PASS"


class TestRunAllChecks:
    def test_returns_results_for_all_statements(self):
        statements = {
            "income_statement": {"Revenue": [1000.0], "Net Income": [100.0]},
            "balance_sheet": {"Total Assets": [5000.0], "Total Liabilities": [3000.0], "Total Stockholders' Equity": [2000.0]},
            "cash_flow": {"Beginning Cash": [100.0], "Net Change in Cash": [50.0], "Ending Cash": [150.0]},
        }
        results = run_all_checks(statements)
        assert len(results) > 0
        assert all(isinstance(r, ValidationResult) for r in results)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_validate.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement validate module**

Create `sec_parser/validate.py`:

```python
"""Financial statement validation checks."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    check: str
    status: str  # "PASS", "WARN", "FAIL", "SKIP"
    detail: str


def parse_numeric(value: str) -> float | None:
    """Parse a display-formatted number into a float.

    Handles: '1,234', '(500)', '$ 1,234', '$ (1,234)', '—', '-', etc.
    Returns None for non-numeric values.
    """
    if not value or not value.strip():
        return None

    cleaned = value.strip()
    # Remove currency symbols
    cleaned = cleaned.replace("$", "").replace("€", "").replace("£", "").strip()

    # Dashes = zero or missing
    if cleaned in ("—", "-", "–", ""):
        return None

    # Handle parenthetical negatives: (1,234) -> -1234
    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1].strip()

    # Remove commas
    cleaned = cleaned.replace(",", "").strip()

    try:
        result = float(cleaned)
        return -result if negative else result
    except ValueError:
        return None


def _check_equality(
    check_name: str,
    expected: float,
    actual: float,
    tolerance: float = 0.01,
) -> ValidationResult:
    """Compare two values with tolerance, returning PASS/WARN/FAIL."""
    diff = abs(expected - actual)
    if diff == 0:
        return ValidationResult(
            check=check_name,
            status="PASS",
            detail=f"{expected:,.0f} = {actual:,.0f}",
        )

    # Relative tolerance
    base = max(abs(expected), abs(actual), 1)
    rel_diff = diff / base

    if rel_diff <= tolerance:
        return ValidationResult(
            check=check_name,
            status="WARN",
            detail=f"Off by {diff:,.0f} ({rel_diff:.2%})",
        )

    return ValidationResult(
        check=check_name,
        status="FAIL",
        detail=f"Expected {expected:,.0f}, got {actual:,.0f} (diff: {diff:,.0f})",
    )


def _get_first(data: dict[str, list[float]], key: str) -> float | None:
    """Get the first value for a canonical item, or None."""
    values = data.get(key)
    if values and len(values) > 0:
        return values[0]
    return None


def validate_balance_sheet(data: dict[str, list[float]]) -> list[ValidationResult]:
    """Check: Total Assets == Total Liabilities + Total Stockholders' Equity."""
    results = []

    assets = _get_first(data, "Total Assets")
    liabilities = _get_first(data, "Total Liabilities")
    equity = _get_first(data, "Total Stockholders' Equity")

    # Also check the combined line item
    if assets is None:
        assets = _get_first(data, "Total Assets")
    total_le = _get_first(data, "Total Liabilities & Stockholders' Equity")

    if assets is not None and liabilities is not None and equity is not None:
        results.append(_check_equality(
            "Balance sheet balances",
            assets,
            liabilities + equity,
        ))
    elif assets is not None and total_le is not None:
        results.append(_check_equality(
            "Balance sheet balances",
            assets,
            total_le,
        ))
    else:
        missing = []
        if assets is None:
            missing.append("Total Assets")
        if liabilities is None:
            missing.append("Total Liabilities")
        if equity is None:
            missing.append("Total Stockholders' Equity")
        results.append(ValidationResult(
            check="Balance sheet balances",
            status="SKIP",
            detail=f"Missing: {', '.join(missing)}",
        ))

    return results


def validate_income_statement(data: dict[str, list[float]]) -> list[ValidationResult]:
    """Check gross profit and net income."""
    results = []

    revenue = _get_first(data, "Revenue")
    cogs = _get_first(data, "Cost of Revenue")
    gross = _get_first(data, "Gross Profit")

    if revenue is not None and cogs is not None and gross is not None:
        results.append(_check_equality(
            "Gross profit ties",
            gross,
            revenue - abs(cogs),  # COGS is sometimes shown as positive
        ))
    else:
        results.append(ValidationResult(
            check="Gross profit ties",
            status="SKIP",
            detail="Missing revenue, COGS, or gross profit",
        ))

    net_income = _get_first(data, "Net Income")
    if net_income is not None:
        results.append(ValidationResult(
            check="Net Income present",
            status="PASS",
            detail=f"Net Income: {net_income:,.0f}",
        ))
    else:
        results.append(ValidationResult(
            check="Net Income present",
            status="SKIP",
            detail="Net Income not found",
        ))

    return results


def validate_cash_flow(data: dict[str, list[float]]) -> list[ValidationResult]:
    """Check cash reconciliation and activity sections."""
    results = []

    beginning = _get_first(data, "Beginning Cash")
    net_change = _get_first(data, "Net Change in Cash")
    ending = _get_first(data, "Ending Cash")

    if beginning is not None and net_change is not None and ending is not None:
        results.append(_check_equality(
            "Cash flow reconciles",
            ending,
            beginning + net_change,
        ))
    else:
        results.append(ValidationResult(
            check="Cash flow reconciles",
            status="SKIP",
            detail="Missing beginning cash, net change, or ending cash",
        ))

    # Check activity sections present
    ops = _get_first(data, "Net Cash from Operations")
    inv = _get_first(data, "Net Cash from Investing")
    fin = _get_first(data, "Net Cash from Financing")
    present = sum(1 for x in [ops, inv, fin] if x is not None)
    if present == 3:
        results.append(ValidationResult(
            check="All activity sections present",
            status="PASS",
            detail="Operating, Investing, Financing all found",
        ))
    else:
        missing = []
        if ops is None:
            missing.append("Operating")
        if inv is None:
            missing.append("Investing")
        if fin is None:
            missing.append("Financing")
        results.append(ValidationResult(
            check="All activity sections present",
            status="SKIP",
            detail=f"Missing: {', '.join(missing)}",
        ))

    return results


def validate_cross_statement(
    statements: dict[str, dict[str, list[float]]],
) -> list[ValidationResult]:
    """Cross-statement checks: net income IS vs CF, cash CF vs BS."""
    results = []

    is_data = statements.get("income_statement", {})
    cf_data = statements.get("cash_flow", {})
    bs_data = statements.get("balance_sheet", {})

    # Net income cross-check
    is_ni = _get_first(is_data, "Net Income")
    cf_ni = _get_first(cf_data, "Net Income")
    if is_ni is not None and cf_ni is not None:
        results.append(_check_equality(
            "Net income cross-check (IS vs CF)",
            is_ni,
            cf_ni,
        ))

    # Cash cross-check
    cf_ending = _get_first(cf_data, "Ending Cash")
    bs_cash = _get_first(bs_data, "Cash & Cash Equivalents")
    if cf_ending is not None and bs_cash is not None:
        results.append(_check_equality(
            "Cash cross-check (CF vs BS)",
            cf_ending,
            bs_cash,
        ))

    return results


def run_all_checks(
    statements: dict[str, dict[str, list[float]]],
) -> list[ValidationResult]:
    """Run all validation checks across all statements."""
    results = []
    results.extend(validate_balance_sheet(statements.get("balance_sheet", {})))
    results.extend(validate_income_statement(statements.get("income_statement", {})))
    results.extend(validate_cash_flow(statements.get("cash_flow", {})))
    results.extend(validate_cross_statement(statements))
    return results


def render_validation_markdown(results: list[ValidationResult]) -> str:
    """Render validation results as a markdown table."""
    if not results:
        return ""

    lines = [
        "## Validation\n",
        "| Check | Status | Detail |",
        "| :--- | :--- | :--- |",
    ]
    for r in results:
        lines.append(f"| {r.check} | {r.status} | {r.detail} |")

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_validate.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add sec_parser/validate.py tests/test_validate.py
git commit -m "Add financial statement validation module"
```

---

### Task 7: Integrate metadata into the pipeline

**Files:**
- Modify: `sec_parser/pipeline.py:35-115`
- Modify: `sec_parser/markdown_writer.py:47-81`

**Step 1: Update pipeline to extract metadata and pass to markdown writer**

In `sec_parser/pipeline.py`, import the new modules and modify `process_pdf()`:

1. After cover page processing, call `extract_cover_fields()` to get raw fields
2. Extract scale hint from the financial statement section text (search for "(in thousands..." pattern)
3. Call `extract_metadata()` to build the metadata dict
4. Pass metadata to `assemble_markdown()`

Key changes to `pipeline.py`:

```python
# Add imports at top
from .programmatic import clean_prose, extract_cover_fields, parse_cover_page, tables_to_markdown
from .metadata import extract_metadata, metadata_to_yaml

# In process_pdf(), after cover page processing:
cover_fields = []
if COVER_PAGE in sections:
    cover_fields = extract_cover_fields(sections[COVER_PAGE].text)

# Extract scale hint from first financial statement found
scale_hint = ""
for key in FINANCIAL_STATEMENTS:
    if key in sections:
        import re
        m = re.search(r"\(in\s+(?:thousands|millions|billions)[^)]*\)", sections[key].text, re.IGNORECASE)
        if m:
            scale_hint = m.group(0)
            break

metadata = extract_metadata(
    cover_fields=cover_fields,
    scale_hint=scale_hint,
    source_pdf=pdf_path.name,
)

# Update assemble_markdown call
md_content = assemble_markdown(pdf_path.name, processed, metadata=metadata)
```

**Step 2: Update assemble_markdown to emit front-matter**

In `sec_parser/markdown_writer.py`, modify `assemble_markdown()` to accept an optional `metadata` dict and prepend YAML front-matter:

```python
from .metadata import metadata_to_yaml

def assemble_markdown(
    source_filename: str,
    processed: dict[str, str],
    metadata: dict | None = None,
) -> str:
    parts: list[str] = []

    if metadata:
        parts.append(metadata_to_yaml(metadata))
        parts.append("")

    parts.append(f"# {Path(source_filename).stem}\n")
    # ... rest unchanged
```

**Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add sec_parser/pipeline.py sec_parser/markdown_writer.py
git commit -m "Integrate YAML front-matter metadata into pipeline output"
```

---

### Task 8: Integrate normalization into table processing

**Files:**
- Modify: `sec_parser/pipeline.py`
- Modify: `sec_parser/programmatic.py` (the `_render_markdown_table` function)

**Step 1: Add normalization step to the pipeline**

In `pipeline.py`, after processing financial statements but before assembling markdown:

1. Load taxonomy once
2. For each financial statement, extract table rows, run `normalize_table_rows()`
3. Collect unmapped items across all statements
4. Batch-call LLM for unmapped items
5. Apply LLM mappings back

The normalization needs to work on the already-collapsed table data. The cleanest approach: modify `tables_to_markdown()` to accept an optional taxonomy and return both markdown and a structured data dict (for validation).

Add a new function `tables_to_markdown_normalized()` in `programmatic.py` that wraps `tables_to_markdown` with normalization, or modify the rendering to insert the Canonical column.

Key change — update `_render_markdown_table` to handle an optional canonical column by modifying the header to include "Canonical":

```python
# In pipeline.py, add normalization pass:
from .normalize import load_taxonomy, normalize_table_rows, collect_unmapped, llm_normalize_batch

taxonomy = load_taxonomy()

# After all financial statements are processed, re-process with normalization
# This requires changing tables_to_markdown to return structured data too
```

Actually, the cleanest approach is to normalize at the row level inside `tables_to_markdown`. Add an optional `taxonomy` parameter:

In `sec_parser/programmatic.py`, modify `tables_to_markdown()` to accept `taxonomy: dict | None = None`. If provided, after collapsing rows, run `normalize_table_rows()` on each table's data rows and adjust `_render_markdown_table` to include the Canonical column.

The header row gets "Canonical" inserted at index 1, and the separator row gets an extra `:---` entry at index 1.

**Step 2: Run tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add sec_parser/programmatic.py sec_parser/pipeline.py
git commit -m "Integrate line item normalization into table rendering"
```

---

### Task 9: Integrate validation into the pipeline

**Files:**
- Modify: `sec_parser/pipeline.py`
- Modify: `sec_parser/markdown_writer.py`

**Step 1: Extract numeric data from normalized tables for validation**

After normalization, build a `statements` dict mapping statement type to `{canonical_name: [values]}`. This requires parsing the numeric values from the normalized table rows.

Add a helper function in `validate.py`:

```python
def extract_statement_data(
    rows: list[list[str]],
) -> dict[str, list[float]]:
    """Extract canonical_name -> [numeric values] from normalized rows.

    Assumes rows have format: [label, canonical, val1, val2, ...].
    """
    data: dict[str, list[float]] = {}
    for row in rows:
        if len(row) < 3:
            continue
        canonical = row[1].strip() if len(row) > 1 else ""
        if not canonical:
            continue
        values = []
        for cell in row[2:]:
            v = parse_numeric(cell)
            if v is not None:
                values.append(v)
        if values:
            data[canonical] = values
    return data
```

**Step 2: Wire validation into pipeline**

In `pipeline.py`, after normalization:

1. Build statement data dicts from normalized rows
2. Call `run_all_checks()`
3. Call `render_validation_markdown()`
4. Pass validation markdown to `assemble_markdown()`

Update `assemble_markdown()` to accept optional `validation_markdown: str` and append it at the end of the document.

**Step 3: Run tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add sec_parser/pipeline.py sec_parser/markdown_writer.py sec_parser/validate.py
git commit -m "Integrate validation checks into pipeline output"
```

---

### Task 10: Add multi-filing consistency pass

**Files:**
- Modify: `sec_parser/cli.py:60-78`
- Create: `sec_parser/consistency.py`
- Create: `tests/test_consistency.py`

**Step 1: Write failing tests**

Create `tests/test_consistency.py`:

```python
"""Tests for multi-filing consistency."""

import pytest

from sec_parser.consistency import enforce_consistent_mappings


class TestEnforceConsistentMappings:
    def test_forces_same_mapping(self):
        # Filing 1 mapped "Net revenues" -> "Revenue"
        # Filing 2 has "Net revenues" unmapped
        filing_mappings = [
            {"Net revenues": "Revenue", "Cost of sales": "Cost of Revenue"},
            {"Net revenues": "", "Cost of sales": "Cost of Revenue"},
        ]
        result = enforce_consistent_mappings(filing_mappings)
        assert result[1]["Net revenues"] == "Revenue"

    def test_no_conflict(self):
        filing_mappings = [
            {"Net revenues": "Revenue"},
            {"Total revenues": "Revenue"},
        ]
        result = enforce_consistent_mappings(filing_mappings)
        assert result[0]["Net revenues"] == "Revenue"
        assert result[1]["Total revenues"] == "Revenue"

    def test_empty_input(self):
        assert enforce_consistent_mappings([]) == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_consistency.py -v`
Expected: FAIL

**Step 3: Implement consistency module**

Create `sec_parser/consistency.py`:

```python
"""Multi-filing consistency: ensure same line items get same canonical names."""

from __future__ import annotations


def enforce_consistent_mappings(
    filing_mappings: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Ensure the same line item label maps to the same canonical name across filings.

    Takes a list of {original_label: canonical_name} dicts (one per filing).
    If a label is mapped in one filing but not another, the known mapping is applied.
    """
    if not filing_mappings:
        return []

    # Build global mapping: label -> canonical (first non-empty wins)
    global_map: dict[str, str] = {}
    for mapping in filing_mappings:
        for label, canonical in mapping.items():
            if canonical and label not in global_map:
                global_map[label] = canonical

    # Apply global mapping to all filings
    result = []
    for mapping in filing_mappings:
        updated = dict(mapping)
        for label in updated:
            if not updated[label] and label in global_map:
                updated[label] = global_map[label]
        result.append(updated)

    return result
```

**Step 4: Run tests**

Run: `pytest tests/test_consistency.py -v`
Expected: All PASS

**Step 5: Integrate into CLI**

In `sec_parser/cli.py`, after the loop processing all PDFs:

1. If multiple filings were processed, collect the normalization mappings from each
2. Call `enforce_consistent_mappings()`
3. Re-write markdown files with updated canonical columns

This requires `process_pdf()` to return the mapping data alongside the output path. Modify `process_pdf()` to return a dataclass with both:

```python
@dataclass
class ProcessingResult:
    output_path: Path
    mappings: dict[str, str]  # label -> canonical for this filing
    metadata: dict  # front-matter metadata
```

Then in `cli.py`, after processing all filings, run the consistency pass and update files if needed.

**Step 6: Add filing_sequence to metadata**

After consistency pass, sort results by `period_end` and assign `filing_sequence` numbers, then update the YAML front-matter in each file.

**Step 7: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add sec_parser/consistency.py tests/test_consistency.py sec_parser/cli.py sec_parser/pipeline.py
git commit -m "Add multi-filing consistency pass and filing sequence numbering"
```

---

### Task 11: End-to-end integration test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

Create a test that processes a small synthetic PDF-like input through the full pipeline and verifies:
- YAML front-matter is present and correct
- Canonical column appears in financial tables
- Validation section is present
- Key metadata fields are populated

Since we can't easily create a real PDF in tests, test the pipeline from the `split_sections` output onward by mocking `extract_pdf`.

**Step 2: Run tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "Add end-to-end integration test for enhanced pipeline"
```

---

### Task 12: Manual test with real filing

**Step 1: Run parser on a real filing**

Run: `sec-parse ./filings/ -o ./output/ --verbose`

**Step 2: Inspect output**

Verify:
- YAML front-matter block at top of each file
- Canonical column in financial statement tables
- Validation section at bottom
- No regressions in existing output quality

**Step 3: Commit any fixes discovered during manual testing**
