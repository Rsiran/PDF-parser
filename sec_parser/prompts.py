"""Prompt templates for Gemini API calls."""

_ANTI_HALLUCINATION_BLOCK = """\
CRITICAL CONSTRAINT — NEVER FABRICATE DATA:
- Only output numbers, labels, and dates that appear verbatim in the source text below.
- If data is incomplete or partially garbled, output exactly what is present — do NOT fill in gaps.
- If no usable data can be extracted, output `[TABLE EXTRACTION FAILED]`.
- Never invent line items, column headers, or numerical values.
- VERIFICATION: before returning, confirm every number in your output appears verbatim in the source.
"""

TABLE_NORMALIZATION_PROMPT = """\
You are a financial document processor. You will receive the text and raw table \
data extracted from a section of an SEC 10-K or 10-Q filing. The data may span \
multiple pages, so table fragments may be split across page boundaries.

{anti_hallucination}

Your task:
1. Merge any multi-page table fragments into a single coherent table.
2. Fix misaligned columns and handle merged/empty cells.
3. Preserve ALL numbers exactly as they appear — do not round, reformat, or omit any values.
4. For multi-period tables (e.g. "Three Months Ended" / "Six Months Ended"), use a \
two-row header: the first row for period groupings, the second for date columns.
5. Output a single clean markdown table.

Output ONLY the markdown table — no commentary, no explanation, no code fences.

## Section text and tables

{{content}}
""".format(anti_hallucination=_ANTI_HALLUCINATION_BLOCK)

NOTES_EXTRACTION_PROMPT = """\
You are a financial document processor. You will receive the text of the \
"Notes to Financial Statements" section from an SEC 10-K or 10-Q filing.

{anti_hallucination}
- If text is garbled or cut off, reproduce what is present and append `[TRUNCATED]`.

Your task:
1. Preserve ALL prose text exactly as written — do not summarize or omit anything.
2. Convert any embedded tabular data into clean markdown tables.
3. Structure the output with hierarchical markdown headings (## for each note, \
### for sub-sections).
4. Preserve ALL numbers exactly as they appear.
5. If a note title is detected (e.g. "Note 1 — Summary of Significant Accounting \
Policies"), use it as the heading.

Output ONLY markdown — no commentary, no code fences.

## Notes text

{{content}}
""".format(anti_hallucination=_ANTI_HALLUCINATION_BLOCK)

PROSE_SECTION_PROMPT = """\
You are a financial document processor. You will receive a prose-heavy section \
from an SEC 10-K or 10-Q filing (e.g. MD&A, Risk Factors, Controls & Procedures, \
Legal Proceedings).

{anti_hallucination}
- If text is garbled or cut off, reproduce what is present and append `[TRUNCATED]`.

Your task:
1. Clean up PDF extraction artifacts: remove page headers/footers, stray page numbers, \
and fix broken line breaks mid-sentence.
2. Preserve ALL prose in full — do NOT summarize or omit any content.
3. Convert any embedded tables into clean markdown tables.
4. Use markdown headings (##, ###) to reflect the document's heading structure.
5. Preserve ALL numbers exactly as they appear.

Output ONLY markdown — no commentary, no code fences.

## Section text

{{content}}
""".format(anti_hallucination=_ANTI_HALLUCINATION_BLOCK)

COVER_PAGE_PROMPT = """\
You are a financial document processor. You will receive the cover page of an SEC \
10-K or 10-Q filing.

{anti_hallucination}

Your task:
Extract the following metadata and output as structured markdown:
- Entity / Company name
- CIK number
- Filing type (e.g. 10-Q, 10-K)
- Fiscal period end date
- Outstanding share counts (if listed)
- Stock exchange and ticker symbol (if listed)

Output ONLY markdown — no commentary, no code fences.
Use this format:

## Cover Page

| Field | Value |
|-------|-------|
| Company | ... |
| CIK | ... |
| Filing Type | ... |
| Period | ... |
| Shares Outstanding | ... |
| Exchange / Ticker | ... |

Omit rows where the information is not present in the source.

## Cover page text

{{content}}
""".format(anti_hallucination=_ANTI_HALLUCINATION_BLOCK)
