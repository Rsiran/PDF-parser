"""Extract and format YAML front-matter metadata from SEC filing cover pages."""

from __future__ import annotations

import re
from datetime import datetime, timezone


# Quarter mapping: month name (lowercase) -> quarter label
_MONTH_TO_QUARTER = {
    "january": "Q?",
    "february": "Q?",
    "march": "Q1",
    "april": "Q?",
    "may": "Q?",
    "june": "Q2",
    "july": "Q?",
    "august": "Q?",
    "september": "Q3",
    "october": "Q?",
    "november": "Q?",
    "december": "Q?",
}


def _detect_fiscal_year_end(cover_text: str) -> int | None:
    """Detect fiscal year-end month from cover page text.

    Looks for patterns like 'fiscal year ended June 30' or
    'For the transition period from'.
    Returns the month number (1-12) or None if not detected.
    """
    # Pattern: "fiscal year ended MONTH DD" or "year ended MONTH DD"
    m = re.search(
        r"(?:fiscal\s+)?year\s+ended\s+(\w+)\s+\d{1,2}",
        cover_text,
        re.IGNORECASE,
    )
    if m:
        month_name = m.group(1).lower()
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        return months.get(month_name)
    return None


def _compute_fiscal_year(period_year: int | None, period_month: int | None, fiscal_year_end_month: int | None) -> int | None:
    """Compute the fiscal year number.

    The fiscal year is named by the calendar year in which it ends.
    E.g., period Sep 2025 with FY end June = FY2026 (ends June 2026).
    """
    if not period_year or not period_month:
        return period_year
    if not fiscal_year_end_month or fiscal_year_end_month == 12:
        return period_year  # calendar year = fiscal year
    # If period month is after FY end, we're in the NEXT fiscal year
    if period_month > fiscal_year_end_month:
        return period_year + 1
    return period_year


def infer_period_type(filing_type: str, period_str: str, fiscal_year_end_month: int | None = None) -> str:
    """Return Q1/Q2/Q3/Q4/FY based on filing type and period end date.

    10-K (and 10-K/A) always returns FY.
    10-Q returns the quarter inferred from the month in period_str.
    If fiscal_year_end_month is provided, quarters are calculated relative
    to the fiscal year end rather than the calendar year.
    """
    if filing_type.upper().startswith("10-K"):
        return "FY"

    # Extract month name from period string
    m = re.search(r"([A-Za-z]+)", period_str)
    if not m:
        return "Q?"

    month_name = m.group(1).lower()
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    month_num = month_map.get(month_name)
    if not month_num:
        return "Q?"

    if fiscal_year_end_month:
        # Calculate fiscal quarter relative to FY end
        # Fiscal Q1 starts the month after FY end
        fy_start_month = (fiscal_year_end_month % 12) + 1
        # How many months into the fiscal year is this period?
        months_into_fy = (month_num - fy_start_month) % 12 + 1
        # Each quarter is 3 months
        quarter = (months_into_fy - 1) // 3 + 1
        return f"Q{quarter}"

    # Fallback: calendar-year quarters
    return _MONTH_TO_QUARTER.get(month_name, "Q?")


def infer_scale(scale_hint: str | None) -> str:
    """Parse scale from strings like '(in thousands, except per share data)'.

    Returns one of: 'thousands', 'millions', 'billions', 'units'.
    """
    if not scale_hint:
        return "units"

    hint_lower = scale_hint.lower()
    # When both are present (e.g., "in millions, except ... in thousands"),
    # prefer the dollar-amount scale (millions)
    has_million = "million" in hint_lower
    has_thousand = "thousand" in hint_lower
    has_billion = "billion" in hint_lower
    if has_million and has_thousand:
        return "millions"  # dollar amounts take precedence
    if has_billion:
        return "billions"
    if has_million:
        return "millions"
    if has_thousand:
        return "thousands"
    return "units"


def _parse_period_date(period_str: str) -> tuple[str, int | None]:
    """Parse a period string like 'June 30, 2024' into (ISO date, year).

    Returns ('2024-06-30', 2024) or ('', None) if parsing fails.
    """
    if not period_str:
        return "", None

    # Try parsing common date formats
    for fmt in ("%B %d, %Y", "%B %d %Y"):
        try:
            dt = datetime.strptime(period_str.strip().replace(",", ", ").replace("  ", " "), fmt)
            return dt.strftime("%Y-%m-%d"), dt.year
        except ValueError:
            continue

    # Fallback: try to extract year at least
    m = re.search(r"(\d{4})", period_str)
    year = int(m.group(1)) if m else None
    return "", year


def extract_metadata(
    cover_fields: list[tuple[str, str]],
    scale_hint: str | None,
    source_pdf: str,
    cover_text: str = "",
) -> dict:
    """Build a metadata dict from cover page fields.

    Parameters
    ----------
    cover_fields : list of (label, value) tuples from cover page extraction
    scale_hint : string like "(in thousands...)" or None
    source_pdf : filename of the source PDF
    cover_text : full cover page text for fiscal year-end detection

    Returns
    -------
    dict with keys: company, ticker, cik, filing_type, period_end, period_type,
    fiscal_year, scale, currency, audited, source_pdf, parsed_at
    """
    # Build a lookup from labels
    lookup: dict[str, str] = {}
    for label, value in cover_fields:
        lookup[label] = value

    filing_type = lookup.get("Filing Type", "")
    period_str = lookup.get("Period", "")
    period_end, fiscal_year = _parse_period_date(period_str)

    fiscal_year_end_month = _detect_fiscal_year_end(cover_text) if cover_text else None
    period_type = infer_period_type(filing_type, period_str, fiscal_year_end_month) if filing_type else ""

    # Parse month from period string for fiscal year calculation
    period_month = None
    m = re.search(r"([A-Za-z]+)", period_str)
    if m:
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        period_month = month_map.get(m.group(1).lower())

    fiscal_year = _compute_fiscal_year(fiscal_year, period_month, fiscal_year_end_month)

    is_10k = filing_type.upper().startswith("10-K") if filing_type else False

    return {
        "company": lookup.get("Company", ""),
        "ticker": lookup.get("Ticker", ""),
        "cik": lookup.get("CIK", ""),
        "commission_file_number": lookup.get("Commission File Number", ""),
        "filing_type": filing_type,
        "period_end": period_end,
        "period_type": period_type,
        "fiscal_year": fiscal_year if fiscal_year else "",
        "scale": infer_scale(scale_hint),
        "currency": "USD",
        "audited": is_10k,
        "source_pdf": source_pdf,
        "parsed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _yaml_value(value: object) -> str:
    """Format a single value for YAML output."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float,)):
        return str(value)

    s = str(value)
    # Quote strings containing YAML-special characters
    if any(ch in s for ch in (":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "'", '"', "%", "@", "`")):
        # Use double quotes, escaping internal double quotes
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def metadata_to_yaml(meta: dict) -> str:
    """Render metadata dict as a YAML front-matter block (--- delimited).

    Uses manual string formatting (not pyyaml serialization).
    """
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"
