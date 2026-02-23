# Round 4 Fix Plan

## Priority Order (dependency-aware)

### Phase 1: Prose-vs-Table Discrimination
- [x] US-001: Detect and reject false prose tables (heuristic in programmatic.py to identify >6-col tables with word-fragment cells, discard or convert to prose)

### Phase 2: Column Header Restoration
- [x] US-002: Preserve first-row column headers in financial tables (only strip date rows AFTER first data row, not the header row)

### Phase 3: JPM Combined Report Fixes
- [x] US-003: Fix JPM cover page metadata extraction (add NYSE/NASDAQ fallback pattern for company/ticker)
- [x] US-004: Fix JPM financial statement section boundaries (prefer pages with numeric tabular data over MDA discussion pages)
- [x] US-005: Fix JPM Notes section boundary (extend end boundary to cover full 150-page notes range)

### Phase 4: Address Parsing
- [x] US-006: Filter cover page label fragments from address field (strip "incorporation or organization", "Identification Number", etc.)

### Phase 5: Missing Section Detection
- [x] US-007: Detect AAPL Risk Factors section (fixed by US-004 heading match improvements)

### Phase 6: Page Artifact Cleanup
- [x] US-008: Strip page number artifacts from notes and prose (F-xx, standalone numbers, running headers)

### Phase 7: Stretch
- [ ] US-009: Fix XOM financial statements to render as markdown tables (investigate text-mode extraction path)
- [ ] US-010: Investigate IREN25 cash flow FY2023 column truncation (try alternative pdfplumber settings)
- [ ] US-011: Handle two-column exhibit layout garbling (detect and mark or extract sequentially)
- [ ] US-012: Fix section header canonical mismatches (skip canonical mapping for lines ending with ":")
- [ ] US-013: Fix Gemini notes extraction error for AAPL (handle None in str.join)
- [ ] US-014: Fix XOM share repurchase table missing data rows
- [ ] US-015: Fix XOM MDA section boundary

## Verification
After each fix, run:
1. `pytest` — all tests must pass
2. `PYTHONPATH=. python -m sec_parser.cli test-pdfs/ -o output/ --verbose` — all 6 PDFs must process
3. Spot-check the affected filing's output for the specific fix
