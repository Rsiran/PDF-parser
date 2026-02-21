"""Integration tests for IFRS pipeline."""

import pytest
from pathlib import Path

from sec_parser.pipeline import process_pdf


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


def test_quarterly_produces_markdown(cadeler_1q25, output_dir):
    result = process_pdf(cadeler_1q25, output_dir, verbose=True)
    assert result.output_path.exists()
    content = result.output_path.read_text()
    assert "## Consolidated Statement of Profit or Loss" in content
    assert "## Consolidated Balance Sheet" in content
    assert "## Consolidated Statement of Cash Flows" in content


def test_quarterly_has_financial_data(cadeler_1q25, output_dir):
    result = process_pdf(cadeler_1q25, output_dir)
    content = result.output_path.read_text()
    # Should contain actual financial figures
    assert "Revenue" in content
    # Should have markdown table syntax
    assert "|" in content


def test_annual_produces_markdown(cadeler_ar24, output_dir):
    result = process_pdf(cadeler_ar24, output_dir, verbose=True)
    assert result.output_path.exists()
    content = result.output_path.read_text()
    assert "## Consolidated Statement of Profit or Loss" in content
    assert "## Consolidated Balance Sheet" in content
    assert "## Consolidated Statement of Cash Flows" in content
    assert "## Consolidated Statement of Changes in Equity" in content
