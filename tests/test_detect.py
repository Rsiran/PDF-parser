"""Tests for report type auto-detection."""

from sec_parser.pdf_extract import extract_pdf
from sec_parser.detect import detect_report_type


def test_detect_ifrs_quarterly(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    assert detect_report_type(pages) == "ifrs"


def test_detect_ifrs_annual(cadeler_ar24):
    pages = extract_pdf(cadeler_ar24)
    assert detect_report_type(pages) == "ifrs"
