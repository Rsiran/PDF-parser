# PDF Parser Analysis Report — 5 Test Filings

**Date:** 2026-02-21
**PDFs tested:** Cola24, Googl25, Nebiud24, Nvda25, Open25

---

## Executive Summary

| Filing | Pages | Sections Found | Financial Tables | Metadata | Verdict |
|--------|-------|---------------|-----------------|----------|---------|
| Cola24 (Coca-Cola) | 31 | 4 of ~8 | Partial — cash flow garbled | Mostly empty | POOR |
| Googl25 (Alphabet) | 99 | 0 of ~12 | None | All empty | FAILED |
| Nebiud24 (Nebius) | 11 | 4 of 4 available | Raw text only (no pdfplumber tables) | Mostly empty | POOR |
| Nvda25 (NVIDIA) | 181 | 11 of 13 | Present but columns collapsed | Mostly correct | FAIR |
| Open25 (Opendoor) | 279 | 2 of ~12 | None | Partial | FAILED |

**Overall: 2 complete failures, 2 poor, 1 fair. Zero filings produce fully correct output.**

---

## Issue 1: TOC Header Kills All Section Detection (CRITICAL — 2 filings)

**Affected:** Googl25, Open25

**Root cause:** `_is_toc_page()` in `section_split.py:142-144` uses a simple substring match:
```python
_TOC_PATTERN = re.compile(r"TABLE\s+OF\s+CONTENTS", re.IGNORECASE)
```
Many SEC filings include a running header "Table of Contents" on **every page**. Both Googl25 (96/99 pages) and Open25 (all 279 pages) have this header. Since every page is flagged as TOC and skipped, zero sections are detected.

**Impact:** Complete parsing failure. These filings produce empty output (577 bytes for Google's 99-page 10-K).

**Evidence:** All section heading patterns (balance sheet, income statement, etc.) do match correctly in both filings when the TOC filter is bypassed.

**Fix needed:** Change `_is_toc_page()` to require "TABLE OF CONTENTS" on a standalone heading line (not a running header), or to verify the page also contains multiple page-number references typical of an actual TOC page. The existing secondary heuristic (≥4 pattern matches) is fine.

---

## Issue 2: Multi-Year Table Columns Collapse Into Single Cell (CRITICAL — all filings with tables)

**Affected:** Nvda25, Cola24, Nebiud24 (when tables are detected)

**Root cause:** `collapse_row()` in `programmatic.py` merges all cells into a single text string. Financial statements typically have 2-3 year columns (e.g., FY2025, FY2024, FY2023), but the output renders all values in one cell:

```
| Revenue $ 130,497 $ 60,922 $ 26,974 |  |
```

Instead of:
```
| Revenue | $130,497 | $60,922 | $26,974 |
```

**Impact:** Output tables are not machine-parseable. Multi-period financial data cannot be extracted from the markdown.

**Additional symptom:** A spurious "Canonical" column appears in many tables — this is the normalization mapping leaking into the rendered output.

---

## Issue 3: No Table Detection for PDFs Without Ruled Lines (HIGH — 1 filing)

**Affected:** Nebiud24

**Root cause:** pdfplumber's default table extraction uses `lines` strategy, which looks for ruled borders/lines. Nebiud24's PDF uses no ruled lines — tables are structured only through spacing. pdfplumber finds 0 tables on all 11 pages with default settings but finds them correctly with `text` strategy.

**Impact:** All financial data is dumped as raw text instead of structured markdown tables.

**Fix needed:** Fall back to `text`-based table extraction strategy when the default `lines` strategy finds no tables on a page that contains financial data patterns.

---

## Issue 4: Cover Page Metadata Extraction Fails for Non-Standard Formats (HIGH — 3 filings)

**Affected:** Cola24, Nebiud24, Googl25 (and Open25 partially)

**Details:**

| Field | Cola24 | Nebiud24 | Googl25 | Nvda25 | Open25 |
|-------|--------|----------|---------|--------|--------|
| company | EMPTY | EMPTY | EMPTY | Correct | Correct |
| ticker | EMPTY | EMPTY | EMPTY | Correct | Correct |
| cik | EMPTY | EMPTY | EMPTY | Wrong* | Wrong* |
| filing_type | EMPTY | EMPTY | EMPTY | Correct | Correct |
| scale | millions | **units** (wrong) | EMPTY | millions | **units** (wrong) |

\* CIK field captures Commission File Number instead of actual CIK.

**Root causes:**
- Cola24 and Nebiud24 are **press releases**, not 10-K/10-Q filings. The cover page parser expects SEC filing cover structure (Commission File Number, Registrant name, etc.) which these don't have.
- Googl25 has no cover page detected because all pages were skipped by TOC filter.
- Scale detection depends on structured table parsing which may fail.
- The `cik` regex captures Commission File Number (e.g., "001-39253") rather than the actual CIK.

---

## Issue 5: Cash Flow Section Absorbs Unrelated Content (MEDIUM — 1 filing)

**Affected:** Cola24

**Root cause:** When the cash flow statement is detected but no subsequent section heading is found, all remaining pages get absorbed into the cash flow section. In Cola24, pages 13-29 (operating segments, GAAP/Non-GAAP reconciliation tables) are incorrectly included in the cash flow section.

**Impact:** The actual cash flow data from page 12 is lost in a sea of unrelated tables, and the reconciliation tables are garbled by the collapse logic (they have complex multi-dimensional headers the parser can't handle).

---

## Issue 6: Notes Extraction Falls Back to Wrong Content (MEDIUM — 1 filing)

**Affected:** Nvda25

**Root cause:** When Gemini is rate-limited and falls back to raw text, the raw-text fallback captures content from the wrong page range. For Nvda25, the Notes section (starting page 149) contains content from Part II Item 5 instead of the actual Notes to Financial Statements.

**Impact:** All 17 Notes (25 pages of detailed disclosures) are entirely missing from the output.

---

## Issue 7: Press Releases Are Misidentified as SEC Filings (LOW — 2 filings)

**Affected:** Cola24, Nebiud24

**Root cause:** `detect_report_type()` scores based on SEC vs IFRS patterns. Press releases containing terms like "Consolidated Statements of Income" score as SEC, but they lack the 10-K/10-Q structure. The parser doesn't distinguish between formal SEC filings and earnings press releases.

**Impact:** Missing sections are reported as warnings, but the parser doesn't fundamentally mishandle these — it just produces sparse output with missing metadata.

---

## Issue 8: Combined Documents Confuse Section Boundaries (LOW — 1 filing)

**Affected:** Nvda25

**Details:** The Nvda25 PDF is a combined document: pages 1-92 are an Annual Review/Proxy, and pages 93-181 are the actual 10-K. The parser processes the entire document, which means the cover page might pick up content from the Annual Review portion rather than the 10-K cover.

---

## Cross-Filing Failure Matrix

| Issue | Cola24 | Googl25 | Nebiud24 | Nvda25 | Open25 |
|-------|--------|---------|----------|--------|--------|
| TOC header kills detection | | X | | | X |
| Column collapse | X | | X | X | |
| No tables (no ruled lines) | | | X | | |
| Empty metadata | X | X | X | | |
| Wrong scale | | | X | | X |
| Cash flow absorbs extras | X | | | | |
| Notes fallback wrong content | | | | X | |
| Press release misidentified | X | | X | | |

---

## Proposed Fix Plan

### Phase 1: Fix Critical Blockers (unblocks 2 completely failed filings)

**Step 1.1 — Fix TOC page detection** (`section_split.py`)
- Change `_is_toc_page()` to require "TABLE OF CONTENTS" as a standalone heading line (not part of a running header like "Table of Contents Alphabet Inc.")
- Add heuristic: a real TOC page should have multiple lines ending with page numbers
- Preserve the existing ≥4-pattern-match fallback

**Step 1.2 — Fix multi-year column collapsing** (`programmatic.py`)
- Modify `tables_to_markdown()` / `collapse_row()` to preserve distinct column structure
- Detect column headers (year labels) and maintain them as separate columns
- Remove the spurious "Canonical" column from rendered output

### Phase 2: Improve Table Detection (unblocks borderless PDFs)

**Step 2.1 — Fallback to text-based table extraction** (`pdf_extract.py`)
- When pdfplumber's default `lines` strategy finds 0 tables on a page, retry with `text` strategy
- Only apply this fallback on pages that are part of a financial statement section

### Phase 3: Fix Metadata Extraction

**Step 3.1 — Improve scale detection** (`metadata.py`)
- Scan page text for patterns like "In USD $ millions", "in millions", "in thousands" even when no structured tables are found
- Fix: currently `scale` defaults to "units" when table parsing fails

**Step 3.2 — Fix CIK vs Commission File Number** (`programmatic.py` or `metadata.py`)
- The regex captures Commission File Number (e.g., "001-39253") as CIK
- Either rename the field or add a separate regex for CIK (which is typically a pure number like "1045810")

**Step 3.3 — Improve cover page parsing for press releases** (`programmatic.py`)
- Add fallback patterns for extracting company name and ticker from non-standard cover pages (press release headers, "NYSE: TICKER" patterns, etc.)

### Phase 4: Fix Section Boundary & Content Issues

**Step 4.1 — Prevent sections from absorbing unrelated pages** (`section_split.py`)
- Add a maximum page count or content-based boundary check so a section doesn't absorb the entire remainder of the document

**Step 4.2 — Fix Notes raw-text fallback page range** (`pipeline.py` or `gemini_client.py`)
- When using raw-text fallback for Notes, ensure the correct page range is used (the Notes section's actual start_page/end_page from section detection)

### Priority Order

1. **Step 1.1** (TOC fix) — Highest ROI, unblocks 2 of 5 test filings completely
2. **Step 1.2** (Column collapse) — Fixes table quality across all filings
3. **Step 2.1** (Text table fallback) — Unblocks borderless PDFs
4. **Step 3.1** (Scale detection) — Quick fix for wrong metadata
5. **Steps 3.2-3.3** (CIK and cover parsing) — Improves metadata accuracy
6. **Steps 4.1-4.2** (Section boundaries and notes fallback) — Edge case fixes
