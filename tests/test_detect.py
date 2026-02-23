"""Tests for report type auto-detection and 10-K start page detection."""

from sec_parser.pdf_extract import PageData, extract_pdf
from sec_parser.detect import detect_10k_start_page, detect_report_type


def test_detect_ifrs_quarterly(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    assert detect_report_type(pages) == "ifrs"


def test_detect_ifrs_annual(cadeler_ar24):
    pages = extract_pdf(cadeler_ar24)
    assert detect_report_type(pages) == "ifrs"


# --- detect_10k_start_page tests ---


def test_10k_start_page_sec_cover_on_page1():
    """Standard 10-K with SEC cover on page 1 returns 1."""
    pages = [
        PageData(
            page_number=1,
            text=(
                "UNITED STATES\n"
                "SECURITIES AND EXCHANGE COMMISSION\n"
                "Washington, D.C. 20549\n"
                "FORM 10-K\n"
            ),
        ),
        PageData(page_number=2, text="Some other content"),
    ]
    assert detect_10k_start_page(pages) == 1


def test_10k_start_page_sec_cover_on_later_page():
    """Combined document with SEC cover page at page 50 returns 50."""
    pages = [
        PageData(page_number=1, text="Dear Fellow Shareholders,\nAnnual letter..."),
        PageData(page_number=2, text="More shareholder letter content..."),
        PageData(
            page_number=50,
            text=(
                "UNITED STATES SECURITIES AND EXCHANGE COMMISSION\n"
                "Washington, D.C. 20549\n"
                "FORM 10-K\n"
            ),
        ),
    ]
    assert detect_10k_start_page(pages) == 50


def test_10k_start_page_registrant_pattern():
    """Page with registrant pattern triggers detection."""
    pages = [
        PageData(page_number=1, text="Annual Report 2024"),
        PageData(
            page_number=30,
            text="Apple Inc.\n(Exact name of registrant as specified in its charter)\n",
        ),
    ]
    assert detect_10k_start_page(pages) == 30


def test_10k_start_page_footer_detection():
    """Combined document with Form 10-K footer pattern detects start."""
    pages = [
        PageData(page_number=1, text="Annual Report 2024\nDear shareholders..."),
        PageData(page_number=2, text="Performance highlights and charts..."),
        PageData(
            page_number=83,
            text=(
                "Table of contents\n"
                "50 Three-Year Summary\n"
                "52 Introduction\n"
                "54 Executive Overview\n"
                "59 Consolidated Results\n"
                "63 Balance Sheets\n"
                "JPMorgan Chase & Co./2024 Form 10-K 49\n"
            ),
        ),
    ]
    assert detect_10k_start_page(pages) == 83


def test_10k_start_page_no_markers():
    """Document with no SEC markers returns 1."""
    pages = [
        PageData(page_number=1, text="Some random PDF content"),
        PageData(page_number=2, text="More content here"),
    ]
    assert detect_10k_start_page(pages) == 1


def test_10k_start_page_toc_skipped():
    """TOC pages with FORM 10-K references are skipped."""
    pages = [
        PageData(
            page_number=1,
            text=(
                "TABLE OF CONTENTS\n"
                "FORM 10-K.............. 5\n"
                "Risk Factors........... 10\n"
                "Balance Sheet.......... 20\n"
            ),
        ),
        PageData(
            page_number=5,
            text=(
                "UNITED STATES SECURITIES AND EXCHANGE COMMISSION\n"
                "FORM 10-K\n"
            ),
        ),
    ]
    assert detect_10k_start_page(pages) == 5


def test_10k_start_page_footer_on_page1():
    """Form 10-K footer on page 1 means no prefix, returns 1."""
    pages = [
        PageData(
            page_number=1,
            text="Company Inc./2024 Form 10-K 1\nSome content",
        ),
        PageData(page_number=2, text="More content"),
    ]
    assert detect_10k_start_page(pages) == 1
