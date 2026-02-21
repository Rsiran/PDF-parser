"""Tests for the validate module — financial statement sanity checks."""

from __future__ import annotations

import pytest

from sec_parser.validate import (
    ValidationResult,
    parse_numeric,
    _check_equality,
    validate_balance_sheet,
    validate_income_statement,
    validate_cash_flow,
    validate_cross_statement,
    run_all_checks,
    render_validation_markdown,
    extract_statement_data,
)


# ---------------------------------------------------------------------------
# TestParseNumeric
# ---------------------------------------------------------------------------

class TestParseNumeric:
    def test_simple_number(self):
        assert parse_numeric("1,234") == 1234.0

    def test_negative_parens(self):
        assert parse_numeric("(500)") == -500.0

    def test_with_dollar(self):
        assert parse_numeric("$1,234") == 1234.0

    def test_dash_returns_none(self):
        assert parse_numeric("—") is None
        assert parse_numeric("-") is None
        assert parse_numeric("–") is None

    def test_empty_returns_none(self):
        assert parse_numeric("") is None
        assert parse_numeric("  ") is None

    def test_dollar_parens(self):
        assert parse_numeric("$ (1,234)") == -1234.0

    def test_decimal(self):
        assert parse_numeric("1,234.56") == 1234.56

    def test_euro(self):
        assert parse_numeric("€500") == 500.0


# ---------------------------------------------------------------------------
# TestCheckEquality
# ---------------------------------------------------------------------------

class TestCheckEquality:
    def test_exact_match(self):
        result = _check_equality("test", 100.0, 100.0)
        assert result.status == "PASS"

    def test_within_tolerance_warn(self):
        # 0.5% off — within 1% tolerance
        result = _check_equality("test", 1000.0, 1005.0)
        assert result.status == "WARN"

    def test_beyond_tolerance_fail(self):
        # 5% off — beyond 1% tolerance
        result = _check_equality("test", 1000.0, 1050.0)
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# TestValidateBalanceSheet
# ---------------------------------------------------------------------------

class TestValidateBalanceSheet:
    def test_balanced_pass(self):
        data = {
            "Total Assets": [1000.0],
            "Total Liabilities": [600.0],
            "Total Stockholders' Equity": [400.0],
        }
        results = validate_balance_sheet(data)
        statuses = [r.status for r in results]
        assert "PASS" in statuses

    def test_off_by_rounding_warn(self):
        data = {
            "Total Assets": [1000.0],
            "Total Liabilities": [600.0],
            "Total Stockholders' Equity": [405.0],  # 0.5% off
        }
        results = validate_balance_sheet(data)
        statuses = [r.status for r in results]
        assert "WARN" in statuses

    def test_material_mismatch_fail(self):
        data = {
            "Total Assets": [1000.0],
            "Total Liabilities": [600.0],
            "Total Stockholders' Equity": [500.0],  # 10% off
        }
        results = validate_balance_sheet(data)
        statuses = [r.status for r in results]
        assert "FAIL" in statuses

    def test_missing_item_skip(self):
        data = {
            "Total Assets": [1000.0],
        }
        results = validate_balance_sheet(data)
        statuses = [r.status for r in results]
        assert "SKIP" in statuses

    def test_total_liabilities_and_equity_line(self):
        """When Total Liabilities & Stockholders' Equity line exists."""
        data = {
            "Total Assets": [1000.0],
            "Total Liabilities & Stockholders' Equity": [1000.0],
        }
        results = validate_balance_sheet(data)
        statuses = [r.status for r in results]
        assert "PASS" in statuses


# ---------------------------------------------------------------------------
# TestValidateIncomeStatement
# ---------------------------------------------------------------------------

class TestValidateIncomeStatement:
    def test_gross_profit_ties_pass(self):
        data = {
            "Revenue": [1000.0],
            "Cost of Revenue": [600.0],
            "Gross Profit": [400.0],
        }
        results = validate_income_statement(data)
        gp_results = [r for r in results if "Gross Profit" in r.check]
        assert any(r.status == "PASS" for r in gp_results)

    def test_net_income_present_pass(self):
        data = {
            "Net Income": [100.0],
        }
        results = validate_income_statement(data)
        ni_results = [r for r in results if "Net Income" in r.check]
        assert any(r.status == "PASS" for r in ni_results)

    def test_missing_items_skip(self):
        data = {
            "Revenue": [1000.0],
        }
        results = validate_income_statement(data)
        gp_results = [r for r in results if "Gross Profit" in r.check]
        assert any(r.status == "SKIP" for r in gp_results)


# ---------------------------------------------------------------------------
# TestValidateCashFlow
# ---------------------------------------------------------------------------

class TestValidateCashFlow:
    def test_cash_reconciles_pass(self):
        data = {
            "Beginning Cash": [100.0],
            "Net Change in Cash": [50.0],
            "Ending Cash": [150.0],
        }
        results = validate_cash_flow(data)
        cash_results = [r for r in results if "Cash Reconcil" in r.check]
        assert any(r.status == "PASS" for r in cash_results)

    def test_activity_sections_present(self):
        data = {
            "Net Cash from Operations": [100.0],
            "Net Cash from Investing": [-50.0],
            "Net Cash from Financing": [-30.0],
        }
        results = validate_cash_flow(data)
        section_results = [r for r in results if "Activity Sections" in r.check]
        assert any(r.status == "PASS" for r in section_results)

    def test_missing_activity_sections(self):
        data = {
            "Net Cash from Operations": [100.0],
        }
        results = validate_cash_flow(data)
        section_results = [r for r in results if "Activity Sections" in r.check]
        assert any(r.status in ("WARN", "FAIL") for r in section_results)


# ---------------------------------------------------------------------------
# TestRunAllChecks
# ---------------------------------------------------------------------------

class TestRunAllChecks:
    def test_returns_results_for_all_statement_types(self):
        statements = {
            "balance_sheet": {
                "Total Assets": [1000.0],
                "Total Liabilities": [600.0],
                "Total Stockholders' Equity": [400.0],
            },
            "income_statement": {
                "Revenue": [1000.0],
                "Cost of Revenue": [600.0],
                "Gross Profit": [400.0],
                "Net Income": [100.0],
            },
            "cash_flow": {
                "Beginning Cash": [100.0],
                "Net Change in Cash": [50.0],
                "Ending Cash": [150.0],
                "Net Cash from Operations": [200.0],
                "Net Cash from Investing": [-100.0],
                "Net Cash from Financing": [-50.0],
            },
        }
        results = run_all_checks(statements)
        assert isinstance(results, list)
        assert all(isinstance(r, ValidationResult) for r in results)
        assert len(results) >= 3  # at least one check per statement type

    def test_empty_statements(self):
        results = run_all_checks({})
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# TestRenderValidationMarkdown
# ---------------------------------------------------------------------------

class TestRenderValidationMarkdown:
    def test_renders_table(self):
        results = [
            ValidationResult(check="BS Balance", status="PASS", detail="OK"),
            ValidationResult(check="GP Check", status="WARN", detail="Off by 0.5%"),
        ]
        md = render_validation_markdown(results)
        assert "| Check" in md
        assert "| Status" in md
        assert "BS Balance" in md
        assert "PASS" in md

    def test_empty_results(self):
        md = render_validation_markdown([])
        assert md == ""


# ---------------------------------------------------------------------------
# TestExtractStatementData
# ---------------------------------------------------------------------------

class TestExtractStatementData:
    def test_basic_extraction(self):
        rows = [
            ["Revenue", "Revenue", "1,000", "900"],
            ["Cost of sales", "Cost of Revenue", "600", "500"],
            ["Some notes", "", "—", "—"],
        ]
        data = extract_statement_data(rows)
        assert "Revenue" in data
        assert data["Revenue"] == [1000.0, 900.0]
        assert "Cost of Revenue" in data
        assert data["Cost of Revenue"] == [600.0, 500.0]
        # Empty canonical should be skipped
        assert "" not in data

    def test_empty_rows(self):
        data = extract_statement_data([])
        assert data == {}
