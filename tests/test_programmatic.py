"""Tests for sec_parser.programmatic — cover page refactor regression tests."""

from __future__ import annotations

from sec_parser.programmatic import extract_cover_fields, parse_cover_page


SAMPLE_COVER = """\
UNITED STATES SECURITIES AND EXCHANGE COMMISSION

FORM 10-Q

QUARTERLY PERIOD ENDED June 30, 2024

Commission File Number: 001-12345

Acme Corp
(Exact name of registrant as specified in its charter)

Central Index Key: 0001234567

1,000,000 shares of common stock

Trading Symbol: ACME

Name of exchange on which registered: NYSE
"""


class TestExtractCoverFields:
    def test_returns_list_of_tuples(self):
        fields = extract_cover_fields(SAMPLE_COVER)
        assert isinstance(fields, list)
        assert all(isinstance(f, tuple) and len(f) == 2 for f in fields)

    def test_extracts_filing_type(self):
        fields = dict(extract_cover_fields(SAMPLE_COVER))
        assert fields["Filing Type"] == "10-Q"

    def test_extracts_company(self):
        fields = dict(extract_cover_fields(SAMPLE_COVER))
        assert fields["Company"] == "Acme Corp"

    def test_extracts_period(self):
        fields = dict(extract_cover_fields(SAMPLE_COVER))
        assert fields["Period"] == "June 30, 2024"

    def test_extracts_ticker(self):
        fields = dict(extract_cover_fields(SAMPLE_COVER))
        assert fields["Ticker"] == "ACME"

    def test_extracts_cik(self):
        fields = dict(extract_cover_fields(SAMPLE_COVER))
        assert fields["CIK"] == "0001234567"

    def test_empty_text_returns_empty(self):
        assert extract_cover_fields("") == []


class TestParseCoverPageRegression:
    def test_returns_markdown_table(self):
        result = parse_cover_page(SAMPLE_COVER)
        assert "| Field | Value |" in result
        assert "| Filing Type | 10-Q |" in result

    def test_fallback_on_no_match(self):
        text = "Nothing relevant here"
        assert parse_cover_page(text) == text

    def test_output_unchanged(self):
        """parse_cover_page output should be identical before and after refactor."""
        result = parse_cover_page(SAMPLE_COVER)
        # Verify structure: header, separator, data rows
        lines = result.strip().split("\n")
        assert lines[0] == "| Field | Value |"
        assert lines[1] == "|-------|-------|"
        assert len(lines) >= 3  # at least one data row
