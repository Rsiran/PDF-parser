"""Tests for multi-filing consistency."""

import pytest
from sec_parser.consistency import enforce_consistent_mappings


class TestEnforceConsistentMappings:
    def test_forces_same_mapping(self):
        filing_mappings = [
            {"Net revenues": "Revenue", "Cost of sales": "Cost of Revenue"},
            {"Net revenues": "", "Cost of sales": "Cost of Revenue"},
        ]
        result = enforce_consistent_mappings(filing_mappings)
        assert result[1]["Net revenues"] == "Revenue"

    def test_no_conflict(self):
        filing_mappings = [
            {"Net revenues": "Revenue"},
            {"Total revenues": "Revenue"},
        ]
        result = enforce_consistent_mappings(filing_mappings)
        assert result[0]["Net revenues"] == "Revenue"
        assert result[1]["Total revenues"] == "Revenue"

    def test_empty_input(self):
        assert enforce_consistent_mappings([]) == []

    def test_single_filing(self):
        result = enforce_consistent_mappings([{"Revenue": "Revenue"}])
        assert result == [{"Revenue": "Revenue"}]
