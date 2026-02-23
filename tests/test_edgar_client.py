"""Tests for sec_parser.edgar_client — XBRL data fetching and parsing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sec_parser.edgar_client import (
    EdgarFetchError,
    XBRLStatementData,
    _accession_to_prefix,
    clear_cache,
    extract_statement_facts,
    find_filing_accession,
    load_xbrl_taxonomy_map,
    pad_cik,
    render_xbrl_statement,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def company_facts():
    with open(FIXTURES / "company_facts_sample.json") as f:
        return json.load(f)


@pytest.fixture
def submissions():
    with open(FIXTURES / "submissions_sample.json") as f:
        return json.load(f)


class TestPadCik:
    def test_string_padding(self):
        assert pad_cik("320193") == "0000320193"

    def test_already_padded(self):
        assert pad_cik("0000320193") == "0000320193"

    def test_int_padding(self):
        assert pad_cik(320193) == "0000320193"

    def test_short_cik(self):
        assert pad_cik("1") == "0000000001"


class TestAccessionPrefix:
    def test_removes_dashes(self):
        assert _accession_to_prefix("0000320193-24-000123") == "000032019324000123"


class TestFindFilingAccession:
    def test_finds_10k(self, submissions):
        acc = find_filing_accession(submissions, "10-K", "2024-09-28")
        assert acc == "0000320193-24-000123"

    def test_finds_10q(self, submissions):
        acc = find_filing_accession(submissions, "10-Q", "2024-06-29")
        assert acc == "0000320193-24-000100"

    def test_returns_none_for_missing(self, submissions):
        acc = find_filing_accession(submissions, "10-K", "2025-09-28")
        assert acc is None

    def test_returns_none_for_empty_submissions(self):
        acc = find_filing_accession({}, "10-K", "2024-09-28")
        assert acc is None


class TestExtractStatementFacts:
    def test_extracts_income_statement(self, company_facts):
        xbrl_map = {
            "Revenues": "Revenue",
            "CostOfGoodsAndServicesSold": "Cost of Revenue",
            "GrossProfit": "Gross Profit",
            "NetIncomeLoss": "Net Income",
        }
        result = extract_statement_facts(
            company_facts, "0000320193-24-000123", "income_statement", xbrl_map
        )
        assert result is not None
        assert result.statement_type == "income_statement"
        assert "Revenue" in result.line_items
        assert "Net Income" in result.line_items
        assert len(result.periods) >= 1

    def test_returns_none_for_missing_accession(self, company_facts):
        xbrl_map = {"Revenues": "Revenue"}
        result = extract_statement_facts(
            company_facts, "9999999999-99-999999", "income_statement", xbrl_map
        )
        assert result is None

    def test_returns_none_for_empty_facts(self):
        result = extract_statement_facts(
            {"facts": {}}, "0000320193-24-000123", "income_statement", {"Revenues": "Revenue"}
        )
        assert result is None


class TestLoadXbrlTaxonomyMap:
    def test_loads_all_statement_types(self):
        mapping = load_xbrl_taxonomy_map()
        assert "income_statement" in mapping
        assert "balance_sheet" in mapping
        assert "cash_flow" in mapping
        assert "stockholders_equity" in mapping
        assert "comprehensive_income" in mapping

    def test_maps_to_valid_canonical_names(self):
        """All canonical names in XBRL map should exist in taxonomy.yaml."""
        import yaml
        taxonomy_path = Path(__file__).parent.parent / "sec_parser" / "taxonomy.yaml"
        with open(taxonomy_path) as f:
            taxonomy = yaml.safe_load(f)

        # Collect all canonical names from taxonomy
        valid_canonicals = set()
        for section in taxonomy.values():
            for item in section.values():
                valid_canonicals.add(item["canonical"])

        # Also add equity-specific names that aren't in taxonomy.yaml yet
        extra_valid = {
            "Additional Paid-in Capital",
            "Treasury Stock",
            "AOCI",
            "Foreign Currency Translation",
            "Unrealized Gains/Losses on Securities",
            "Cash Flow Hedges",
            "Pension Adjustments",
            "Other Comprehensive Income",
            "Total Comprehensive Income",
        }

        xbrl_map = load_xbrl_taxonomy_map()
        for statement_type, concepts in xbrl_map.items():
            for xbrl_concept, canonical in concepts.items():
                assert canonical in valid_canonicals or canonical in extra_valid, (
                    f"XBRL concept '{xbrl_concept}' maps to '{canonical}' which is not "
                    f"in taxonomy.yaml (statement: {statement_type})"
                )


class TestRenderXbrlStatement:
    def test_renders_markdown_table(self):
        data = XBRLStatementData(
            statement_type="income_statement",
            line_items={
                "Revenue": [391035000000, 383285000000],
                "Net Income": [93736000000, 96995000000],
            },
            periods=["2024-09-28", "2023-09-30"],
        )
        md = render_xbrl_statement(data)
        assert "| Revenue |" in md
        assert "| Net Income |" in md
        assert "2024-09-28" in md
        assert "---:" in md  # right-aligned columns

    def test_handles_none_values(self):
        data = XBRLStatementData(
            statement_type="income_statement",
            line_items={"Revenue": [100, None]},
            periods=["2024", "2023"],
        )
        md = render_xbrl_statement(data)
        assert "\u2014" in md

    def test_empty_data_returns_empty(self):
        data = XBRLStatementData(
            statement_type="income_statement",
            line_items={},
            periods=[],
        )
        assert render_xbrl_statement(data) == ""


class TestEdgarFetchError:
    def test_missing_email_raises(self):
        """fetch_company_facts should raise when SEC_EDGAR_EMAIL is not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove the env var if present
            import os
            os.environ.pop("SEC_EDGAR_EMAIL", None)
            from sec_parser.edgar_client import _get_user_agent
            with pytest.raises(EdgarFetchError, match="SEC_EDGAR_EMAIL"):
                _get_user_agent()


@pytest.fixture(autouse=True)
def _clear_edgar_cache():
    """Clear EDGAR cache before each test."""
    clear_cache()
    yield
    clear_cache()
