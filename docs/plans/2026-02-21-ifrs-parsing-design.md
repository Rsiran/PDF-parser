# IFRS Report Parsing Design

## Goal

Extend the PDF parser to handle Norwegian/European IFRS financial reports (Oslo Stock Exchange companies) alongside existing US SEC filings. Extract financial statements and notes only — skip narrative, ESG, and visual content.

## Auto-detection

`detect_report_type()` scans the first ~5 pages for markers:

- **SEC**: "FORM 10-K", "FORM 10-Q", "SECURITIES AND EXCHANGE COMMISSION", "CIK"
- **IFRS**: "IFRS", "EUR'000" / "NOK'000", CVR/org numbers, "Consolidated Statement of Profit or Loss"
- Returns `"sec"` or `"ifrs"`, defaulting to `"ifrs"` if unclear

## IFRS Section Splitter (`ifrs_section_split.py`)

Regex patterns targeting IFRS financial statement headers:

- **Income Statement**: "Statement of Profit or Loss" (and "Other Comprehensive Income")
- **Balance Sheet**: "Balance Sheet" or "Statement of Financial Position"
- **Cash Flow**: "Statement of Cash Flows"
- **Equity Changes**: "Statement of Changes in Equity"
- **Notes**: "Notes to the (Consolidated) Financial Statements"

For annual reports, financial sections typically start deep into the document (after narrative/ESG). The splitter only extracts these sections and ignores everything else. Parent company financials are skipped — consolidated statements are what matters.

## Pipeline Changes

`pipeline.py` dispatcher:

1. Extract pages with pdfplumber (shared)
2. Detect report type
3. Route to SEC section splitter or IFRS section splitter
4. Process sections with existing programmatic parsers (table collapsing, prose cleanup are format-agnostic)
5. Notes: Gemini if available, raw text fallback (same as SEC)
6. Assemble markdown with IFRS section order

## Output Format

Same markdown format, IFRS section ordering:

```markdown
# Cadeler-AR24
## Consolidated Statement of Profit or Loss
## Consolidated Balance Sheet
## Consolidated Statement of Changes in Equity
## Consolidated Statement of Cash Flows
## Notes to the Consolidated Financial Statements
```

## Shared Components (unchanged)

- `pdf_extract.py` — pdfplumber extraction
- `programmatic.py` — table collapsing, prose cleanup
- `gemini_client.py` / `prompts.py` — Notes LLM processing
- `markdown_writer.py` — minor addition for IFRS section order
- CLI interface — auto-detect handles routing
