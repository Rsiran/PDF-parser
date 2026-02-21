"""Tests for sec_parser.normalize module."""

import pytest

from sec_parser.normalize import (
    NormResult,
    load_taxonomy,
    _build_alias_index,
    match_line_item,
    normalize_table_rows,
    collect_unmapped,
)


@pytest.fixture
def taxonomy():
    return load_taxonomy()


# --- load_taxonomy ---

def test_load_taxonomy_has_three_sections(taxonomy):
    assert "income_statement" in taxonomy
    assert "balance_sheet" in taxonomy
    assert "cash_flow" in taxonomy


def test_load_taxonomy_revenue_entry(taxonomy):
    rev = taxonomy["income_statement"]["revenue"]
    assert rev["canonical"] == "Revenue"
    assert "Net revenues" in rev["aliases"]
    assert "Net sales" in rev["aliases"]


# --- match_line_item ---

def test_exact_match(taxonomy):
    result = match_line_item("Net revenues", taxonomy)
    assert result.canonical == "Revenue"
    assert result.confidence == 1.0
    assert result.method == "exact"


def test_exact_match_case_insensitive(taxonomy):
    result = match_line_item("NET REVENUES", taxonomy)
    assert result.canonical == "Revenue"
    assert result.confidence == 1.0
    assert result.method == "exact"


def test_fuzzy_match(taxonomy):
    result = match_line_item("Revenues, net", taxonomy)
    assert result.method == "fuzzy"
    assert result.canonical == "Revenue"
    assert result.confidence >= 0.85


def test_no_match(taxonomy):
    result = match_line_item("Goodwill impairment charge adjustment", taxonomy)
    assert result.canonical is None
    assert result.method == "none"


def test_empty_label(taxonomy):
    result = match_line_item("", taxonomy)
    assert result.canonical is None
    assert result.confidence == 0.0
    assert result.method == "none"


def test_balance_sheet_item(taxonomy):
    result = match_line_item("Total current assets", taxonomy)
    assert result.canonical == "Total Current Assets"
    assert result.confidence == 1.0
    assert result.method == "exact"


def test_cash_flow_item(taxonomy):
    result = match_line_item("Net cash provided by operating activities", taxonomy)
    assert result.canonical == "Net Cash from Operations"
    assert result.confidence == 1.0
    assert result.method == "exact"


# --- normalize_table_rows ---

def test_normalize_table_rows_adds_canonical(taxonomy):
    rows = [
        ["Net revenues", "100", "200"],
        ["Cost of sales", "50", "80"],
    ]
    result = normalize_table_rows(rows, taxonomy)
    assert len(result) == 2
    assert result[0] == ["Net revenues", "Revenue", "100", "200"]
    assert result[1] == ["Cost of sales", "Cost of Revenue", "50", "80"]


def test_normalize_table_rows_unmapped(taxonomy):
    rows = [["Goodwill impairment charge adjustment", "10", "20"]]
    result = normalize_table_rows(rows, taxonomy)
    assert result[0][1] == ""


def test_normalize_table_rows_numeric_first_cell(taxonomy):
    rows = [["1,234", "10", "20"]]
    result = normalize_table_rows(rows, taxonomy)
    assert result[0][1] == ""


def test_normalize_table_rows_empty_first_cell(taxonomy):
    rows = [["", "10", "20"]]
    result = normalize_table_rows(rows, taxonomy)
    assert result[0][1] == ""


# --- collect_unmapped ---

def test_collect_unmapped(taxonomy):
    rows = [
        ["Net revenues", "Revenue", "100"],
        ["Goodwill impairment charge adjustment", "", "10"],
        ["", "", "5"],
        ["Some unknown item", "", "20"],
    ]
    unmapped = collect_unmapped(rows, taxonomy)
    assert "Goodwill impairment charge adjustment" in unmapped
    assert "Some unknown item" in unmapped
    assert len(unmapped) == 2
