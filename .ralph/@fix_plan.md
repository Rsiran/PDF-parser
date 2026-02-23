# Round 5 Fix Plan

## Priority Order (dependency-aware)

### Phase 1: Prose-Table Discrimination (tighten thresholds)
- [x] US-001: Tighten _is_prose_table() thresholds — max_cols >= 6 (was > 6), numeric_ratio > 0.15 (was > 0.25)

### Phase 2: Section Boundary Fixes
- [ ] US-002: Cap Risk Factors at 25 pages to prevent duplication (add to _MAX_PAGES in section_split.py)

### Phase 3: Table Rendering
- [ ] US-003: Fix AAPL Comprehensive Income to render as markdown table (text-based fallback in pipeline.py/programmatic.py)

### Phase 4: Header Merging
- [ ] US-004: Merge double-header date rows (month-day + year) into single header rows in programmatic.py

### Phase 5: XOM Cash Flow Fixes
- [ ] US-005: Fix missing "Postretirement benefits expense" row (check orphaned-row filters in programmatic.py)
- [ ] US-006: Fix concatenated values in "Inflows from noncontrolling" row (split_single_col_row() in programmatic.py)

### Phase 6: Table Deduplication
- [ ] US-007: Deduplicate AAPL MDA tables — skip tables with >70% matching row labels vs previous table

## Verification
After each fix, run:
1. `pytest` — all tests must pass
2. `PYTHONPATH=. python -m sec_parser.cli test-pdfs/ -o output/ --verbose` — all 6 PDFs must process
3. Spot-check the affected filing's output for the specific fix
