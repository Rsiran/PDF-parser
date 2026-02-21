# Financial Modeling Enhancements Design

## Goal

Enhance the SEC filing PDF parser so its output is optimized for Claude in Excel to build 3-statement financial models with DCF valuations. Support parsing 4-6 filings per company (mix of 10-Ks and 10-Qs) with consistent, normalized output across filings.

## Context

The current parser produces clean markdown tables from SEC filings but lacks structured metadata, line item normalization, and validation — all critical when feeding data to an LLM for financial modeling.

## Design

### 1. Structured Front-Matter Metadata

Each markdown file gets a YAML front-matter block extracted from existing cover page parsing plus light inference:

```yaml
---
company: "Strive Inc."
ticker: "STRV"
cik: "0001234567"
filing_type: "10-Q"
period_end: "2025-09-30"
period_type: "Q3"
fiscal_year: 2025
scale: "thousands"
currency: "USD"
audited: false
source_pdf: "strive-10q-2025-09-30.pdf"
parsed_at: "2026-02-21T14:30:00Z"
filing_sequence: 3
---
```

Field derivation:
- `period_type` — inferred from filing type + period end date (10-K = FY, 10-Q = Q1/Q2/Q3)
- `scale` — extracted from "(in thousands...)" metadata line already captured by table parser
- `audited` — 10-K = true, 10-Q = false
- `filing_sequence` — assigned during multi-filing consistency pass, 1 = oldest

### 2. Line Item Normalization (Hybrid)

#### Taxonomy

A static `taxonomy.yaml` file with ~60-80 canonical line items organized by statement (income_statement, balance_sheet, cash_flow). Each canonical item has a list of known aliases.

#### Matching Pipeline

1. **Exact match** — strip whitespace/case, check aliases
2. **Fuzzy match** — token-based similarity (SequenceMatcher). Accept if confidence > 85%
3. **LLM fallback** — items below 85% batched into one Gemini call per filing: "Map these line items to these canonical names, or return UNMAPPED"
4. **Unmapped passthrough** — original label preserved with `<!-- unmapped -->` comment

#### Output Format

A "Canonical" column is added to financial statement tables:

```markdown
| Line Item | Canonical | Q3 2025 | Q3 2024 |
| :--- | :--- | ---: | ---: |
| Net revenues | Revenue | 1,234,567 | 1,100,432 |
| Cost of net revenues | Cost of Revenue | (890,123) | (812,345) |
```

Both original and canonical names preserved — no information lost.

### 3. Validation Checks

Programmatic checks run after normalization using canonical names.

#### Checks

| Category | Check |
| :--- | :--- |
| Balance Sheet | Total Assets == Total Liabilities + Total Stockholders' Equity (1% tolerance) |
| Income Statement | Gross Profit == Revenue - Cost of Revenue |
| Income Statement | Operating Income == Gross Profit - Total Operating Expenses |
| Income Statement | Net Income present and non-null |
| Cash Flow | Ending Cash == Beginning Cash + Net Change in Cash (1% tolerance) |
| Cash Flow | All three activity sections present |
| Cross-statement | Net Income on IS matches Net Income on CF |
| Cross-statement | Ending Cash on CF matches Cash on BS |

#### Output

Appended as a `## Validation` section at end of file:

```markdown
## Validation

| Check | Status | Detail |
| :--- | :--- | :--- |
| Balance sheet balances | PASS | Assets: 5,234,000 = L+E: 5,234,000 |
| Gross profit ties | PASS | 344,444 = 1,234,567 - 890,123 |
| Cash flow reconciles | WARN | Ending cash off by 2 (rounding) |
| Net income cross-check | FAIL | IS: 45,200 vs CF: 44,800 (diff: 400) |
```

Statuses: PASS, WARN (small rounding), FAIL (material discrepancy), SKIP (key item unmapped).

### 4. Multi-Filing Consistency

When a directory contains multiple PDFs:

1. All filings parsed independently (existing behavior)
2. A normalization consistency pass forces the same line-item-to-canonical mapping across all filings for the same company
3. Each file gets a `filing_sequence` number based on `period_end` date sorting

CLI interface unchanged:

```bash
sec-parse ./filings/strive/ -o ./output/strive/ --verbose
```

No consolidated file produced — each filing stays as its own markdown. Claude handles time-series assembly using consistent canonical names and period metadata.

## New Dependencies

- `pyyaml` — for taxonomy file and front-matter generation
- `difflib.SequenceMatcher` — for fuzzy matching (stdlib, no new dep)
- Gemini API usage increases slightly (one batch call per filing for unmapped items)

## New Files

- `taxonomy.yaml` — canonical line item definitions with aliases
- `normalize.py` — matching pipeline (exact, fuzzy, LLM fallback)
- `validate.py` — validation checks
- `metadata.py` — front-matter extraction and generation

## Modified Files

- `markdown_writer.py` — emit YAML front-matter, add Canonical column to tables, append validation section
- `main.py` — multi-filing consistency pass after individual parsing
- `programmatic.py` — expose parsed numeric values for validation (currently only outputs formatted strings)
