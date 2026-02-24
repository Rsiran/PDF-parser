"""Orchestrate full PDF -> markdown pipeline."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .detect import detect_10k_start_page, detect_report_type
from .edgar_client import (
    EdgarFetchError,
    clear_cache as clear_edgar_cache,
    extract_statement_facts,
    fetch_company_facts,
    fetch_submissions,
    find_filing_accession,
    load_xbrl_taxonomy_map,
    render_xbrl_statement,
)
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
from .confidence import (
    ExtractionConfidence,
    compute_confidence,
    cross_validate,
    render_confidence_markdown,
)
from .metadata import extract_metadata
from .normalize import load_taxonomy
from .programmatic import (
    _extract_column_headers,
    _parse_text_as_table,
    clean_prose,
    extract_cover_fields,
    format_exhibits,
    parse_cover_page,
    process_notes_fallback,
    tables_to_markdown,
)
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
    data_sources: dict[str, str] = field(default_factory=dict)  # section -> "xbrl"|"pdf"
    confidences: list = field(default_factory=list)  # list[ExtractionConfidence]


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

# Map section keys to XBRL taxonomy map keys (all 5 financial statements)
XBRL_STATEMENT_MAP = {
    INCOME_STATEMENT: "income_statement",
    BALANCE_SHEET: "balance_sheet",
    CASH_FLOW: "cash_flow",
    STOCKHOLDERS_EQUITY: "stockholders_equity",
    COMPREHENSIVE_INCOME: "comprehensive_income",
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


def process_pdf(
    pdf_path: Path,
    output_dir: Path,
    verbose: bool = False,
    use_xbrl: bool = True,
) -> ProcessingResult:
    """Process a financial report PDF into a structured markdown file.

    Auto-detects SEC vs IFRS report type.
    Returns a ProcessingResult with the output path, label mappings, and metadata.
    Raises RuntimeError for scanned PDFs or other unrecoverable errors.

    When use_xbrl=True (default), attempts to fetch XBRL data from SEC EDGAR
    for financial statements. Falls back to PDF extraction on failure.
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
    pre_10k_text = ""
    if tenk_start > 1:
        if verbose:
            print(f"  Combined document detected: 10-K starts at page {tenk_start}", file=sys.stderr)
        # Save first ~5000 chars of pre-10K pages for metadata fallback
        pre_parts = []
        for p in pages:
            if p.page_number >= tenk_start:
                break
            pre_parts.append(p.text)
            if sum(len(t) for t in pre_parts) > 5000:
                break
        pre_10k_text = "\n".join(pre_parts)[:5000]
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

    # Cover page — programmatic regex extraction (extract early for XBRL matching)
    cover_fields: list[tuple[str, str]] = []
    if COVER_PAGE in sections:
        if verbose:
            print(f"  Processing {SECTION_TITLES[COVER_PAGE]}...", file=sys.stderr)
        cover_fields = extract_cover_fields(sections[COVER_PAGE].text)
        processed[COVER_PAGE] = parse_cover_page(sections[COVER_PAGE].text)

    # For combined documents, supplement cover fields from pre-10K pages
    if pre_10k_text:
        field_labels = {label for label, _ in cover_fields}
        if "Company" not in field_labels or "Ticker" not in field_labels:
            pre_fields = extract_cover_fields(pre_10k_text)
            for label, value in pre_fields:
                if label not in field_labels:
                    cover_fields.append((label, value))
                    field_labels.add(label)

    # --- XBRL fetch (if enabled and CIK available) ---
    xbrl_facts_by_section: dict[str, object] = {}  # section_key -> XBRLStatementData
    data_sources: dict[str, str] = {}

    cover_lookup = dict(cover_fields)
    cik = cover_lookup.get("CIK", "")

    if use_xbrl and cik:
        try:
            xbrl_map = load_xbrl_taxonomy_map()
            if verbose:
                print(f"  Fetching XBRL data for CIK {cik}...", file=sys.stderr)
            company_facts = fetch_company_facts(cik)
            submissions = fetch_submissions(cik)

            # We need filing_type and period_end for accession matching
            filing_type_for_match = cover_lookup.get("Filing Type", "")
            from .metadata import _parse_period_date
            period_str = cover_lookup.get("Period", "")
            period_end_for_match, _ = _parse_period_date(period_str)

            if filing_type_for_match and period_end_for_match:
                accession = find_filing_accession(
                    submissions, filing_type_for_match, period_end_for_match
                )
                if accession:
                    if verbose:
                        print(f"  Found EDGAR filing: {accession}", file=sys.stderr)
                    for section_key, xbrl_stmt_type in XBRL_STATEMENT_MAP.items():
                        stmt_map = xbrl_map.get(xbrl_stmt_type, {})
                        if stmt_map:
                            xbrl_data = extract_statement_facts(
                                company_facts, accession, xbrl_stmt_type, stmt_map
                            )
                            if xbrl_data:
                                xbrl_facts_by_section[section_key] = xbrl_data
                    if verbose and xbrl_facts_by_section:
                        xbrl_sections = [SECTION_TITLES.get(k, k) for k in xbrl_facts_by_section]
                        print(f"  XBRL data found for: {', '.join(xbrl_sections)}", file=sys.stderr)
                elif verbose:
                    print(f"  No EDGAR filing match for {filing_type_for_match} {period_end_for_match}", file=sys.stderr)
            elif verbose:
                print("  Insufficient metadata for EDGAR filing match", file=sys.stderr)
        except EdgarFetchError as exc:
            if verbose:
                print(f"  XBRL fetch failed: {exc}", file=sys.stderr)
        except Exception as exc:
            if verbose:
                print(f"  XBRL fetch error: {exc}", file=sys.stderr)
    elif use_xbrl and not cik and verbose:
        print("  No CIK found — skipping XBRL fetch", file=sys.stderr)
    elif not use_xbrl and verbose:
        print("  XBRL disabled", file=sys.stderr)

    # Financial statements — XBRL if available, else programmatic table collapse
    normalized_rows: dict[str, list[list[str]]] = {}
    for key in FINANCIAL_STATEMENTS:
        if key in xbrl_facts_by_section:
            # Use XBRL data as primary source
            xbrl_data = xbrl_facts_by_section[key]
            if verbose:
                print(f"  Processing {SECTION_TITLES[key]} (XBRL)...", file=sys.stderr)
            processed[key] = render_xbrl_statement(xbrl_data)
            data_sources[XBRL_STATEMENT_MAP.get(key, key)] = "xbrl"
            # Also run PDF extraction for cross-validation (Phase 4)
            if key in sections and key in STATEMENT_TYPE_MAP:
                rows_out: list[list[str]] = []
                tables_to_markdown(
                    sections[key].text, sections[key].tables,
                    taxonomy=taxonomy, normalized_data_out=rows_out,
                )
                normalized_rows[key] = rows_out
        elif key in sections:
            section = sections[key]
            if verbose:
                print(f"  Processing {SECTION_TITLES[key]} (PDF)...", file=sys.stderr)
            rows_out = []
            result = tables_to_markdown(
                section.text, section.tables,
                taxonomy=taxonomy, normalized_data_out=rows_out,
            )
            # If tables_to_markdown returned plain text (no markdown table),
            # try parsing the text itself as a table (for PDFs like XOM where
            # pdfplumber tables lack row labels but text has complete data)
            if "|" not in result:
                period_headers, year_columns = _extract_column_headers(section.text)
                text_table = _parse_text_as_table(
                    section.text, period_headers, year_columns
                )
                if text_table:
                    result = text_table
            processed[key] = result
            if key in STATEMENT_TYPE_MAP:
                normalized_rows[key] = rows_out
            data_sources[XBRL_STATEMENT_MAP.get(key, key)] = "pdf"

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

    # Add data source and confidence info to metadata
    if data_sources:
        metadata["data_sources"] = data_sources

    # Run validation checks on normalized financial data
    statements: dict[str, dict[str, list[float]]] = {}
    for key, stmt_type in STATEMENT_TYPE_MAP.items():
        if key in normalized_rows:
            stmt_data = extract_statement_data(normalized_rows[key])
            if stmt_data:
                statements[stmt_type] = stmt_data

    validation_md = ""
    results = []
    if statements:
        results = run_all_checks(statements)
        validation_md = render_validation_markdown(results)
        if verbose and results:
            print(f"  Validation: {len(results)} checks run", file=sys.stderr)

    # --- Confidence scoring ---
    confidences: list[ExtractionConfidence] = []
    for section_key, xbrl_stmt_type in XBRL_STATEMENT_MAP.items():
        xbrl_data = xbrl_facts_by_section.get(section_key)
        pdf_data = statements.get(xbrl_stmt_type)

        # Cross-validate if both sources available
        discs = None
        if xbrl_data and pdf_data:
            discs = cross_validate(xbrl_data.line_items, pdf_data)
            # Print WARN/ERROR discrepancies to stderr always
            for d in discs:
                if d.severity in ("warn", "error"):
                    print(
                        f"  {d.severity.upper()}: {xbrl_stmt_type}.{d.line_item} "
                        f"XBRL={d.xbrl_value:,.0f} PDF={d.pdf_value:,.0f} "
                        f"({d.pct_difference:.1%})",
                        file=sys.stderr,
                    )

        # Determine validation status for this statement
        val_status = None
        if results:
            stmt_results = [r for r in results if xbrl_stmt_type.upper()[:2] in r.check.upper()[:5]]
            if stmt_results:
                if any(r.status == "FAIL" for r in stmt_results):
                    val_status = "FAIL"
                elif any(r.status == "WARN" for r in stmt_results):
                    val_status = "WARN"
                else:
                    val_status = "PASS"

        conf = compute_confidence(
            xbrl_data=xbrl_data,
            pdf_data=pdf_data,
            statement_type=xbrl_stmt_type,
            discrepancies=discs,
            validation_status=val_status,
        )
        if conf.xbrl_available or conf.pdf_available:
            confidences.append(conf)

    confidence_md = render_confidence_markdown(confidences) if confidences else ""

    # Add confidence scores to metadata
    if confidences:
        metadata["confidence"] = {
            c.statement_type: c.confidence for c in confidences
        }

    if verbose and confidences:
        print(f"  Confidence: {len(confidences)} statements scored", file=sys.stderr)

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
        confidence_markdown=confidence_md,
    )
    output_path = output_dir / f"{pdf_path.stem}.md"
    write_markdown(output_path, md_content)

    if verbose:
        print(f"  Written to {output_path}", file=sys.stderr)

    return ProcessingResult(
        output_path=output_path,
        mappings=mappings,
        metadata=metadata,
        data_sources=data_sources,
        confidences=confidences,
    )
