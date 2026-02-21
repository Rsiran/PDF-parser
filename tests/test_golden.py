"""Golden file tests: assert specific values in output/3QStrive.md stay stable."""

import re
from pathlib import Path

import pytest

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "output" / "3QStrive.md"


@pytest.fixture(scope="module")
def golden_md():
    """Read the golden markdown file."""
    assert GOLDEN_PATH.exists(), f"Golden file not found: {GOLDEN_PATH}"
    return GOLDEN_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sections(golden_md):
    """Split golden file on ## headings into {title: content} dict."""
    result = {}
    current_title = ""
    current_lines = []
    for line in golden_md.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            if current_title:
                result[current_title] = "\n".join(current_lines).strip()
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title:
        result[current_title] = "\n".join(current_lines).strip()
    return result


def _extract_value(content: str, row_label: str, col_index: int) -> str:
    """Pull a table cell value by row label and column index.

    col_index is 0-based among data columns (excludes the label column).
    """
    for line in content.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # split on | gives empty strings at edges: ['', 'label', 'v1', 'v2', '']
        cells = [c for c in cells if c is not None]  # keep empty strings between pipes
        # Re-split properly
        parts = line.split("|")
        # parts[0] is before first pipe (empty), parts[-1] is after last pipe (empty)
        data = [p.strip() for p in parts[1:-1]]
        if len(data) < 2:
            continue
        label = data[0]
        if row_label.lower() in label.lower():
            if col_index + 1 < len(data):
                return data[col_index + 1]
    return ""


# ---------------------------------------------------------------------------
# Section Structure
# ---------------------------------------------------------------------------

class TestGoldenSectionStructure:
    def test_all_expected_sections_present(self, sections):
        expected = [
            "Cover Page",
            "Consolidated Balance Sheets",
            "Consolidated Statements of Income",
            "Consolidated Statements of Cash Flows",
            "Consolidated Statements of Stockholders' Equity",
            "Notes to Financial Statements",
        ]
        for sec in expected:
            assert any(sec.lower() in k.lower() for k in sections), f"Missing section: {sec}"

    def test_section_ordering(self, golden_md):
        ordered = [
            "Cover Page",
            "Consolidated Balance Sheets",
            "Consolidated Statements of Income",
            "Consolidated Statements of Cash Flows",
            "Consolidated Statements of Stockholders' Equity",
            "Notes to Financial Statements",
        ]
        positions = []
        for sec in ordered:
            pos = golden_md.lower().find(f"## {sec.lower()}")
            assert pos >= 0, f"Section not found: {sec}"
            positions.append(pos)
        assert positions == sorted(positions), "Sections are out of order"

    def test_total_section_count(self, sections):
        assert len(sections) >= 15


# ---------------------------------------------------------------------------
# Cover Page
# ---------------------------------------------------------------------------

class TestGoldenCoverPage:
    def test_filing_type(self, sections):
        cover = sections.get("Cover Page", "")
        assert "| Filing Type | 10-Q |" in cover

    def test_company(self, sections):
        cover = sections.get("Cover Page", "")
        assert "| Company | STRIVE, INC. |" in cover

    def test_period(self, sections):
        cover = sections.get("Cover Page", "")
        assert "| Period Ended | September 30, 2025 |" in cover

    def test_shares_outstanding(self, sections):
        cover = sections.get("Cover Page", "")
        assert "592,579,510" in cover


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------

class TestGoldenBalanceSheet:
    def _get_bs(self, sections):
        return sections.get("Consolidated Balance Sheets", "")

    def test_header_columns(self, sections):
        bs = self._get_bs(sections)
        assert "September 30, 2025 (Successor, unaudited)" in bs
        assert "December 31, 2024 (Predecessor, audited)" in bs

    def test_cash(self, sections):
        bs = self._get_bs(sections)
        assert "Cash and cash equivalents | $ 109,069 | $ 6,155" in bs

    def test_total_assets(self, sections):
        bs = self._get_bs(sections)
        assert "Total assets | $ 792,576 | $ 28,197" in bs

    def test_total_liabilities(self, sections):
        bs = self._get_bs(sections)
        assert "Total liabilities | 13,147 | 4,855" in bs

    def test_total_equity(self, sections):
        bs = self._get_bs(sections)
        assert "Total stockholders\u2019 equity | 779,429 | 23,342" in bs

    def test_accumulated_deficit(self, sections):
        bs = self._get_bs(sections)
        assert "Accumulated deficit | (268,423) | (49,146)" in bs


# ---------------------------------------------------------------------------
# Income Statement
# ---------------------------------------------------------------------------

class TestGoldenIncomeStatement:
    def _get_is(self, sections):
        return sections.get("Consolidated Statements of Income", "")

    def test_quarterly_subtitle(self, sections):
        content = self._get_is(sections)
        assert "### CONSOLIDATED STATEMENTS OF OPERATIONS (Quarterly)" in content

    def test_ytd_subtitle(self, sections):
        content = self._get_is(sections)
        assert "### CONSOLIDATED STATEMENTS OF OPERATIONS (Year-to-Date)" in content

    def test_quarterly_headers(self, sections):
        content = self._get_is(sections)
        assert "Successor:" in content
        assert "Predecessor:" in content

    def test_net_loss_quarterly(self, sections):
        content = self._get_is(sections)
        # Find the quarterly section (before Year-to-Date)
        ytd_pos = content.find("(Year-to-Date)")
        quarterly = content[:ytd_pos] if ytd_pos > 0 else content
        assert "Net loss | $ (192,287) | $ (14,366) | $ (6,802)" in quarterly

    def test_net_loss_ytd(self, sections):
        content = self._get_is(sections)
        ytd_pos = content.find("(Year-to-Date)")
        ytd = content[ytd_pos:] if ytd_pos > 0 else ""
        assert "Net loss | $ (192,287) | $ (26,990) | $ (17,462)" in ytd


# ---------------------------------------------------------------------------
# Cash Flows
# ---------------------------------------------------------------------------

class TestGoldenCashFlow:
    def _get_cf(self, sections):
        return sections.get("Consolidated Statements of Cash Flows", "")

    def test_cash_end_of_period(self, sections):
        cf = self._get_cf(sections)
        assert "Cash and cash equivalents, end of period | $ 109,069 | $ 3,923 | $ 3,764" in cf

    def test_net_loss(self, sections):
        cf = self._get_cf(sections)
        assert "Net loss | $ (192,287) | $ (26,990) | $ (17,462)" in cf

    def test_operating_activities(self, sections):
        cf = self._get_cf(sections)
        assert "Net cash used in operating activities | (13,955) | (18,209) | (15,522)" in cf

    def test_digital_asset_purchase(self, sections):
        cf = self._get_cf(sections)
        assert "Purchases of digital assets | (675,008)" in cf


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------

class TestGoldenEquity:
    def _get_eq(self, sections):
        return sections.get("Consolidated Statements of Stockholders' Equity", "")

    def test_14_column_header(self, sections):
        eq = self._get_eq(sections)
        # Find separator row
        for line in eq.splitlines():
            if re.match(r"^\|[\s:|-]+\|$", line.strip()):
                # Count ---: markers (data columns are right-aligned)
                markers = re.findall(r"---:", line)
                assert len(markers) == 13, f"Expected 13 right-aligned columns, got {len(markers)}"
                # Total cells = 14 (1 left-aligned label + 13 right-aligned data)
                cells = [c.strip() for c in line.split("|") if c.strip()]
                assert len(cells) == 14, f"Expected 14 columns, got {len(cells)}"
                return
        pytest.fail("No separator row found in equity section")

    def test_column_names(self, sections):
        eq = self._get_eq(sections)
        assert "Pref. Stock Shares" in eq
        assert "APIC" in eq
        assert "Total Equity" in eq

    def test_final_balance(self, sections):
        eq = self._get_eq(sections)
        # Find the final balance row
        found = False
        for line in eq.splitlines():
            if "Balance at September 30, 2025" in line:
                assert "448,817,597" in line
                assert "$ 779,429" in line
                found = True
                break
        assert found, "Final balance row not found"


# ---------------------------------------------------------------------------
# Cross-Statement Consistency
# ---------------------------------------------------------------------------

class TestGoldenCrossStatementConsistency:
    """The most important tests — catches wrong numbers that no structural check finds."""

    def test_assets_equals_liabilities_plus_equity(self, sections):
        bs = sections.get("Consolidated Balance Sheets", "")
        assert "Total assets | $ 792,576" in bs
        assert "Total liabilities and stockholders' equity | $ 792,576" in bs

    def test_cash_balance_sheet_matches_cash_flow(self, sections):
        bs = sections.get("Consolidated Balance Sheets", "")
        cf = sections.get("Consolidated Statements of Cash Flows", "")
        # Balance sheet: Cash = $109,069
        assert "Cash and cash equivalents | $ 109,069" in bs
        # Cash flow: end of period = $109,069
        assert "Cash and cash equivalents, end of period | $ 109,069" in cf

    def test_accumulated_deficit_consistent(self, sections):
        bs = sections.get("Consolidated Balance Sheets", "")
        eq = sections.get("Consolidated Statements of Stockholders' Equity", "")
        # Balance sheet accumulated deficit
        assert "(268,423)" in bs
        # Equity final row should also have this
        final_line = ""
        for line in eq.splitlines():
            if "Balance at September 30, 2025" in line and "448,817,597" in line:
                final_line = line
                break
        assert "(268,423)" in final_line, "Accumulated deficit mismatch between BS and equity"

    def test_net_loss_income_to_cash_flow(self, sections):
        income = sections.get("Consolidated Statements of Income", "")
        cf = sections.get("Consolidated Statements of Cash Flows", "")
        # Both YTD sections should show same net loss
        # Income YTD: Net loss | $ (192,287) | $ (26,990) | $ (17,462)
        assert "Net loss | $ (192,287) | $ (26,990) | $ (17,462)" in income
        assert "Net loss | $ (192,287) | $ (26,990) | $ (17,462)" in cf
