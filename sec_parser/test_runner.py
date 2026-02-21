"""Quality evaluation harness for SEC PDF parser output.

Processes PDFs through the pipeline and runs programmatic quality checks
against the markdown output. No AI calls — purely deterministic checks.

Usage:
    python -m sec_parser.test_runner                          # process + evaluate all PDFs
    python -m sec_parser.test_runner --eval-only              # evaluate existing output only
    python -m sec_parser.test_runner --report quality.md      # write markdown report
    python -m sec_parser.test_runner --pdf-dir my-pdfs/       # custom PDF directory
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class PDFReport:
    pdf_name: str
    md_path: Path | None
    error: str | None = None
    checks: list[CheckResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXPECTED_SECTIONS: dict[str, list[str]] = {
    "10-Q": [
        "Cover Page",
        "Consolidated Balance Sheets",
        "Consolidated Statements of Income",
        "Consolidated Statements of Cash Flows",
        "Consolidated Statements of Stockholders' Equity",
        "Notes to Financial Statements",
        "Management's Discussion and Analysis",
    ],
    "10-K": [
        "Cover Page",
        "Consolidated Balance Sheets",
        "Consolidated Statements of Income",
        "Consolidated Statements of Cash Flows",
        "Consolidated Statements of Stockholders' Equity",
        "Notes to Financial Statements",
        "Management's Discussion and Analysis",
        "Risk Factors",
    ],
}

FINANCIAL_TABLE_SECTIONS = [
    "Consolidated Balance Sheets",
    "Consolidated Statements of Income",
    "Consolidated Statements of Cash Flows",
    "Consolidated Statements of Stockholders' Equity",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_filing_type(md_content: str) -> str:
    """Detect filing type (10-Q or 10-K) from Cover Page table."""
    m = re.search(r"\|\s*Filing Type\s*\|\s*(10-[QK](?:/A)?)\s*\|", md_content)
    return m.group(1) if m else "10-Q"


def _extract_sections(md_content: str) -> dict[str, str]:
    """Split markdown on ## headings into {title: content} dict."""
    sections: dict[str, str] = {}
    current_title = ""
    current_lines: list[str] = []

    for line in md_content.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            if current_title:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title:
        sections[current_title] = "\n".join(current_lines).strip()

    return sections


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

def check_section_completeness(md_content: str, filing_type: str) -> CheckResult:
    """All expected ## sections are present (fuzzy substring match)."""
    sections = _extract_sections(md_content)
    section_titles = list(sections.keys())
    expected = EXPECTED_SECTIONS.get(filing_type, EXPECTED_SECTIONS["10-Q"])
    missing: list[str] = []

    for exp in expected:
        found = any(exp.lower() in title.lower() for title in section_titles)
        if not found:
            missing.append(exp)

    return CheckResult(
        name="section_completeness",
        passed=len(missing) == 0,
        message=f"{len(expected) - len(missing)}/{len(expected)} expected sections found",
        details=[f"Missing: {s}" for s in missing],
    )


def check_financial_tables_formatted(md_content: str, filing_type: str) -> CheckResult:
    """Financial sections contain pipe-delimited tables, not flat text."""
    sections = _extract_sections(md_content)
    failures: list[str] = []

    for fin_section in FINANCIAL_TABLE_SECTIONS:
        matched_key = None
        for title in sections:
            if fin_section.lower() in title.lower():
                matched_key = title
                break
        if matched_key is None:
            continue
        content = sections[matched_key]
        if "|" not in content:
            failures.append(f"{matched_key}: no pipe-delimited table found")

    return CheckResult(
        name="financial_tables_formatted",
        passed=len(failures) == 0,
        message=f"All present financial sections have markdown tables" if not failures else f"{len(failures)} section(s) lack tables",
        details=failures,
    )


def check_no_stray_page_numbers(md_content: str, filing_type: str) -> CheckResult:
    """No standalone page number lines outside tables."""
    stray: list[str] = []
    in_table = False

    for i, line in enumerate(md_content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            continue
        if in_table and not stripped.startswith("|"):
            in_table = False
        if not in_table and re.match(r"^\d{1,3}$", stripped):
            stray.append(f"Line {i}: '{stripped}'")

    return CheckResult(
        name="no_stray_page_numbers",
        passed=len(stray) == 0,
        message=f"No stray page numbers" if not stray else f"{len(stray)} stray page number(s)",
        details=stray[:10],
    )


def check_table_structure_valid(md_content: str, filing_type: str) -> CheckResult:
    """Every markdown table has consistent column counts."""
    issues: list[str] = []
    current_table_lines: list[tuple[int, str]] = []

    def _check_table(table_lines: list[tuple[int, str]]) -> None:
        if len(table_lines) < 2:
            return
        counts = [line.count("|") for _, line in table_lines]
        expected_count = counts[0]
        for idx, (lineno, line) in enumerate(table_lines):
            if counts[idx] != expected_count:
                issues.append(f"Line {lineno}: expected {expected_count} pipes, got {counts[idx]}")

    for i, line in enumerate(md_content.splitlines(), 1):
        if line.strip().startswith("|"):
            current_table_lines.append((i, line))
        else:
            if current_table_lines:
                _check_table(current_table_lines)
                current_table_lines = []
    if current_table_lines:
        _check_table(current_table_lines)

    return CheckResult(
        name="table_structure_valid",
        passed=len(issues) == 0,
        message="All tables have consistent column counts" if not issues else f"{len(issues)} column count mismatch(es)",
        details=issues[:10],
    )


def check_no_empty_sections(md_content: str, filing_type: str) -> CheckResult:
    """Every section has >20 chars of content."""
    sections = _extract_sections(md_content)
    empty: list[str] = []

    for title, content in sections.items():
        if len(content.strip()) <= 20:
            empty.append(f"{title}: only {len(content.strip())} chars")

    return CheckResult(
        name="no_empty_sections",
        passed=len(empty) == 0,
        message="All sections have content" if not empty else f"{len(empty)} empty section(s)",
        details=empty,
    )


def check_prose_quality(md_content: str, filing_type: str) -> CheckResult:
    """Notes & MD&A have ### subheadings, no 4+ consecutive blank lines."""
    sections = _extract_sections(md_content)
    issues: list[str] = []

    prose_sections = ["Notes to Financial Statements", "Management's Discussion and Analysis"]
    for sec_name in prose_sections:
        matched_key = None
        for title in sections:
            if sec_name.lower() in title.lower():
                matched_key = title
                break
        if matched_key is None:
            continue
        content = sections[matched_key]

        if "### " not in content:
            issues.append(f"{matched_key}: no ### subheadings found")

        if "\n\n\n\n" in content:
            issues.append(f"{matched_key}: has 4+ consecutive blank lines")

    return CheckResult(
        name="prose_quality",
        passed=len(issues) == 0,
        message="Prose sections have good structure" if not issues else f"{len(issues)} prose quality issue(s)",
        details=issues,
    )


def check_cover_page_fields(md_content: str, filing_type: str) -> CheckResult:
    """Cover Page has Filing Type, Company, Period Ended."""
    sections = _extract_sections(md_content)
    cover = ""
    for title in sections:
        if "cover page" in title.lower():
            cover = sections[title]
            break

    if not cover:
        return CheckResult(
            name="cover_page_fields",
            passed=False,
            message="No Cover Page section found",
        )

    required_fields = ["Filing Type", "Company", "Period Ended"]
    missing: list[str] = []
    for f in required_fields:
        if f not in cover:
            missing.append(f)

    return CheckResult(
        name="cover_page_fields",
        passed=len(missing) == 0,
        message="Cover Page has all required fields" if not missing else f"Missing: {', '.join(missing)}",
        details=[f"Missing field: {f}" for f in missing],
    )


def check_table_density(md_content: str, filing_type: str) -> CheckResult:
    """Financial sections have >=5 data rows each."""
    sections = _extract_sections(md_content)
    sparse: list[str] = []

    for fin_section in FINANCIAL_TABLE_SECTIONS:
        matched_key = None
        for title in sections:
            if fin_section.lower() in title.lower():
                matched_key = title
                break
        if matched_key is None:
            continue
        content = sections[matched_key]

        # Count data rows (table lines that aren't headers or separators)
        data_rows = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", stripped):
                data_rows += 1
        # Subtract header rows (first row of each table)
        # Rough: just check total >= 5
        if data_rows < 5:
            sparse.append(f"{matched_key}: only {data_rows} table row(s)")

    return CheckResult(
        name="table_density",
        passed=len(sparse) == 0,
        message="Financial sections have sufficient data rows" if not sparse else f"{len(sparse)} sparse section(s)",
        details=sparse,
    )


def check_no_pdf_artifacts(md_content: str, filing_type: str) -> CheckResult:
    """No repeated 'Table of Contents', no replacement char, no F-N page refs."""
    issues: list[str] = []

    toc_count = md_content.lower().count("table of contents")
    if toc_count > 2:
        issues.append(f"'Table of Contents' appears {toc_count} times")

    if "\ufffd" in md_content:
        count = md_content.count("\ufffd")
        issues.append(f"Unicode replacement character appears {count} time(s)")

    fn_refs = re.findall(r"\bF-\d+\b", md_content)
    if len(fn_refs) > 3:
        issues.append(f"F-N page references found: {len(fn_refs)} occurrences")

    return CheckResult(
        name="no_pdf_artifacts",
        passed=len(issues) == 0,
        message="No PDF artifacts detected" if not issues else f"{len(issues)} artifact type(s) found",
        details=issues,
    )


# Ordered list of all checks — append new checks here
ALL_CHECKS = [
    check_section_completeness,
    check_financial_tables_formatted,
    check_no_stray_page_numbers,
    check_table_structure_valid,
    check_no_empty_sections,
    check_prose_quality,
    check_cover_page_fields,
    check_table_density,
    check_no_pdf_artifacts,
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

# ANSI color codes
_GREEN = "\033[92m"
_RED = "\033[91m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _evaluate_markdown(md_path: Path) -> PDFReport:
    """Run all quality checks against a markdown file."""
    report = PDFReport(pdf_name=md_path.stem, md_path=md_path)

    try:
        md_content = md_path.read_text(encoding="utf-8")
    except Exception as exc:
        report.error = str(exc)
        return report

    filing_type = _detect_filing_type(md_content)

    for check_fn in ALL_CHECKS:
        result = check_fn(md_content, filing_type)
        report.checks.append(result)

    return report


def _print_report(report: PDFReport) -> None:
    """Print colored terminal output for a single PDF report."""
    print(f"\n{_BOLD}{report.pdf_name}{_RESET}")

    if report.error:
        print(f"  {_RED}ERROR: {report.error}{_RESET}")
        return

    for check in report.checks:
        icon = f"{_GREEN}PASS{_RESET}" if check.passed else f"{_RED}FAIL{_RESET}"
        print(f"  [{icon}] {check.name}: {check.message}")
        if not check.passed:
            for detail in check.details:
                print(f"         {detail}")


def _write_markdown_report(reports: list[PDFReport], report_path: Path) -> None:
    """Write a markdown summary report."""
    lines: list[str] = []
    lines.append("# Quality Evaluation Report\n")

    total_pass = 0
    total_fail = 0

    for report in reports:
        lines.append(f"## {report.pdf_name}\n")

        if report.error:
            lines.append(f"**ERROR:** {report.error}\n")
            continue

        for check in report.checks:
            status = "PASS" if check.passed else "FAIL"
            lines.append(f"- **{status}** `{check.name}`: {check.message}")
            if check.passed:
                total_pass += 1
            else:
                total_fail += 1
                for detail in check.details:
                    lines.append(f"  - {detail}")
        lines.append("")

    lines.append(f"---\n**Summary:** {total_pass} passed, {total_fail} failed\n")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SEC PDF parser quality evaluator")
    parser.add_argument("--pdf-dir", default="test-pdfs", help="Directory containing PDFs")
    parser.add_argument("--output-dir", default="output", help="Directory for markdown output")
    parser.add_argument("--eval-only", action="store_true", help="Only evaluate existing output")
    parser.add_argument("--report", metavar="PATH", help="Write markdown report to file")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    output_dir = Path(args.output_dir)

    if not args.eval_only:
        # Process PDFs through the pipeline
        pdfs = sorted(pdf_dir.glob("*.pdf"))
        if not pdfs:
            print(f"No PDFs found in {pdf_dir}")
            return 0

        from .pipeline import process_pdf

        output_dir.mkdir(parents=True, exist_ok=True)
        for pdf_path in pdfs:
            print(f"Processing {pdf_path.name}...", file=sys.stderr)
            try:
                process_pdf(pdf_path, output_dir, verbose=True)
            except Exception as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)

    # Evaluate output
    md_files = sorted(output_dir.glob("*.md"))
    if not md_files:
        print(f"No markdown files found in {output_dir}")
        return 0

    reports: list[PDFReport] = []
    any_failed = False

    for md_path in md_files:
        report = _evaluate_markdown(md_path)
        reports.append(report)
        _print_report(report)
        if report.error or any(not c.passed for c in report.checks):
            any_failed = True

    # Summary
    total_checks = sum(len(r.checks) for r in reports)
    total_passed = sum(sum(1 for c in r.checks if c.passed) for r in reports)
    total_errors = sum(1 for r in reports if r.error)

    print(f"\n{_BOLD}Summary:{_RESET} {total_passed}/{total_checks} checks passed", end="")
    if total_errors:
        print(f", {total_errors} pipeline error(s)", end="")
    print()

    if args.report:
        _write_markdown_report(reports, Path(args.report))

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

