"""Orchestrate full PDF -> markdown pipeline."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .detect import detect_10k_start_page, detect_report_type
from .gemini_client import extract_notes
from .ifrs_section_split import (
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_INCOME_STATEMENT,
    IFRS_NOTES,
    IFRS_SECTION_TITLES,
    split_ifrs_sections,
)
from .metadata import extract_metadata
from .normalize import load_taxonomy
from .programmatic import clean_prose, extract_cover_fields, format_exhibits, parse_cover_page, process_notes_fallback, tables_to_markdown
from .validate import extract_statement_data, render_validation_markdown, run_all_checks
from .markdown_writer import (
    IFRS_REQUIRED_SECTIONS,
    IFRS_SECTION_ORDER,
    assemble_markdown,
    write_markdown,
)
from .pdf_extract import detect_scanned, extract_pdf
from .section_split import (
    BALANCE_SHEET,
    CASH_FLOW,
    COMPREHENSIVE_INCOME,
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

@dataclass
class ProcessingResult:
    """Result of processing a single PDF filing."""
    output_path: Path
    mappings: dict[str, str] = field(default_factory=dict)  # label -> canonical
    metadata: dict = field(default_factory=dict)


IFRS_FINANCIAL_STATEMENTS = [
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
]

FINANCIAL_STATEMENTS = [INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, STOCKHOLDERS_EQUITY, COMPREHENSIVE_INCOME]
PROSE_SECTIONS = [MDA, MARKET_RISK, CONTROLS, LEGAL_PROCEEDINGS, RISK_FACTORS]
PASSTHROUGH_SECTIONS = [EXHIBITS, SIGNATURES]

# Map section keys to validation statement types
STATEMENT_TYPE_MAP = {
    INCOME_STATEMENT: "income_statement",
    BALANCE_SHEET: "balance_sheet",
    CASH_FLOW: "cash_flow",
}


def _process_ifrs(
    pages: list,
    pdf_path: Path,
    output_dir: Path,
    verbose: bool,
) -> ProcessingResult:
    """Process an IFRS report PDF into markdown."""
    sections = split_ifrs_sections(pages)

    if verbose:
        found = [IFRS_SECTION_TITLES.get(k, k) for k in sections]
        print(f"  Sections found: {', '.join(found)}", file=sys.stderr)

    required = [IFRS_INCOME_STATEMENT, IFRS_BALANCE_SHEET, IFRS_CASH_FLOW, IFRS_EQUITY_CHANGES, IFRS_NOTES]
    for key in required:
        if key not in sections:
            print(
                f"  WARNING: {IFRS_SECTION_TITLES.get(key, key)} not found in {pdf_path.name}",
                file=sys.stderr,
            )

    processed: dict[str, str] = {}

    # Financial statements — programmatic table collapse
    for key in IFRS_FINANCIAL_STATEMENTS:
        if key in sections:
            section = sections[key]
            if verbose:
                print(f"  Processing {IFRS_SECTION_TITLES[key]}...", file=sys.stderr)
            processed[key] = tables_to_markdown(section.text, section.tables)

    # Notes — LLM if available, raw text fallback
    if IFRS_NOTES in sections:
        if verbose:
            print(f"  Processing {IFRS_SECTION_TITLES[IFRS_NOTES]}...", file=sys.stderr)
        try:
            processed[IFRS_NOTES] = extract_notes(
                sections[IFRS_NOTES].text, verbose=verbose
            )
        except Exception as exc:
            print(
                f"  WARNING: Notes extraction failed ({exc}), using raw text",
                file=sys.stderr,
            )
            processed[IFRS_NOTES] = sections[IFRS_NOTES].text

    # Assemble with IFRS ordering
    md_content = assemble_markdown(
        pdf_path.name,
        processed,
        section_order=IFRS_SECTION_ORDER,
        section_titles=IFRS_SECTION_TITLES,
        required_sections=IFRS_REQUIRED_SECTIONS,
    )
    output_path = output_dir / f"{pdf_path.stem}.md"
    write_markdown(output_path, md_content)

    if verbose:
        print(f"  Written to {output_path}", file=sys.stderr)

    return ProcessingResult(output_path=output_path)


def process_pdf(pdf_path: Path, output_dir: Path, verbose: bool = False) -> ProcessingResult:
    """Process a financial report PDF into a structured markdown file.

    Auto-detects SEC vs IFRS report type.
    Returns a ProcessingResult with the output path, label mappings, and metadata.
    Raises RuntimeError for scanned PDFs or other unrecoverable errors.
    """
    if verbose:
        print(f"Extracting text from {pdf_path.name}...", file=sys.stderr)

    pages = extract_pdf(pdf_path)
    detect_scanned(pages)

    if verbose:
        print(f"  {len(pages)} pages extracted", file=sys.stderr)

    report_type = detect_report_type(pages)
    if verbose:
        print(f"  Detected report type: {report_type.upper()}", file=sys.stderr)

    if report_type == "ifrs":
        return _process_ifrs(pages, pdf_path, output_dir, verbose)

    # === SEC pipeline ===

    # Detect combined document (annual report + 10-K)
    tenk_start = detect_10k_start_page(pages)
    if tenk_start > 1:
        if verbose:
            print(f"  Combined document detected: 10-K starts at page {tenk_start}", file=sys.stderr)
        pages = [p for p in pages if p.page_number >= tenk_start]

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

    # Load taxonomy for line-item normalization
    taxonomy = load_taxonomy()

    # Cover page — programmatic regex extraction
    if COVER_PAGE in sections:
        if verbose:
            print(f"  Processing {SECTION_TITLES[COVER_PAGE]}...", file=sys.stderr)
        processed[COVER_PAGE] = parse_cover_page(sections[COVER_PAGE].text)

    # Financial statements — programmatic table collapse with normalization
    normalized_rows: dict[str, list[list[str]]] = {}
    for key in FINANCIAL_STATEMENTS:
        if key in sections:
            section = sections[key]
            if verbose:
                print(f"  Processing {SECTION_TITLES[key]}...", file=sys.stderr)
            rows_out: list[list[str]] = []
            processed[key] = tables_to_markdown(
                section.text, section.tables,
                taxonomy=taxonomy, normalized_data_out=rows_out,
            )
            if key in STATEMENT_TYPE_MAP:
                normalized_rows[key] = rows_out

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
            processed[NOTES] = process_notes_fallback(sections[NOTES].text, sections[NOTES].tables)

    # Prose sections — programmatic cleanup (no LLM)
    for key in PROSE_SECTIONS:
        if key in sections:
            section = sections[key]
            if verbose:
                print(f"  Processing {SECTION_TITLES[key]}...", file=sys.stderr)
            processed[key] = clean_prose(section.text, section.tables)

    # Passthrough sections (light cleanup, no LLM)
    for key in PASSTHROUGH_SECTIONS:
        if key in sections:
            if key == EXHIBITS:
                processed[key] = format_exhibits(sections[key].text)
            else:
                processed[key] = clean_prose(sections[key].text)

    # Extract metadata from cover page fields
    cover_fields: list[tuple[str, str]] = []
    if COVER_PAGE in sections:
        cover_fields = extract_cover_fields(sections[COVER_PAGE].text)

    # Search for scale hint in financial statement text
    scale_hint: str | None = None
    _SCALE_PATTERNS = [
        # Parenthesized: "(in thousands, except per share data)"
        re.compile(
            r"\(in\s+(?:\w+\s+)?(?:thousands|millions|billions)[^)]*\)",
            re.IGNORECASE,
        ),
        # Unparenthesized: "In USD $ millions" or "in millions"
        re.compile(
            r"\bin\s+(?:(?:USD|U\.S\.\s*dollars?|CAD|EUR)\s*\$?\s*)?(?:thousands|millions|billions)\b",
            re.IGNORECASE,
        ),
        # Tabular: "(Amounts in millions)" or "amounts in thousands"
        re.compile(
            r"(?:amounts?|tabular\s+amounts?)\s+in\s+(?:thousands|millions|billions)",
            re.IGNORECASE,
        ),
        # Standalone: "(millions of dollars)" or "(thousands of euros)"
        re.compile(
            r"\((?:thousands|millions|billions)\s+of\s+(?:dollars|euros|pounds)\)",
            re.IGNORECASE,
        ),
    ]
    for key in FINANCIAL_STATEMENTS:
        if key in sections:
            for pat in _SCALE_PATTERNS:
                m = pat.search(sections[key].text)
                if m:
                    scale_hint = m.group(0)
                    break
            if scale_hint:
                break

    cover_text = sections[COVER_PAGE].text if COVER_PAGE in sections else ""
    metadata = extract_metadata(
        cover_fields=cover_fields,
        scale_hint=scale_hint,
        source_pdf=pdf_path.name,
        cover_text=cover_text,
    )

    # Run validation checks on normalized financial data
    statements: dict[str, dict[str, list[float]]] = {}
    for key, stmt_type in STATEMENT_TYPE_MAP.items():
        if key in normalized_rows:
            stmt_data = extract_statement_data(normalized_rows[key])
            if stmt_data:
                statements[stmt_type] = stmt_data

    validation_md = ""
    if statements:
        results = run_all_checks(statements)
        validation_md = render_validation_markdown(results)
        if verbose and results:
            print(f"  Validation: {len(results)} checks run", file=sys.stderr)

    # Collect label -> canonical mappings from normalized rows
    mappings: dict[str, str] = {}
    for rows in normalized_rows.values():
        for row in rows:
            if len(row) >= 2:
                label = row[0].strip()
                canonical = row[1].strip()
                if label and canonical:
                    mappings[label] = canonical

    # Assemble and write output
    md_content = assemble_markdown(
        pdf_path.name, processed, metadata=metadata,
        validation_markdown=validation_md,
    )
    output_path = output_dir / f"{pdf_path.stem}.md"
    write_markdown(output_path, md_content)

    if verbose:
        print(f"  Written to {output_path}", file=sys.stderr)

    return ProcessingResult(
        output_path=output_path,
        mappings=mappings,
        metadata=metadata,
    )
