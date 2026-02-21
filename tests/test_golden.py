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
        assert len(sections) >= 10


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
        assert "| Period | September 30, 2025 |" in cover

    def test_commission_file_number(self, sections):
        cover = sections.get("Cover Page", "")
        assert "| Commission File Number | 001-41612 |" in cover


# ---------------------------------------------------------------------------
# Income Statement
# ---------------------------------------------------------------------------

class TestGoldenIncomeStatement:
    def _get_is(self, sections):
        return sections.get("Consolidated Statements of Income", "")

    def test_total_revenues(self, sections):
        content = self._get_is(sections)
        assert "Total revenues | Revenue | 255 | 1,288 | 984 |" in content

    def test_total_operating_expenses(self, sections):
        content = self._get_is(sections)
        assert "Total operating expenses | Total Operating Expenses | 19,477 | 5,384 | 7,994 |" in content

    def test_net_loss_quarterly(self, sections):
        content = self._get_is(sections)
        assert "Net loss | Net Income | $ (192,287) | $ (14,366) | $ (6,802) |" in content

    def test_net_loss_ytd(self, sections):
        content = self._get_is(sections)
        assert "Net loss | Net Income | $ (192,287) | $ (26,990) | $ (17,462) |" in content

    def test_has_canonical_column(self, sections):
        content = self._get_is(sections)
        assert "Depreciation & Amortization" in content
        assert "Selling, General & Administrative" in content


# ---------------------------------------------------------------------------
# Cash Flows
# ---------------------------------------------------------------------------

class TestGoldenCashFlow:
    def _get_cf(self, sections):
        return sections.get("Consolidated Statements of Cash Flows", "")

    def test_cash_end_of_period(self, sections):
        cf = self._get_cf(sections)
        assert "Cash and cash equivalents, end of period | Ending Cash | $ 109,069 | $ 3,923 | $ 3,764 |" in cf

    def test_net_loss(self, sections):
        cf = self._get_cf(sections)
        assert "Net loss | Net Income | $ (192,287) | $ (26,990) | $ (17,462) |" in cf

    def test_operating_activities(self, sections):
        cf = self._get_cf(sections)
        assert "Net cash used in operating activities | Net Cash from Operations | (13,955) | (18,209) | (15,522) |" in cf

    def test_digital_asset_purchase(self, sections):
        cf = self._get_cf(sections)
        assert "Purchases of digital assets |" in cf
        assert "(675,008)" in cf


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------

class TestGoldenEquity:
    def _get_eq(self, sections):
        return sections.get("Consolidated Statements of Stockholders' Equity", "")

    def test_15_column_header(self, sections):
        eq = self._get_eq(sections)
        # Find separator row — 15 columns (1 label + 1 canonical + 13 data)
        for line in eq.splitlines():
            if re.match(r"^\|.*---.*\|$", line.strip()) and "---" in line and not any(c.isalpha() for c in line.replace("|", "")):
                # Count columns by splitting on pipe
                cols = [c.strip() for c in line.split("|")[1:-1]]
                assert len(cols) == 15, f"Expected 15 columns, got {len(cols)}"
                return
        pytest.fail("No separator row found in equity section")

    def test_final_balance(self, sections):
        eq = self._get_eq(sections)
        found = False
        for line in eq.splitlines():
            if "Balance at September 30, 2025" in line:
                assert "448,817,597" in line
                assert "$ 779,429" in line
                found = True
                break
        assert found, "Final balance row not found"

    def test_accumulated_deficit_in_final_row(self, sections):
        eq = self._get_eq(sections)
        for line in eq.splitlines():
            if "Balance at September 30, 2025" in line and "448,817,597" in line:
                assert "(268,423)" in line
                return
        pytest.fail("Final balance row not found")


# ---------------------------------------------------------------------------
# Cross-Statement Consistency
# ---------------------------------------------------------------------------

class TestGoldenCrossStatementConsistency:
    """The most important tests — catches wrong numbers that no structural check finds."""

    def test_net_loss_income_to_cash_flow(self, sections):
        income = sections.get("Consolidated Statements of Income", "")
        cf = sections.get("Consolidated Statements of Cash Flows", "")
        # Both YTD sections should show same net loss
        assert "Net loss | Net Income | $ (192,287) | $ (26,990) | $ (17,462)" in income
        assert "Net loss | Net Income | $ (192,287) | $ (26,990) | $ (17,462)" in cf

    def test_cash_flow_beginning_end_reconcile(self, sections):
        cf = sections.get("Consolidated Statements of Cash Flows", "")
        assert "Cash and cash equivalents, beginning of period | Beginning Cash | 3,923 | 6,155 | 2,086 |" in cf
        assert "Cash and cash equivalents, end of period | Ending Cash | $ 109,069 | $ 3,923 | $ 3,764 |" in cf

    def test_equity_net_loss_matches_income(self, sections):
        eq = sections.get("Consolidated Statements of Stockholders' Equity", "")
        # The final Successor period net loss in equity should be (192,287)
        for line in eq.splitlines():
            if "Net loss" in line and "(192,287)" in line:
                return
        pytest.fail("Net loss (192,287) not found in equity statement")
