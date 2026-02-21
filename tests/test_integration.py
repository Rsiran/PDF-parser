"""Integration tests for the enhanced pipeline."""

import pytest
from sec_parser.markdown_writer import assemble_markdown
from sec_parser.metadata import extract_metadata, metadata_to_yaml
from sec_parser.normalize import load_taxonomy, normalize_table_rows
from sec_parser.validate import extract_statement_data, run_all_checks, render_validation_markdown


class TestPipelineIntegration:
    def test_front_matter_in_output(self):
        """Front-matter appears at top of assembled markdown."""
        metadata = extract_metadata(
            cover_fields=[("Filing Type", "10-Q"), ("Company", "Test Corp"), ("Period", "June 30, 2025")],
            scale_hint="(in thousands)",
            source_pdf="test.pdf",
        )
        result = assemble_markdown("test.pdf", {}, metadata=metadata)
        assert result.startswith("---\n")
        assert "company: Test Corp" in result
        assert "period_type: Q2" in result
        assert "scale: thousands" in result

    def test_canonical_column_in_table(self):
        """Normalization adds Canonical column to tables."""
        taxonomy = load_taxonomy()
        rows = [
            ["Net revenues", "1,000", "900"],
            ["Cost of sales", "600", "500"],
            ["Net income", "100", "80"],
        ]
        normalized = normalize_table_rows(rows, taxonomy)
        assert normalized[0][1] == "Revenue"
        assert normalized[1][1] == "Cost of Revenue"
        assert normalized[2][1] == "Net Income"

    def test_validation_in_output(self):
        """Validation section appears in assembled markdown."""
        statements = {
            "balance_sheet": {"Total Assets": [5000.0], "Total Liabilities": [3000.0], "Total Stockholders' Equity": [2000.0]},
        }
        results = run_all_checks(statements)
        validation_md = render_validation_markdown(results)
        output = assemble_markdown("test.pdf", {}, validation_markdown=validation_md)
        assert "## Validation" in output
        assert "PASS" in output

    def test_end_to_end_data_flow(self):
        """Full data flow: normalize rows -> extract data -> validate."""
        taxonomy = load_taxonomy()
        rows = [
            ["Total assets", "5,000", "4,500"],
            ["Total liabilities", "3,000", "2,700"],
            ["Total stockholders' equity", "2,000", "1,800"],
        ]
        normalized = normalize_table_rows(rows, taxonomy)
        data = extract_statement_data(normalized)
        assert "Total Assets" in data
        assert data["Total Assets"] == [5000.0, 4500.0]

        statements = {"balance_sheet": data}
        results = run_all_checks(statements)
        bs_checks = [r for r in results if "Balance sheet" in r.check or "BS" in r.check]
        assert bs_checks[0].status == "PASS"

    def test_metadata_yaml_round_trip(self):
        """Metadata dict renders to valid YAML front-matter."""
        metadata = extract_metadata(
            cover_fields=[("Filing Type", "10-K"), ("Company", "Acme Corp"), ("Period", "December 31, 2024")],
            scale_hint="(in millions)",
            source_pdf="acme.pdf",
        )
        yaml_str = metadata_to_yaml(metadata)
        assert yaml_str.startswith("---")
        assert yaml_str.endswith("---\n")
        assert "audited: true" in yaml_str
        assert "period_type: FY" in yaml_str
