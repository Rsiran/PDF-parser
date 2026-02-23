"""Cross-validation and confidence scoring for XBRL vs PDF financial data."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Discrepancy:
    """A discrepancy between XBRL and PDF values for a line item."""
    line_item: str
    xbrl_value: float
    pdf_value: float
    difference: float  # absolute difference
    pct_difference: float  # as fraction, e.g. 0.05 = 5%
    severity: str  # "info", "warn", "error"


@dataclass
class ExtractionConfidence:
    """Confidence assessment for a single financial statement."""
    statement_type: str
    source: str  # "xbrl", "pdf", "xbrl+pdf"
    confidence: float  # 0.0 to 1.0
    xbrl_available: bool
    pdf_available: bool
    discrepancies: list[Discrepancy] = field(default_factory=list)


def cross_validate(
    xbrl_facts: dict[str, list[float | None]],
    pdf_facts: dict[str, list[float]],
    tolerance: float = 0.01,
) -> list[Discrepancy]:
    """Compare overlapping line items between XBRL and PDF extractions.

    Args:
        xbrl_facts: {canonical_name: [values]} from XBRL extraction
        pdf_facts: {canonical_name: [values]} from PDF extraction (via validate.extract_statement_data)
        tolerance: relative tolerance for "info" severity (default 1%)

    Returns list of Discrepancy objects for all overlapping line items.
    """
    discrepancies: list[Discrepancy] = []

    # Find overlapping canonical names
    common_keys = set(xbrl_facts.keys()) & set(pdf_facts.keys())

    for key in sorted(common_keys):
        xbrl_vals = xbrl_facts[key]
        pdf_vals = pdf_facts[key]

        # Compare first non-None value from each
        xbrl_val = next((v for v in xbrl_vals if v is not None), None)
        pdf_val = pdf_vals[0] if pdf_vals else None

        if xbrl_val is None or pdf_val is None:
            continue

        diff = abs(xbrl_val - pdf_val)
        denom = abs(xbrl_val) if xbrl_val != 0 else abs(pdf_val)
        if denom == 0:
            pct = 0.0
        else:
            pct = diff / denom

        # Determine severity
        if pct <= tolerance:
            severity = "info"
        elif pct <= 0.05:
            severity = "warn"
        else:
            severity = "error"

        discrepancies.append(Discrepancy(
            line_item=key,
            xbrl_value=xbrl_val,
            pdf_value=pdf_val,
            difference=diff,
            pct_difference=pct,
            severity=severity,
        ))

    return discrepancies


def compute_confidence(
    xbrl_data: object | None,
    pdf_data: dict[str, list[float]] | None,
    statement_type: str,
    discrepancies: list[Discrepancy] | None = None,
    validation_status: str | None = None,
) -> ExtractionConfidence:
    """Compute confidence score for a financial statement.

    Confidence levels:
        1.0 — XBRL + PDF both available and values match
        0.9 — XBRL only (no PDF to cross-validate)
        0.7 — PDF only, validation checks pass
        0.5 — PDF only, validation checks warn
        0.3 — PDF only, validation checks fail

    Args:
        xbrl_data: XBRLStatementData or None
        pdf_data: Parsed PDF data dict or None
        statement_type: e.g. "income_statement"
        discrepancies: Results from cross_validate(), if available
        validation_status: "PASS", "WARN", "FAIL", or None
    """
    xbrl_available = xbrl_data is not None
    pdf_available = pdf_data is not None and len(pdf_data) > 0

    if xbrl_available and pdf_available:
        # Both sources available — score based on discrepancies
        if discrepancies is not None:
            errors = [d for d in discrepancies if d.severity == "error"]
            warns = [d for d in discrepancies if d.severity == "warn"]
            if not errors and not warns:
                confidence = 1.0
                source = "xbrl+pdf"
            elif not errors:
                confidence = 0.95
                source = "xbrl+pdf"
            else:
                confidence = 0.8
                source = "xbrl"
        else:
            confidence = 0.9
            source = "xbrl+pdf"
        return ExtractionConfidence(
            statement_type=statement_type,
            source=source,
            confidence=confidence,
            xbrl_available=True,
            pdf_available=True,
            discrepancies=discrepancies or [],
        )

    if xbrl_available and not pdf_available:
        return ExtractionConfidence(
            statement_type=statement_type,
            source="xbrl",
            confidence=0.9,
            xbrl_available=True,
            pdf_available=False,
        )

    if pdf_available:
        # PDF only — score based on validation results
        if validation_status == "PASS":
            confidence = 0.7
        elif validation_status == "WARN":
            confidence = 0.5
        elif validation_status == "FAIL":
            confidence = 0.3
        else:
            confidence = 0.6  # No validation data
        return ExtractionConfidence(
            statement_type=statement_type,
            source="pdf",
            confidence=confidence,
            xbrl_available=False,
            pdf_available=True,
        )

    # Neither source available
    return ExtractionConfidence(
        statement_type=statement_type,
        source="none",
        confidence=0.0,
        xbrl_available=False,
        pdf_available=False,
    )


def render_confidence_markdown(confidences: list[ExtractionConfidence]) -> str:
    """Render confidence data as a markdown section.

    Includes a summary table and, if discrepancies exist, a detail table.
    Returns empty string if no confidence data.
    """
    if not confidences:
        return ""

    # Summary table
    lines = [
        "| Statement | Source | Confidence | Discrepancies |",
        "|:----------|:-------|:-----------|:--------------|",
    ]
    for c in confidences:
        disc_count = len(c.discrepancies)
        disc_summary = "None" if disc_count == 0 else f"{disc_count} found"
        errors = sum(1 for d in c.discrepancies if d.severity == "error")
        warns = sum(1 for d in c.discrepancies if d.severity == "warn")
        if errors:
            disc_summary = f"{disc_count} ({errors} ERROR, {warns} WARN)"
        elif warns:
            disc_summary = f"{disc_count} ({warns} WARN)"
        lines.append(
            f"| {c.statement_type} | {c.source} | {c.confidence:.1f} | {disc_summary} |"
        )

    # Discrepancy detail table (only if any exist)
    all_discs = [d for c in confidences for d in c.discrepancies]
    if all_discs:
        lines.append("")
        lines.append("### Discrepancy Details")
        lines.append("")
        lines.append("| Line Item | XBRL Value | PDF Value | Difference | Severity |")
        lines.append("|:----------|:-----------|:----------|:-----------|:---------|")
        for d in all_discs:
            lines.append(
                f"| {d.line_item} | {d.xbrl_value:,.2f} | {d.pdf_value:,.2f} | "
                f"{d.pct_difference:.2%} | {d.severity.upper()} |"
            )

    return "\n".join(lines)
