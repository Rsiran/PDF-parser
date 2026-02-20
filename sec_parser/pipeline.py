"""Orchestrate full PDF -> markdown pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

from .gemini_client import extract_notes
from .programmatic import clean_prose, parse_cover_page, tables_to_markdown
from .markdown_writer import assemble_markdown, write_markdown
from .pdf_extract import detect_scanned, extract_pdf
from .section_split import (
    BALANCE_SHEET,
    CASH_FLOW,
    CONTROLS,
    COVER_PAGE,
    EXHIBITS,
    INCOME_STATEMENT,
    LEGAL_PROCEEDINGS,
    MARKET_RISK,
    MDA,
    NOTES,
    RISK_FACTORS,
    SECTION_TITLES,
    SIGNATURES,
    STOCKHOLDERS_EQUITY,
    split_sections,
)

FINANCIAL_STATEMENTS = [INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, STOCKHOLDERS_EQUITY]
PROSE_SECTIONS = [MDA, MARKET_RISK, CONTROLS, LEGAL_PROCEEDINGS, RISK_FACTORS]
PASSTHROUGH_SECTIONS = [EXHIBITS, SIGNATURES]


def process_pdf(pdf_path: Path, output_dir: Path, verbose: bool = False) -> Path:
    """Process a single SEC filing PDF into a structured markdown file.

    Returns the path to the output markdown file.
    Raises RuntimeError for scanned PDFs or other unrecoverable errors.
    """
    if verbose:
        print(f"Extracting text from {pdf_path.name}...", file=sys.stderr)

    pages = extract_pdf(pdf_path)
    detect_scanned(pages)

    if verbose:
        print(f"  {len(pages)} pages extracted", file=sys.stderr)

    sections = split_sections(pages)

    if verbose:
        found = [SECTION_TITLES.get(k, k) for k in sections]
        print(f"  Sections found: {', '.join(found)}", file=sys.stderr)

    # Warn about missing required sections
    required = [INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, NOTES]
    for key in required:
        if key not in sections:
            print(
                f"  WARNING: {SECTION_TITLES.get(key, key)} not found in {pdf_path.name}",
                file=sys.stderr,
            )

    processed: dict[str, str] = {}

    # Cover page — programmatic regex extraction
    if COVER_PAGE in sections:
        if verbose:
            print(f"  Processing {SECTION_TITLES[COVER_PAGE]}...", file=sys.stderr)
        processed[COVER_PAGE] = parse_cover_page(sections[COVER_PAGE].text)

    # Financial statements — programmatic table collapse (no LLM)
    for key in FINANCIAL_STATEMENTS:
        if key in sections:
            section = sections[key]
            if verbose:
                print(f"  Processing {SECTION_TITLES[key]}...", file=sys.stderr)
            processed[key] = tables_to_markdown(section.text, section.tables)

    # Notes — keep LLM (only remaining API call)
    if NOTES in sections:
        if verbose:
            print(f"  Processing {SECTION_TITLES[NOTES]}...", file=sys.stderr)
        try:
            processed[NOTES] = extract_notes(sections[NOTES].text, verbose=verbose)
        except Exception as exc:
            print(
                f"  WARNING: Notes extraction failed ({exc}), using raw text",
                file=sys.stderr,
            )
            processed[NOTES] = sections[NOTES].text

    # Prose sections — programmatic cleanup (no LLM)
    for key in PROSE_SECTIONS:
        if key in sections:
            section = sections[key]
            if verbose:
                print(f"  Processing {SECTION_TITLES[key]}...", file=sys.stderr)
            processed[key] = clean_prose(section.text, section.tables)

    # Passthrough sections (raw text, no LLM)
    for key in PASSTHROUGH_SECTIONS:
        if key in sections:
            processed[key] = sections[key].text

    # Assemble and write output
    md_content = assemble_markdown(pdf_path.name, processed)
    output_path = output_dir / f"{pdf_path.stem}.md"
    write_markdown(output_path, md_content)

    if verbose:
        print(f"  Written to {output_path}", file=sys.stderr)

    return output_path
