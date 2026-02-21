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


def infer_period_type(filing_type: str, period_str: str) -> str:
    """Return Q1/Q2/Q3/Q4/FY based on filing type and period end date.

    10-K (and 10-K/A) always returns FY.
    10-Q returns the quarter inferred from the month in period_str.
    """
    if filing_type.upper().startswith("10-K"):
        return "FY"

    # Extract month name from period string
    m = re.search(r"([A-Za-z]+)", period_str)
    if not m:
        return "Q?"

    month = m.group(1).lower()
    return _MONTH_TO_QUARTER.get(month, "Q?")


def infer_scale(scale_hint: str | None) -> str:
    """Parse scale from strings like '(in thousands, except per share data)'.

    Returns one of: 'thousands', 'millions', 'billions', 'units'.
    """
    if not scale_hint:
        return "units"

    hint_lower = scale_hint.lower()
    if "thousand" in hint_lower:
        return "thousands"
    if "million" in hint_lower:
        return "millions"
    if "billion" in hint_lower:
        return "billions"
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
) -> dict:
    """Build a metadata dict from cover page fields.

    Parameters
    ----------
    cover_fields : list of (label, value) tuples from cover page extraction
    scale_hint : string like "(in thousands...)" or None
    source_pdf : filename of the source PDF

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
    period_type = infer_period_type(filing_type, period_str) if filing_type else ""
    is_10k = filing_type.upper().startswith("10-K") if filing_type else False

    return {
        "company": lookup.get("Company", ""),
        "ticker": lookup.get("Ticker", ""),
        "cik": lookup.get("CIK", ""),
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
