# SEC-Parse Audit Report — 2026-02-24

## Executive Summary

**6 PDFs tested, 5 succeeded, 1 crashed (XOM)**

| Filing | Type | Pages | CRITICAL | HIGH | MEDIUM | LOW | Status |
|--------|------|-------|----------|------|--------|-----|--------|
| AAPL | 10-K | 80 | 1 | 3 | 4 | 3 | Parsed |
| IREN25 | 10-K | 416 | 1 | 3 | 4 | 4 | Parsed |
| IRENQ1 | 10-Q | 69 | 1 | 4 | — | — | Parsed |
| IRENQ2 | 10-Q | 309 | 1 | 3 | 5 | 6 | Parsed |
| JPM | 10-K | 372 | 3 | 8 | 9 | 5 | Parsed |
| XOM | 10-K | 153 | 1 | — | — | — | **CRASHED** |

**Totals: 8 CRITICAL, 21 HIGH, 22 MEDIUM, 18 LOW**

### What works well
- **Financial numbers are accurate** when tables parse correctly (AAPL BS/IS/CF/Equity, all IREN filings)
- **Notes extraction via Gemini** is comprehensive and well-formatted
- **Prose sections** (MDA, Risk Factors, Legal) are substantially complete
- **Section detection** finds all major sections reliably
- **Cover page metadata** is mostly correct (company, ticker, filing_type, period_end, scale, currency)

---

## Systemic Issues (Recurring Across Multiple Filings)

### S1. Note Reference Columns Parsed as Data — CRITICAL/HIGH
**Affected:** IREN25, IRENQ2 (likely IRENQ1 too)
**Root cause:** When PDFs include a "Note" column (e.g., note refs 3, 4, 9, 12), pdfplumber extracts it as a data column. `collapse_row()` / `tables_to_markdown()` does not detect or strip note-reference columns, creating a phantom extra column that shifts all year-column data right.
**Impact:** Column headers become misaligned ("June 30," with no years), and downstream consumers cannot determine which column maps to which period.
**Fix location:** `programmatic.py` — add note-reference column detection/stripping in `tables_to_markdown()` or `collapse_row()`.

### S2. Column Headers Missing Year Labels — HIGH
**Affected:** IREN25 (IS, CF financing), IRENQ2 (IS, BS, Equity), JPM (all statements)
**Root cause:** Multi-line headers in PDFs (e.g., "Year Ended / June 30, / 2025") get partially collapsed. The year values on a second header row are lost or merged into the wrong column.
**Impact:** Tables show ambiguous headers like "2025 | 2025" or "June 30, |  |  |" — consumers cannot identify columns.
**Fix location:** `programmatic.py` — improve multi-line header merging in `tables_to_markdown()`.

### S3. Wide Tables with Word-Wrapped Line Items — HIGH
**Affected:** JPM (all statements), partially IREN25
**Root cause:** pdfplumber extracts wide PDF tables into many narrow columns, splitting line item text across multiple cells (e.g., "Cash and due from | banks"). The `collapse_row()` function handles some cases but fails on heavily fragmented tables (JPM has 11+ columns).
**Impact:** Line items are unreadable, values land in wrong columns, parenthetical negatives get truncated (missing closing parens).
**Fix location:** `programmatic.py:collapse_row()` — needs better handling of heavily fragmented wide tables.

### S4. Page Header/Footer Artifacts in Prose and Notes — MEDIUM
**Affected:** AAPL (14 footer instances in Risk Factors), IREN25 (F-8 through F-55 in Notes), IRENQ2 (page numbers in Notes), JPM (footers in Notes)
**Root cause:** `clean_prose()` strips some patterns but misses filing-specific footers like "Apple Inc. | 2025 Form 10-K | 30" and running headers like "IREN Limited / Notes to the condensed consolidated..."
**Impact:** Noise in prose output; not data-corrupting but degrades quality.
**Fix location:** `programmatic.py:clean_prose()` — add more generic page-header/footer stripping patterns.

### S5. Section Sub-Headers Mapped to Wrong Canonical Names — LOW
**Affected:** IREN25, IRENQ2
**Root cause:** Section sub-headers like "Non-current assets", "Current liabilities" are short text that fuzzy-matches against canonical names like "Total Non-Current Assets" or "Other Current Liabilities" (score ≥ 0.85). These are headers, not data rows.
**Impact:** Duplicate/incorrect canonical mappings; misleading but not data-corrupting since the actual total rows also get mapped correctly.
**Fix location:** `normalize.py` — skip normalization for rows with no numeric values (pure header rows).

### S6. Missing CIK in YAML Front-Matter — MEDIUM
**Affected:** All filings (AAPL, IREN25, IRENQ1, IRENQ2, JPM)
**Root cause:** CIK is not printed on most cover pages. The parser only extracts it from cover page text. Without CIK, XBRL cross-validation is disabled.
**Impact:** All filings fall back to PDF-only extraction, losing XBRL validation benefits.
**Note:** This is partially by design — the `--no-xbrl` flag was used. But even without the flag, CIK extraction from the PDF cover page would fail for most filings.

### S7. Comprehensive Income Not Always Parsed as Table — CRITICAL/MEDIUM
**Affected:** AAPL (raw text instead of table), JPM (garbled duplicate), IREN25 (merged into IS — defensible)
**Root cause:** When the comprehensive income statement is a small table (2-3 rows) or combined with the income statement, the table extraction fails or produces raw text.
**Impact:** AAPL comprehensive income is completely unparseable. JPM has garbled values.
**Fix location:** `programmatic.py:tables_to_markdown()` — ensure small financial tables are still recognized.

---

## Per-Filing Details

### AAPL (Apple 10-K, FY2025)
| # | Issue | Severity | Section |
|---|-------|----------|---------|
| 1 | Comprehensive Income rendered as raw text, not a table | CRITICAL | Comprehensive Income |
| 2 | MDA tables rendered as inline concatenated text | HIGH | MDA |
| 3 | MDA tables duplicated as garbled markdown tables | HIGH | MDA |
| 4 | Content duplication — Risk Factors/Legal appear twice | HIGH | Multiple |
| 5 | Missing CIK (0000320193) | MEDIUM | Metadata |
| 6 | Products gross margin % row empty in MDA table | MEDIUM | MDA |
| 7 | Interest rate sensitivity table garbled | MEDIUM | Market Risk |
| 8 | Page footer artifacts (14 instances) | MEDIUM | Risk Factors |
| 9 | Financial statement index duplicated 3x | LOW | Multiple |
| 10 | Orphaned share repurchase table fragment | LOW | Part II |
| 11 | Business section (Item 1) not extracted (by design) | LOW | Business |

**Correctly parsed:** Balance Sheet, Income Statement, Cash Flow, Stockholders' Equity, Notes — all numbers verified correct.

### IREN25 (IREN Limited 10-K, FY2025)
| # | Issue | Severity | Section |
|---|-------|----------|---------|
| 1 | Cash flow financing columns truncated across page break | CRITICAL | Cash Flow |
| 2 | Note reference column parsed as data column | HIGH | Income Statement |
| 3 | Missing year column headers | HIGH | Income Statement |
| 4 | Prose rendered as garbled table (Bitcoin Mining Revenue) | HIGH | Market Risk |
| 5 | Address has "Australi a" split | MEDIUM | Metadata |
| 6 | Financing section missing year headers | MEDIUM | Cash Flow |
| 7 | Page header/footer artifacts in Notes (F-8 through F-55) | MEDIUM | Notes |
| 8 | Business section (Item 1) not detected | MEDIUM | Business |
| 9-12 | Sub-headers mapped to wrong canonicals; comp income merged | LOW | Various |

### IRENQ1 (IREN Limited 10-Q, Q1)
| # | Issue | Severity | Section |
|---|-------|----------|---------|
| 1 | SOX Section 302 certifications completely garbled (character-interleaved) | CRITICAL | Exhibits |
| 2 | EBITDA reconciliation table missing from MDA | HIGH | MDA |
| 3 | Net electricity cost table missing from MDA | HIGH | MDA |
| 4 | Results of operations comparison table missing from MDA | HIGH | MDA |
| 5 | Stockholders' equity lacks sub-column headers | HIGH | Equity |

**All financial numbers verified correct.** Balance sheet equation passes.

### IRENQ2 (IREN Limited 10-Q, Q2)
| # | Issue | Severity | Section |
|---|-------|----------|---------|
| 1 | Income statement column headers malformed (4 periods unlabeled) | CRITICAL | Income Statement |
| 2 | Note references parsed as data column | HIGH | Income Statement |
| 3 | Balance sheet shows "2025 \| 2025" (can't distinguish periods) | HIGH | Balance Sheet |
| 4 | Stockholders' equity column headers missing | HIGH | Equity |
| 5 | Cash flow duplicate header rows | MEDIUM | Cash Flow |
| 6-7 | Page number & running header artifacts in Notes | MEDIUM | Notes |
| 8 | Section header misidentified | MEDIUM | Income Statement |
| 9 | Sub-header mapped to wrong canonical | MEDIUM | Balance Sheet |
| 10-15 | Minor formatting, missing signatory, exhibits as flat list | LOW | Various |

### JPM (JPMorgan Chase 10-K, Combined Annual Report)
| # | Issue | Severity | Section |
|---|-------|----------|---------|
| 1 | VIE footnote sub-table merged into main balance sheet | CRITICAL | Balance Sheet |
| 2 | Cash flow values misaligned across columns | CRITICAL | Cash Flow |
| 3 | BS validation reads VIE totals instead of main BS | CRITICAL | Validation |
| 4 | Balance sheet truncated closing parentheses | HIGH | Balance Sheet |
| 5 | Balance sheet 11-column word-wrapped layout | HIGH | Balance Sheet |
| 6 | Income statement garbled/duplicate header rows | HIGH | Income Statement |
| 7 | Income statement missing values from word wrapping | HIGH | Income Statement |
| 8 | "Noninterest expense" mapped to "Interest Expense" | HIGH | Normalization |
| 9 | Cash flow missing net cash totals | HIGH | Cash Flow |
| 10 | Notes raw text with merged two-column artifacts (Gemini 503) | HIGH | Notes |
| 11 | Cash flow validation failures | HIGH | Validation |
| 12-18 | Missing CIK, controls not detected, comp income garbled, MDA pre-material | MEDIUM | Various |
| 19-25 | Company name formatting, exhibits/signatures missing (by design), footers | LOW | Various |

**JPM is the hardest filing** — a 372-page combined annual report with wide multi-column tables that overwhelm the current table collapse logic.

### XOM (ExxonMobil 10-K) — CRASHED
| # | Issue | Severity | Section |
|---|-------|----------|---------|
| 1 | `UnboundLocalError: cannot access local variable 'results'` | CRITICAL | pipeline.py:473 |

**Root cause:** `results` is assigned inside `if statements:` (line 446) but referenced outside that block at line 473 in the confidence scoring loop. When `statements` is empty, `results` is never defined.
**Fix:** Initialize `results = []` before the `if statements:` block (~line 444).

---

## Fix Plan

### Phase 1: Crash Fix (Effort: Trivial, Issues Fixed: 1, Filings Improved: 1)
| File | Change | Issues |
|------|--------|--------|
| `pipeline.py:~444` | Initialize `results = []` before `if statements:` block | XOM crash |

### Phase 2: Note Reference Column Stripping (Effort: Medium, Issues Fixed: 6, Filings Improved: 3)
| File | Change | Issues |
|------|--------|--------|
| `programmatic.py` | Detect and strip note-reference columns in `tables_to_markdown()`. A note-ref column is one where most cells contain single-digit integers (1-30) or are empty, positioned between the line-item column and the first data column. | IREN25 IS note refs, IRENQ2 IS note refs, column header misalignment across IREN filings |

### Phase 3: Multi-Line Header Merging (Effort: Medium, Issues Fixed: 8, Filings Improved: 4)
| File | Change | Issues |
|------|--------|--------|
| `programmatic.py` | Improve header row detection in `tables_to_markdown()` — merge multi-line headers (e.g., "December 31," + "2025 \| 2024") into single header rows. Detect when a second row has year values that complement the first header row. | Missing year labels across IREN25, IRENQ2, JPM, AAPL comp income |

### Phase 4: Page Header/Footer Cleanup (Effort: Low, Issues Fixed: 5, Filings Improved: 4)
| File | Change | Issues |
|------|--------|--------|
| `programmatic.py:clean_prose()` | Add generic patterns: lines matching `^Company .* Form 10-[KQ] .* \d+$`, standalone page numbers (F-\d+), repeated document title lines in Notes sections | AAPL footers, IREN25 F-page headers, IRENQ2 page numbers, JPM footers |

### Phase 5: Wide Table Collapse Improvements (Effort: High, Issues Fixed: 10+, Filings Improved: 1-2)
| File | Change | Issues |
|------|--------|--------|
| `programmatic.py:collapse_row()` | Better handling of heavily fragmented tables (11+ columns) where line-item text is split across 3+ cells. Detect and merge text-only prefix cells before the first numeric cell. Ensure closing parentheses are preserved when negative values span multiple cells. | JPM all statements, truncated parens |

### Phase 6: Sub-Table Separation (Effort: Medium, Issues Fixed: 3, Filings Improved: 1)
| File | Change | Issues |
|------|--------|--------|
| `programmatic.py` | Detect footnote sub-tables (rows after a "Total assets/liabilities" row that restart with a new header like "Assets") and either separate them or exclude them from the main table. | JPM VIE sub-table merged into BS, validation failure |

### Phase 7: Canonical Mapping Guards (Effort: Low, Issues Fixed: 4, Filings Improved: 2)
| File | Change | Issues |
|------|--------|--------|
| `normalize.py` | Skip normalization for rows where all value cells are empty (pure section headers). Also fix "Noninterest expense" → "Interest Expense" mis-mapping. | Sub-header mis-mappings, JPM normalization error |

### Summary

| Phase | Effort | Issues Fixed | Filings Improved |
|-------|--------|-------------|-----------------|
| 1. Crash fix | Trivial | 1 | XOM |
| 2. Note ref stripping | Medium | 6 | IREN25, IRENQ1, IRENQ2 |
| 3. Header merging | Medium | 8 | IREN25, IRENQ2, JPM, AAPL |
| 4. Footer cleanup | Low | 5 | AAPL, IREN25, IRENQ2, JPM |
| 5. Wide table collapse | High | 10+ | JPM (+ future wide-format filings) |
| 6. Sub-table separation | Medium | 3 | JPM |
| 7. Canonical guards | Low | 4 | IREN25, IRENQ2, JPM |
