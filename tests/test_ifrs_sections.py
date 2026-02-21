"""Tests for IFRS section splitting."""

from sec_parser.pdf_extract import extract_pdf
from sec_parser.ifrs_section_split import (
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_NOTES,
    split_ifrs_sections,
)


def test_quarterly_finds_all_sections(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)

    # Quarterly report should have all financial statement sections
    assert IFRS_INCOME_STATEMENT in sections
    assert IFRS_BALANCE_SHEET in sections
    assert IFRS_CASH_FLOW in sections
    assert IFRS_EQUITY_CHANGES in sections


def test_annual_finds_all_sections(cadeler_ar24):
    pages = extract_pdf(cadeler_ar24)
    sections = split_ifrs_sections(pages)

    assert IFRS_INCOME_STATEMENT in sections
    assert IFRS_BALANCE_SHEET in sections
    assert IFRS_CASH_FLOW in sections
    assert IFRS_EQUITY_CHANGES in sections
    assert IFRS_NOTES in sections


def test_income_statement_has_revenue(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)
    text = sections[IFRS_INCOME_STATEMENT].text
    assert "Revenue" in text or "revenue" in text


def test_balance_sheet_has_assets(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)
    text = sections[IFRS_BALANCE_SHEET].text
    assert "Total" in text and "assets" in text.lower()


def test_sections_have_tables(cadeler_1q25):
    pages = extract_pdf(cadeler_1q25)
    sections = split_ifrs_sections(pages)

    # Financial statements should have extracted tables
    for key in [IFRS_INCOME_STATEMENT, IFRS_BALANCE_SHEET, IFRS_CASH_FLOW]:
        assert sections[key].tables, f"{key} should have tables"


def test_ignores_parent_company_financials(cadeler_ar24):
    """Should pick consolidated statements, not parent company."""
    pages = extract_pdf(cadeler_ar24)
    sections = split_ifrs_sections(pages)

    # Income statement should be the consolidated one (page ~143),
    # not the parent company one (page ~226)
    assert sections[IFRS_INCOME_STATEMENT].start_page < 200
