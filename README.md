# sec-parse

Batch-process SEC 10-K and 10-Q filing PDFs into structured markdown.

Extracts financial statements, MD&A, notes, and other sections from SEC filings using pdfplumber for table/text extraction and programmatic parsing for cleanup. Only the Notes section uses an LLM (Gemini) — everything else is regex and table-collapse logic.

## Features

- **Financial statement tables** — collapses sparse pdfplumber rows, merges currency symbols and parenthetical negatives, detects column headers, merges multi-page table fragments
- **Cover page** — regex extraction of company name, filing type, period, CIK, ticker, exchange
- **Prose sections** (MD&A, Controls, Risk Factors, etc.) — removes page artifacts, fixes mid-sentence line breaks, adds markdown headings
- **Notes** — LLM-assisted structuring (Gemini), with graceful fallback to raw text
- **Section splitting** — regex-based detection of 13 standard SEC filing sections with text-level boundary splitting to prevent duplication

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
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Required for Notes extraction (free tier: 20 calls/day) |
| `GEMINI_MODEL` | Model to use (default: `gemini-2.5-flash`) |

If the Gemini API is unavailable or rate-limited, Notes fall back to raw extracted text.

## Output

Each PDF produces a single markdown file with sections:

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

Financial tables are rendered as aligned markdown with proper column headers:

```
|  | Three Months Ended June 30, |  | Six Months Ended June 30, |  |
|  | 2025 | 2024 | 2025 | 2024 |
| :--- | ---: | ---: | ---: | ---: |
| Total Revenue | 13,572 | 10,344 | 22,892 | 20,130 |
| Gross loss | (1,588) | (2,897) | (891) | (5,712) |
```

## Architecture

```
PDF → pdfplumber (text + tables per page)
    → section_split (regex boundary detection)
    → programmatic parsers:
        - parse_cover_page()      → regex metadata extraction
        - tables_to_markdown()    → collapse rows, detect headers, render markdown
        - clean_prose()           → remove artifacts, add headings
    → gemini_client (Notes only) → LLM structuring
    → markdown_writer            → assemble final output
```
