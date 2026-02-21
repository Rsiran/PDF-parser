# sec-parse

Batch-process SEC 10-K/10-Q and IFRS financial filing PDFs into structured markdown with YAML front-matter.

Extracts financial statements, metadata, prose sections, and notes from PDF filings using pdfplumber for table/text extraction and programmatic parsing. The tool auto-detects whether a filing is SEC or IFRS and routes it through the appropriate pipeline. Only Notes extraction uses an LLM (Gemini) — everything else is regex and table-collapse logic.

## Features

- **SEC and IFRS support** — auto-detects filing type based on pattern scoring across the first pages
- **Financial statement tables** — collapses sparse pdfplumber rows, merges currency symbols and parenthetical negatives, detects column headers, merges multi-page table fragments
- **Cover page** — regex extraction of company name, filing type, period, CIK, ticker, exchange
- **Prose sections** (MD&A, Controls, Risk Factors, etc.) — removes page artifacts, fixes mid-sentence line breaks, adds markdown headings
- **Notes** — LLM-assisted structuring (Gemini), with graceful fallback to raw text
- **Section splitting** — regex-based detection of 13 SEC sections and 5 IFRS sections with text-level boundary splitting
- **Line-item normalization** — 3-tier fallback (exact match → fuzzy match → LLM) against a canonical taxonomy
- **Financial validation** — programmatic sanity checks (e.g. balance sheet equation)
- **Multi-filing consistency** — enforces consistent normalization mappings across batch runs and assigns filing sequence numbers by period

## Installation

```bash
pip install -e .
```

Requires Python 3.10+.

## Usage

```bash
# Process all PDFs in a folder
sec-parse ./filings -o ./output --verbose

# Use a specific Gemini model
sec-parse ./filings --model gemini-2.5-flash
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Required for Notes extraction and LLM normalization fallback |
| `GEMINI_MODEL` | Model to use (default: `gemini-2.5-flash`) |

If the Gemini API is unavailable or rate-limited, Notes fall back to raw extracted text and normalization skips the LLM tier.

## Output

Each PDF produces a single markdown file with YAML front-matter containing structured metadata:

```yaml
---
company_name: "Example Corp"
ticker: "EXMP"
cik: "0001234567"
filing_type: "10-Q"
period_end: "2025-06-30"
scale: "thousands"
currency: "USD"
filing_sequence: 1
---
```

Followed by sections in standard order:

```
## Cover Page
## Consolidated Balance Sheets
## Consolidated Statements of Income
## Consolidated Statements of Cash Flows
## Consolidated Statements of Stockholders' Equity
## Notes to Financial Statements
## Management's Discussion and Analysis
...
```

Financial tables are rendered as aligned markdown:

```
|  | Three Months Ended June 30, |  | Six Months Ended June 30, |  |
|  | 2025 | 2024 | 2025 | 2024 |
| :--- | ---: | ---: | ---: | ---: |
| Total Revenue | 13,572 | 10,344 | 22,892 | 20,130 |
| Gross loss | (1,588) | (2,897) | (891) | (5,712) |
```

## Architecture

```
PDF file
  → pdfplumber extracts text + tables per page
  → Auto-detect SEC vs IFRS report type
  → Regex-based section splitting (SEC: 13 sections, IFRS: 5 sections)
  → Per-section processing:
      • Cover page: regex metadata extraction
      • Financial statements: table collapse + normalization
      • Prose sections: artifact cleanup
      • Notes: Gemini LLM extraction with raw-text fallback
  → Metadata extraction from cover fields
  → Financial validation checks
  → Assemble final markdown with YAML front-matter
  → Write .md file to output directory
```

For multi-filing batch runs, the tool also enforces consistent line-item normalization across filings and assigns `filing_sequence` numbers ordered by `period_end` date.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

Tests are in `tests/`. Golden file tests compare output against reference files in `output/`.
