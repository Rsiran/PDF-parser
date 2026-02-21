"""Tests for sec_parser.metadata module."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from sec_parser.metadata import (
    extract_metadata,
    infer_period_type,
    infer_scale,
    metadata_to_yaml,
)


# ---------------------------------------------------------------------------
# infer_period_type
# ---------------------------------------------------------------------------

class TestInferPeriodType:
    def test_10k_returns_fy(self):
        assert infer_period_type("10-K", "December 31, 2024") == "FY"

    def test_10k_a_returns_fy(self):
        assert infer_period_type("10-K/A", "December 31, 2024") == "FY"

    def test_10q_march_returns_q1(self):
        assert infer_period_type("10-Q", "March 31, 2024") == "Q1"

    def test_10q_june_returns_q2(self):
        assert infer_period_type("10-Q", "June 30, 2024") == "Q2"

    def test_10q_september_returns_q3(self):
        assert infer_period_type("10-Q", "September 30, 2024") == "Q3"

    def test_10q_unknown_month_returns_q_unknown(self):
        assert infer_period_type("10-Q", "December 31, 2024") == "Q?"

    def test_10q_no_period_returns_q_unknown(self):
        assert infer_period_type("10-Q", "") == "Q?"

    def test_case_insensitive_month(self):
        assert infer_period_type("10-Q", "JUNE 30, 2024") == "Q2"


# ---------------------------------------------------------------------------
# infer_scale
# ---------------------------------------------------------------------------

class TestInferScale:
    def test_thousands(self):
        assert infer_scale("(in thousands, except per share data)") == "thousands"

    def test_millions(self):
        assert infer_scale("(In millions)") == "millions"

    def test_billions(self):
        assert infer_scale("(in billions)") == "billions"

    def test_units_fallback(self):
        assert infer_scale("something else entirely") == "units"

    def test_empty_string(self):
        assert infer_scale("") == "units"

    def test_none(self):
        assert infer_scale(None) == "units"


# ---------------------------------------------------------------------------
# extract_metadata
# ---------------------------------------------------------------------------

class TestExtractMetadata:
    def _make_cover_fields(self, **overrides):
        """Build a standard set of cover fields with optional overrides."""
        defaults = {
            "Filing Type": "10-Q",
            "Company": "Acme Corp",
            "Ticker": "ACME",
            "CIK": "0001234567",
            "Period": "June 30, 2024",
        }
        defaults.update(overrides)
        return [(k, v) for k, v in defaults.items()]

    def test_basic_extraction(self):
        fields = self._make_cover_fields()
        meta = extract_metadata(fields, "(in thousands)", "acme-10q.pdf")

        assert meta["company"] == "Acme Corp"
        assert meta["ticker"] == "ACME"
        assert meta["cik"] == "0001234567"
        assert meta["filing_type"] == "10-Q"
        assert meta["period_end"] == "2024-06-30"
        assert meta["period_type"] == "Q2"
        assert meta["fiscal_year"] == 2024
        assert meta["scale"] == "thousands"
        assert meta["currency"] == "USD"
        assert meta["audited"] is False
        assert meta["source_pdf"] == "acme-10q.pdf"
        assert "parsed_at" in meta

    def test_10k_audited_flag(self):
        fields = self._make_cover_fields(**{"Filing Type": "10-K", "Period": "December 31, 2024"})
        meta = extract_metadata(fields, "", "acme-10k.pdf")
        assert meta["audited"] is True
        assert meta["period_type"] == "FY"

    def test_missing_fields_graceful(self):
        """Metadata extraction should not crash with minimal fields."""
        fields = [("Filing Type", "10-Q")]
        meta = extract_metadata(fields, None, "unknown.pdf")

        assert meta["filing_type"] == "10-Q"
        assert meta["company"] == ""
        assert meta["ticker"] == ""
        assert meta["cik"] == ""
        assert meta["period_end"] == ""
        assert meta["source_pdf"] == "unknown.pdf"

    def test_empty_fields_list(self):
        meta = extract_metadata([], None, "empty.pdf")
        assert meta["company"] == ""
        assert meta["filing_type"] == ""

    def test_period_end_iso_format(self):
        fields = self._make_cover_fields(Period="March 31, 2025")
        meta = extract_metadata(fields, "", "test.pdf")
        assert meta["period_end"] == "2025-03-31"

    def test_fiscal_year_from_period(self):
        fields = self._make_cover_fields(Period="September 30, 2023")
        meta = extract_metadata(fields, "", "test.pdf")
        assert meta["fiscal_year"] == 2023


# ---------------------------------------------------------------------------
# metadata_to_yaml
# ---------------------------------------------------------------------------

class TestMetadataToYaml:
    def test_yaml_delimiters(self):
        meta = {"company": "Acme", "ticker": "ACME"}
        result = metadata_to_yaml(meta)
        assert result.startswith("---\n")
        assert result.rstrip().endswith("---")

    def test_contains_key_value_pairs(self):
        meta = {"company": "Acme Corp", "scale": "thousands"}
        result = metadata_to_yaml(meta)
        assert "company: Acme Corp" in result
        assert "scale: thousands" in result

    def test_special_chars_quoted(self):
        meta = {"company": "Acme: The Company"}
        result = metadata_to_yaml(meta)
        # Value containing colon should be quoted
        assert '"Acme: The Company"' in result or "'Acme: The Company'" in result

    def test_boolean_values(self):
        meta = {"audited": True}
        result = metadata_to_yaml(meta)
        assert "audited: true" in result

    def test_integer_values(self):
        meta = {"fiscal_year": 2024}
        result = metadata_to_yaml(meta)
        assert "fiscal_year: 2024" in result
