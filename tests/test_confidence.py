"""Tests for sec_parser.confidence — cross-validation and confidence scoring."""

from __future__ import annotations

from sec_parser.confidence import (
    Discrepancy,
    ExtractionConfidence,
    compute_confidence,
    cross_validate,
    render_confidence_markdown,
)


class TestCrossValidate:
    def test_matching_values(self):
        """Identical values should produce info-severity discrepancies with 0% diff."""
        xbrl = {"Revenue": [100.0], "Net Income": [25.0]}
        pdf = {"Revenue": [100.0], "Net Income": [25.0]}
        discs = cross_validate(xbrl, pdf)
        assert len(discs) == 2
        assert all(d.severity == "info" for d in discs)
        assert all(d.pct_difference == 0.0 for d in discs)

    def test_small_discrepancy_warn(self):
        """1-5% difference should be 'warn' severity."""
        xbrl = {"Revenue": [100.0]}
        pdf = {"Revenue": [97.0]}  # 3% off
        discs = cross_validate(xbrl, pdf)
        assert len(discs) == 1
        assert discs[0].severity == "warn"
        assert 0.02 < discs[0].pct_difference < 0.04

    def test_large_discrepancy_error(self):
        """Over 5% difference should be 'error' severity."""
        xbrl = {"Revenue": [100.0]}
        pdf = {"Revenue": [80.0]}  # 20% off
        discs = cross_validate(xbrl, pdf)
        assert len(discs) == 1
        assert discs[0].severity == "error"

    def test_within_tolerance_info(self):
        """Under 1% difference should be 'info' severity."""
        xbrl = {"Revenue": [100.0]}
        pdf = {"Revenue": [99.5]}  # 0.5% off
        discs = cross_validate(xbrl, pdf)
        assert len(discs) == 1
        assert discs[0].severity == "info"

    def test_no_overlap_returns_empty(self):
        """Non-overlapping keys should produce no discrepancies."""
        xbrl = {"Revenue": [100.0]}
        pdf = {"Net Income": [25.0]}
        discs = cross_validate(xbrl, pdf)
        assert len(discs) == 0

    def test_none_values_skipped(self):
        """None values in XBRL should be skipped."""
        xbrl = {"Revenue": [None]}
        pdf = {"Revenue": [100.0]}
        discs = cross_validate(xbrl, pdf)
        assert len(discs) == 0

    def test_zero_denominator(self):
        """Both zero should produce info with 0% diff."""
        xbrl = {"Revenue": [0.0]}
        pdf = {"Revenue": [0.0]}
        discs = cross_validate(xbrl, pdf)
        assert len(discs) == 1
        assert discs[0].severity == "info"

    def test_custom_tolerance(self):
        """Custom tolerance should affect severity thresholds."""
        xbrl = {"Revenue": [100.0]}
        pdf = {"Revenue": [96.0]}  # 4% off
        # With 5% tolerance, this should be info
        discs = cross_validate(xbrl, pdf, tolerance=0.05)
        assert discs[0].severity == "info"


class TestComputeConfidence:
    def test_xbrl_pdf_match(self):
        """XBRL + PDF with no discrepancies = 1.0"""
        result = compute_confidence(
            xbrl_data="some_xbrl",
            pdf_data={"Revenue": [100.0]},
            statement_type="income_statement",
            discrepancies=[],
        )
        assert result.confidence == 1.0
        assert result.source == "xbrl+pdf"

    def test_xbrl_pdf_with_warns(self):
        """XBRL + PDF with warnings = 0.95"""
        disc = Discrepancy("Revenue", 100.0, 97.0, 3.0, 0.03, "warn")
        result = compute_confidence(
            xbrl_data="some_xbrl",
            pdf_data={"Revenue": [97.0]},
            statement_type="income_statement",
            discrepancies=[disc],
        )
        assert result.confidence == 0.95

    def test_xbrl_pdf_with_errors(self):
        """XBRL + PDF with errors = 0.8"""
        disc = Discrepancy("Revenue", 100.0, 80.0, 20.0, 0.20, "error")
        result = compute_confidence(
            xbrl_data="some_xbrl",
            pdf_data={"Revenue": [80.0]},
            statement_type="income_statement",
            discrepancies=[disc],
        )
        assert result.confidence == 0.8

    def test_xbrl_only(self):
        """XBRL without PDF = 0.9"""
        result = compute_confidence(
            xbrl_data="some_xbrl",
            pdf_data=None,
            statement_type="income_statement",
        )
        assert result.confidence == 0.9
        assert result.source == "xbrl"

    def test_pdf_pass(self):
        """PDF only with validation pass = 0.7"""
        result = compute_confidence(
            xbrl_data=None,
            pdf_data={"Revenue": [100.0]},
            statement_type="income_statement",
            validation_status="PASS",
        )
        assert result.confidence == 0.7
        assert result.source == "pdf"

    def test_pdf_warn(self):
        """PDF only with validation warn = 0.5"""
        result = compute_confidence(
            xbrl_data=None,
            pdf_data={"Revenue": [100.0]},
            statement_type="income_statement",
            validation_status="WARN",
        )
        assert result.confidence == 0.5

    def test_pdf_fail(self):
        """PDF only with validation fail = 0.3"""
        result = compute_confidence(
            xbrl_data=None,
            pdf_data={"Revenue": [100.0]},
            statement_type="income_statement",
            validation_status="FAIL",
        )
        assert result.confidence == 0.3

    def test_neither_source(self):
        """No XBRL and no PDF = 0.0"""
        result = compute_confidence(
            xbrl_data=None,
            pdf_data=None,
            statement_type="income_statement",
        )
        assert result.confidence == 0.0
        assert result.source == "none"


class TestRenderConfidenceMarkdown:
    def test_empty_returns_empty(self):
        assert render_confidence_markdown([]) == ""

    def test_renders_summary_table(self):
        conf = ExtractionConfidence(
            statement_type="income_statement",
            source="xbrl+pdf",
            confidence=1.0,
            xbrl_available=True,
            pdf_available=True,
        )
        md = render_confidence_markdown([conf])
        assert "| income_statement |" in md
        assert "| xbrl+pdf |" in md
        assert "| 1.0 |" in md
        assert "None" in md

    def test_renders_discrepancy_details(self):
        disc = Discrepancy("Revenue", 100.0, 80.0, 20.0, 0.20, "error")
        conf = ExtractionConfidence(
            statement_type="income_statement",
            source="xbrl",
            confidence=0.8,
            xbrl_available=True,
            pdf_available=True,
            discrepancies=[disc],
        )
        md = render_confidence_markdown([conf])
        assert "Discrepancy Details" in md
        assert "| Revenue |" in md
        assert "ERROR" in md

    def test_multiple_statements(self):
        confs = [
            ExtractionConfidence("income_statement", "xbrl+pdf", 1.0, True, True),
            ExtractionConfidence("balance_sheet", "pdf", 0.7, False, True),
        ]
        md = render_confidence_markdown(confs)
        assert "income_statement" in md
        assert "balance_sheet" in md
