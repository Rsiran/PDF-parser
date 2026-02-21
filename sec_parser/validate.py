"""Programmatic sanity checks for parsed financial statements."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    check: str
    status: str  # "PASS", "WARN", "FAIL", "SKIP"
    detail: str


# ---------------------------------------------------------------------------
# Numeric parsing
# ---------------------------------------------------------------------------

def parse_numeric(value: str) -> float | None:
    """Parse display-formatted financial numbers to float.

    Handles currency symbols, commas, parenthetical negatives, and dashes.
    Returns float or None for empty/dash values.
    """
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None

    # Remove currency symbols and whitespace
    s = re.sub(r"[$€£]", "", s).strip()

    # Dashes → None
    if s in ("—", "-", "–", ""):
        return None

    # Detect parenthetical negatives: "(1,234)" or "( 1,234 )"
    negative = False
    m = re.match(r"^\((.+)\)$", s)
    if m:
        negative = True
        s = m.group(1).strip()

    # Remove commas and remaining whitespace
    s = s.replace(",", "").replace(" ", "")

    try:
        result = float(s)
    except ValueError:
        return None

    return -result if negative else result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_first(data: dict[str, list[float]], key: str) -> float | None:
    """Get the first value from a list in the data dict, or None."""
    values = data.get(key)
    if values and len(values) > 0:
        return values[0]
    return None


def _check_equality(
    check_name: str,
    expected: float,
    actual: float,
    tolerance: float = 0.01,
) -> ValidationResult:
    """Compare two values with relative tolerance.

    Exact match → PASS, within tolerance → WARN, beyond → FAIL.
    """
    if expected == actual:
        return ValidationResult(
            check=check_name,
            status="PASS",
            detail=f"Expected {expected:,.2f}, got {actual:,.2f}",
        )

    # Relative difference
    denom = abs(expected) if expected != 0 else abs(actual)
    if denom == 0:
        # Both zero — exact match already handled above
        return ValidationResult(
            check=check_name,
            status="PASS",
            detail="Both values are zero",
        )

    rel_diff = abs(expected - actual) / denom
    if rel_diff <= tolerance:
        return ValidationResult(
            check=check_name,
            status="WARN",
            detail=f"Expected {expected:,.2f}, got {actual:,.2f} (off by {rel_diff:.2%})",
        )

    return ValidationResult(
        check=check_name,
        status="FAIL",
        detail=f"Expected {expected:,.2f}, got {actual:,.2f} (off by {rel_diff:.2%})",
    )


# ---------------------------------------------------------------------------
# Statement-level validators
# ---------------------------------------------------------------------------

def validate_balance_sheet(data: dict[str, list[float]]) -> list[ValidationResult]:
    """Check Total Assets == Total Liabilities + Total Stockholders' Equity."""
    results: list[ValidationResult] = []

    total_assets = _get_first(data, "Total Assets")
    total_liab_equity = _get_first(data, "Total Liabilities & Stockholders' Equity")

    # If we have the combined line, compare directly
    if total_assets is not None and total_liab_equity is not None:
        results.append(_check_equality(
            "BS Balance (Assets vs L+E)",
            total_assets,
            total_liab_equity,
        ))
        return results

    total_liabilities = _get_first(data, "Total Liabilities")
    total_equity = _get_first(data, "Total Stockholders' Equity")

    if total_assets is None or (total_liabilities is None and total_equity is None):
        results.append(ValidationResult(
            check="BS Balance (Assets vs L+E)",
            status="SKIP",
            detail="Missing key items for balance sheet check",
        ))
        return results

    liab = total_liabilities if total_liabilities is not None else 0.0
    eq = total_equity if total_equity is not None else 0.0
    results.append(_check_equality(
        "BS Balance (Assets vs L+E)",
        total_assets,
        liab + eq,
    ))
    return results


def validate_income_statement(data: dict[str, list[float]]) -> list[ValidationResult]:
    """Check Gross Profit == Revenue - |Cost of Revenue|. Check Net Income present."""
    results: list[ValidationResult] = []

    revenue = _get_first(data, "Revenue")
    cost_of_rev = _get_first(data, "Cost of Revenue")
    gross_profit = _get_first(data, "Gross Profit")

    if revenue is not None and cost_of_rev is not None and gross_profit is not None:
        expected_gp = revenue - abs(cost_of_rev)
        results.append(_check_equality(
            "IS Gross Profit Check",
            expected_gp,
            gross_profit,
        ))
    else:
        results.append(ValidationResult(
            check="IS Gross Profit Check",
            status="SKIP",
            detail="Missing Revenue, Cost of Revenue, or Gross Profit",
        ))

    net_income = _get_first(data, "Net Income")
    if net_income is not None:
        results.append(ValidationResult(
            check="IS Net Income Present",
            status="PASS",
            detail=f"Net Income = {net_income:,.2f}",
        ))
    else:
        results.append(ValidationResult(
            check="IS Net Income Present",
            status="SKIP",
            detail="Net Income not found",
        ))

    return results


def validate_cash_flow(data: dict[str, list[float]]) -> list[ValidationResult]:
    """Check Ending Cash == Beginning Cash + Net Change. Check activity sections."""
    results: list[ValidationResult] = []

    beginning = _get_first(data, "Beginning Cash")
    net_change = _get_first(data, "Net Change in Cash")
    ending = _get_first(data, "Ending Cash")

    if beginning is not None and net_change is not None and ending is not None:
        expected_ending = beginning + net_change
        results.append(_check_equality(
            "CF Cash Reconciliation",
            expected_ending,
            ending,
        ))
    else:
        results.append(ValidationResult(
            check="CF Cash Reconciliation",
            status="SKIP",
            detail="Missing Beginning Cash, Net Change, or Ending Cash",
        ))

    # Check activity sections
    sections = ["Net Cash from Operations", "Net Cash from Investing", "Net Cash from Financing"]
    present = [s for s in sections if _get_first(data, s) is not None]
    missing = [s for s in sections if _get_first(data, s) is None]

    if len(present) == 3:
        results.append(ValidationResult(
            check="CF Activity Sections",
            status="PASS",
            detail="All 3 activity sections present",
        ))
    else:
        results.append(ValidationResult(
            check="CF Activity Sections",
            status="WARN" if len(present) >= 2 else "FAIL",
            detail=f"Missing: {', '.join(missing)}",
        ))

    return results


def validate_cross_statement(
    statements: dict[str, dict[str, list[float]]],
) -> list[ValidationResult]:
    """Cross-statement checks: Net Income IS↔CF, Ending Cash CF↔BS."""
    results: list[ValidationResult] = []

    is_data = statements.get("income_statement", {})
    cf_data = statements.get("cash_flow", {})
    bs_data = statements.get("balance_sheet", {})

    # Net Income: IS vs CF — compare all columns, pass if any pair matches
    is_ni_vals = is_data.get("Net Income", [])
    cf_ni_vals = cf_data.get("Net Income", [])
    if is_ni_vals and cf_ni_vals:
        matched = any(
            abs(iv - cv) <= max(1, abs(iv) * 0.01)
            for iv in is_ni_vals for cv in cf_ni_vals
        )
        if matched:
            results.append(ValidationResult(
                check="Cross: Net Income (IS vs CF)",
                status="PASS",
                detail=f"IS values {is_ni_vals} match CF values {cf_ni_vals}",
            ))
        else:
            results.append(_check_equality(
                "Cross: Net Income (IS vs CF)",
                is_ni_vals[0],
                cf_ni_vals[0],
            ))
    else:
        results.append(ValidationResult(
            check="Cross: Net Income (IS vs CF)",
            status="SKIP",
            detail="Net Income not available in both IS and CF",
        ))

    # Ending Cash CF vs Cash on BS
    cf_ending = _get_first(cf_data, "Ending Cash")
    bs_cash = _get_first(bs_data, "Cash & Cash Equivalents")
    if cf_ending is not None and bs_cash is not None:
        result = _check_equality(
            "Cross: Cash (CF Ending vs BS)",
            cf_ending,
            bs_cash,
        )
        if result.status == "FAIL":
            # Check if restricted cash explains the difference
            restricted = _get_first(bs_data, "Restricted Cash")
            if restricted is not None:
                combined = _check_equality(
                    "Cross: Cash (CF Ending vs BS)",
                    cf_ending,
                    bs_cash + restricted,
                )
                if combined.status in ("PASS", "WARN"):
                    combined.detail += " (includes restricted cash)"
                    result = combined
        results.append(result)
    else:
        results.append(ValidationResult(
            check="Cross: Cash (CF Ending vs BS)",
            status="SKIP",
            detail="Ending Cash or BS Cash not available",
        ))

    return results


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_all_checks(
    statements: dict[str, dict[str, list[float]]],
) -> list[ValidationResult]:
    """Run all validation checks, return combined list."""
    results: list[ValidationResult] = []

    if "balance_sheet" in statements:
        results.extend(validate_balance_sheet(statements["balance_sheet"]))

    if "income_statement" in statements:
        results.extend(validate_income_statement(statements["income_statement"]))

    if "cash_flow" in statements:
        results.extend(validate_cash_flow(statements["cash_flow"]))

    # Cross-statement checks (run if at least 2 statement types present)
    if len(statements) >= 2:
        results.extend(validate_cross_statement(statements))

    return results


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_validation_markdown(results: list[ValidationResult]) -> str:
    """Render validation results as a markdown table."""
    if not results:
        return ""

    lines = [
        "| Check | Status | Detail |",
        "|:------|:-------|:-------|",
    ]
    for r in results:
        lines.append(f"| {r.check} | {r.status} | {r.detail} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def extract_statement_data(
    rows: list[list[str]],
) -> dict[str, list[float]]:
    """Extract {canonical_name: [numeric_values]} from normalized table rows.

    Row format: [label, canonical, val1, val2, ...]
    Skips rows with empty canonical name.
    """
    data: dict[str, list[float]] = {}
    for row in rows:
        if len(row) < 3:
            continue
        canonical = row[1].strip() if row[1] else ""
        if not canonical:
            continue
        values: list[float] = []
        for cell in row[2:]:
            v = parse_numeric(cell)
            if v is not None:
                values.append(v)
        if values:
            data[canonical] = values
    return data
