# Round 3 Fix Plan

## Priority Order (dependency-aware)

### Phase 1: Taxonomy & Normalization
- [x] US-001: Add missing canonical entries to taxonomy.yaml (long_term_investments, other_current_liabilities, other_non_current_liabilities)
- [x] US-002: Fix canonical normalization for current vs non-current items (context-aware disambiguation in normalize.py/programmatic.py)

### Phase 2: Core Table & Section Fixes
- [x] US-003: Eliminate duplicate notes in raw-text fallback (suppress pdfplumber tables when raw-text already covers those pages)
- [ ] US-004: Fix stockholders' equity column alignment for sparse rows (pad collapsed rows to match dominant column count)
- [ ] US-005: Capture cash flow beginning balance row for AAPL
- [ ] US-006: Detect Comprehensive Income as separate section (add comprehensive_income to SECTION_PATTERNS)

### Phase 3: Table Cell & Header Cleanup
- [ ] US-007: Apply character collapse to table cell values in pdf_extract.py
- [ ] US-008: Remove leaked column header rows (date/period patterns) from financial tables

### Phase 4: Metadata Improvements
- [ ] US-009: Improve address parsing for multi-line cover pages

### Phase 5: JPM Combined Annual Report Support
- [ ] US-010: Add detect_10k_start_page() function to find where 10-K begins in combined documents
- [ ] US-011: Integrate 10-K start page into pipeline (section splitting, cover page, scale detection start from 10-K page)
- [ ] US-012: Verify JPM financial statements contain correct data after pipeline integration

### Phase 6: Stretch
- [ ] US-013: Reduce garbled rotated-text column headers (de-interleave heuristic, best effort)

## Verification
After each fix, run:
1. `pytest` — all tests must pass
2. `PYTHONPATH=. python -m sec_parser.cli test-pdfs/ -o output/ --verbose` — all 6 PDFs must process
3. Spot-check the affected filing's output for the specific fix
