"""SEC EDGAR XBRL client — fetch structured financial data from EDGAR API."""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class EdgarFetchError(Exception):
    """Raised when an EDGAR API request fails."""


@dataclass
class XBRLStatementData:
    """Structured XBRL data for a single financial statement."""
    statement_type: str
    line_items: dict[str, list[float | None]]  # canonical_name -> [val_per_period]
    periods: list[str]  # ISO date strings for each column
    unit: str = "USD"


# In-memory cache: CIK -> (company_facts, submissions)
_cache: dict[str, dict] = {}

# Timestamp of last request for rate limiting
_last_request_time: float = 0.0


def _get_user_agent() -> str:
    """Get User-Agent from SEC_EDGAR_EMAIL env var. Required by SEC."""
    email = os.environ.get("SEC_EDGAR_EMAIL", "")
    if not email:
        raise EdgarFetchError(
            "SEC_EDGAR_EMAIL environment variable is required for EDGAR API access. "
            "Set it to your email address (e.g. 'your-name@example.com')."
        )
    return f"sec-parse/1.0 ({email})"


def _rate_limited_request(url: str) -> bytes:
    """Make an HTTP GET request with rate limiting and proper headers."""
    global _last_request_time

    # Rate limit: at least 100ms between requests
    elapsed = time.monotonic() - _last_request_time
    if elapsed < 0.1:
        time.sleep(0.1 - elapsed)

    user_agent = _get_user_agent()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            _last_request_time = time.monotonic()
            return resp.read()
    except urllib.error.HTTPError as e:
        raise EdgarFetchError(f"EDGAR API error {e.code} for {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise EdgarFetchError(f"Network error fetching {url}: {e.reason}") from e


def pad_cik(cik: str | int) -> str:
    """Zero-pad a CIK to 10 digits."""
    return str(cik).strip().zfill(10)


def fetch_company_facts(cik: str | int) -> dict:
    """Fetch all XBRL facts for a company from EDGAR.

    Returns the full JSON response from data.sec.gov/api/xbrl/companyfacts/.
    Results are cached in-memory per CIK for the batch run.
    """
    padded = pad_cik(cik)
    cache_key = f"facts_{padded}"

    if cache_key in _cache:
        return _cache[cache_key]

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json"
    data = json.loads(_rate_limited_request(url))
    _cache[cache_key] = data
    return data


def fetch_submissions(cik: str | int) -> dict:
    """Fetch filing submissions metadata for a company.

    Returns the full JSON response from data.sec.gov/submissions/.
    Results are cached in-memory per CIK for the batch run.
    """
    padded = pad_cik(cik)
    cache_key = f"subs_{padded}"

    if cache_key in _cache:
        return _cache[cache_key]

    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    data = json.loads(_rate_limited_request(url))
    _cache[cache_key] = data
    return data


def find_filing_accession(
    submissions: dict,
    filing_type: str,
    period_end: str,
) -> str | None:
    """Find the accession number for a specific filing.

    Args:
        submissions: Response from fetch_submissions()
        filing_type: e.g. "10-K", "10-Q"
        period_end: ISO date like "2024-06-30"

    Returns accession number (with dashes) or None if not found.
    """
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])

    if not forms or not dates or not accessions:
        return None

    # Normalize filing type for matching (e.g. "10-K" matches "10-K", "10-K/A")
    target_type = filing_type.upper().rstrip("/A")

    for i, form in enumerate(forms):
        form_base = form.upper().rstrip("/A")
        if form_base == target_type and i < len(dates) and i < len(accessions):
            # Compare dates — EDGAR uses YYYY-MM-DD format
            if dates[i] == period_end:
                return accessions[i]

    return None


def _accession_to_prefix(accession: str) -> str:
    """Convert accession number to the prefix used in XBRL fact references.

    EDGAR accession numbers come as "0000320193-24-000123" but XBRL facts
    reference them without dashes: "000032019324000123".
    """
    return accession.replace("-", "")


def load_xbrl_taxonomy_map() -> dict[str, dict[str, str]]:
    """Load XBRL concept -> canonical name mapping from xbrl_taxonomy_map.yaml.

    Returns dict keyed by statement_type, each containing {xbrl_concept: canonical_name}.
    """
    map_path = Path(__file__).parent / "xbrl_taxonomy_map.yaml"
    with open(map_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    result: dict[str, dict[str, str]] = {}
    for statement_type, concepts in raw.items():
        result[statement_type] = {}
        for concept_name, canonical_name in concepts.items():
            result[statement_type][concept_name] = canonical_name

    return result


def extract_statement_facts(
    company_facts: dict,
    accession: str,
    statement_type: str,
    xbrl_map: dict[str, str],
) -> XBRLStatementData | None:
    """Extract and organize XBRL facts for one financial statement.

    Args:
        company_facts: Response from fetch_company_facts()
        accession: Filing accession number (with dashes)
        statement_type: Key into xbrl_map (e.g. "income_statement")
        xbrl_map: {xbrl_concept: canonical_name} for this statement type

    Returns XBRLStatementData or None if insufficient data found.
    """
    acc_nodash = _accession_to_prefix(accession)

    us_gaap = company_facts.get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None

    # Collect facts for mapped concepts
    found_items: dict[str, dict[str, float]] = {}  # canonical -> {period_key: value}
    all_periods: set[str] = set()

    for xbrl_concept, canonical_name in xbrl_map.items():
        concept_data = us_gaap.get(xbrl_concept)
        if not concept_data:
            continue

        # Look in USD units first, then pure units (for ratios like EPS)
        for unit_key in ("USD", "USD/shares", "shares", "pure"):
            unit_data = concept_data.get("units", {}).get(unit_key, [])
            for fact in unit_data:
                # Filter to matching accession
                fact_acc = fact.get("accn", "").replace("-", "")
                if fact_acc != acc_nodash:
                    continue

                # Get the period end date
                end_date = fact.get("end", "")
                if not end_date:
                    continue

                val = fact.get("val")
                if val is None:
                    continue

                # For dimensional data (stockholders' equity), skip segment-filtered facts
                # unless we specifically want them
                if fact.get("segment"):
                    continue

                # Use end date as period key (handles instant and duration)
                period_key = end_date

                # Prefer duration facts over instant for IS/CF, instant for BS
                start = fact.get("start", "")
                if start:
                    period_key = f"{start}_{end_date}"

                if canonical_name not in found_items:
                    found_items[canonical_name] = {}
                found_items[canonical_name][period_key] = float(val)
                all_periods.add(period_key)

            if canonical_name in found_items:
                break  # Found data in this unit, don't check others

    if len(found_items) < 3:
        return None  # Not enough data to be useful

    # Sort periods chronologically and build columnar data
    sorted_periods = sorted(all_periods)

    # Group by end date to find the main reporting periods
    # (typically current period and prior year comparative)
    end_dates: dict[str, list[str]] = {}
    for p in sorted_periods:
        end = p.split("_")[-1] if "_" in p else p
        end_dates.setdefault(end, []).append(p)

    # Take the most recent end dates (up to 4 for 10-Q multi-period)
    recent_ends = sorted(end_dates.keys(), reverse=True)[:4]

    # For each end date, prefer the longest duration period
    final_periods: list[str] = []
    for end in sorted(recent_ends):
        candidates = end_dates[end]
        # Prefer duration (has start_end format) over instant (just end)
        durations = [c for c in candidates if "_" in c]
        if durations:
            # Pick the longest duration
            durations.sort(key=lambda x: x.split("_")[0])
            final_periods.append(durations[0])
        else:
            final_periods.append(candidates[0])

    if not final_periods:
        return None

    # Build line_items dict with values aligned to final_periods
    line_items: dict[str, list[float | None]] = {}
    for canonical, period_vals in found_items.items():
        values: list[float | None] = []
        for period in final_periods:
            values.append(period_vals.get(period))
        line_items[canonical] = values

    # Extract display periods (just end dates)
    display_periods = [p.split("_")[-1] if "_" in p else p for p in final_periods]

    return XBRLStatementData(
        statement_type=statement_type,
        line_items=line_items,
        periods=display_periods,
    )


def render_xbrl_statement(xbrl_data: XBRLStatementData, scale: str = "units") -> str:
    """Render XBRL statement data as a markdown table.

    Args:
        xbrl_data: Structured XBRL data from extract_statement_facts()
        scale: Scale factor from metadata ("millions", "thousands", etc.)

    Returns markdown table string.
    """
    if not xbrl_data.line_items or not xbrl_data.periods:
        return ""

    col_count = len(xbrl_data.periods) + 1  # +1 for label column

    # Header row
    header = [""] + xbrl_data.periods
    sep = [":---"] + ["---:"] * len(xbrl_data.periods)

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]

    for canonical, values in xbrl_data.line_items.items():
        cells = [canonical]
        for v in values:
            if v is None:
                cells.append("\u2014")
            elif v == int(v):
                cells.append(f"{int(v):,}")
            else:
                cells.append(f"{v:,.2f}")
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def clear_cache() -> None:
    """Clear the in-memory EDGAR cache. Call between batch runs if needed."""
    _cache.clear()
