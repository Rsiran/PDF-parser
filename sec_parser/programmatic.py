"""Programmatic parsers for SEC filing sections — no LLM needed."""

from __future__ import annotations

import re
from collections import Counter


# ---------------------------------------------------------------------------
# Cover Page
# ---------------------------------------------------------------------------

def extract_cover_fields(text: str) -> list[tuple[str, str]]:
    """Extract cover page metadata fields via regex.

    Returns a list of (label, value) tuples with all detected fields.
    """
    fields: list[tuple[str, str]] = []

    # Filing type
    m = re.search(r"FORM\s+(10-[QK](?:/A)?)", text, re.IGNORECASE)
    if m:
        fields.append(("Filing Type", m.group(1).upper()))

    # Company name — line before "(Exact name of registrant ...)"
    m = re.search(
        r"^[ \t]*(.+)\n\s*\((?:Exact|exact)\s+name\s+of\s+(?:R|r)egistrant",
        text,
        re.MULTILINE,
    )
    if m:
        name = m.group(1).strip()
        # Avoid grabbing the commission file number line
        if not re.match(r"Commission|File\s+Number|\d+-\d+", name, re.IGNORECASE):
            fields.append(("Company", name))

    # Period of report
    m = re.search(
        r"(?:(?:quarterly|annual)\s+period\s+ended|(?:fiscal\s+)?year\s+ended|period\s+of\s+report)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        fields.append(("Period", m.group(1).strip()))

    # Commission File Number
    m = re.search(r"Commission\s+File\s+Number[:\s]+([\d-]+)", text, re.IGNORECASE)
    if m:
        fields.append(("Commission File Number", m.group(1).strip()))

    # CIK — often near "Central Index Key"
    m = re.search(r"(?:Central\s+Index\s+Key|CIK)[:\s]+(\d+)", text, re.IGNORECASE)
    if m:
        fields.append(("CIK", m.group(1).strip()))

    # Shares outstanding
    m = re.search(r"(\d[\d,]+)\s+shares\s+of\s+common\s+stock", text, re.IGNORECASE)
    if m:
        fields.append(("Shares Outstanding", m.group(1).strip()))

    # Trading Symbol / Ticker
    # SEC 12(b) table format: header line with "Trading Symbol" followed by
    # data lines like "Class A common stock, $0.001 par value ASST The Nasdaq ..."
    # Match SEC 12(b) table header — handles both single-line
    # ("Title of Each Class Trading Symbol") and split-line formats
    # ("Trading\nTitle of each class symbol(s) ...")
    header_match = re.search(
        r"Title\s+of\s+(?:Each|each)\s+(?:Class|class)\s+(?:Trading\s+)?[Ss]ymbol",
        text,
        re.IGNORECASE,
    )
    ticker_found = False
    if header_match:
        # Look at lines after the header for ticker data rows
        after_header = text[header_match.end():]
        for line in after_header.splitlines()[:10]:
            line_s = line.strip()
            # Skip the header continuation line and empty lines
            # Note: don't skip lines just because they contain "exchange" — data rows
            # like "Common Stock XOM New York Stock Exchange" are valid ticker sources
            if not line_s or "registered" in line_s.lower():
                continue
            # Skip lines that are purely exchange header continuations
            if re.match(r"^\s*(?:Name\s+of\s+)?(?:Each\s+)?Exchange", line_s, re.IGNORECASE):
                continue
            if line_s.lower().startswith("indicate"):
                break
            # Data line pattern: description ending with "par value [per share]",
            # "stock", "warrant", etc., then TICKER (1-5 uppercase letters),
            # then exchange name. Also handle "N/A" as no ticker.
            # Also match "Common Stock, without par value XOM New York..."
            ticker_m = re.search(
                r"(?:par\s+value(?:\s+per\s+share)?|per\s+share|stock|warrant[s]?|unit[s]?|right[s]?|debenture[s]?|shares)\s+([A-Z]{1,5})\s",
                line_s,
            )
            if ticker_m:
                tok = ticker_m.group(1)
                if tok not in ("THE", "LLC", "INC", "NYSE", "EACH", "NAME"):
                    fields.append(("Ticker", tok))
                    ticker_found = True
                    break
    if not ticker_found:
        # Fallback: inline format "Trading Symbol(s): AAPL" or "Trading Symbol(s) AAPL"
        m = re.search(
            r"Trading\s+Symbol\(?s?\)?[:\s]+([A-Za-z]{1,5})\b",
            text,
            re.IGNORECASE,
        )
        if m and m.group(1).upper() not in ("NAME", "THE", "OF", "EACH", "N", "A"):
            fields.append(("Ticker", m.group(1).strip().upper()))

    # Exchange
    m = re.search(
        r"(?:Name\s+of\s+.*exchange|registered)[:\s]*((?:NYSE|NASDAQ|New\s+York\s+Stock\s+Exchange)[^\n]*)",
        text,
        re.IGNORECASE,
    )
    if m:
        exchange = m.group(1).strip().rstrip(".")
        fields.append(("Exchange", exchange))

    # State of Incorporation — "(State or other jurisdiction of incorporation...)"
    m = re.search(
        r"^(.+)\n\s*\((?:State|state)\s+or\s+other\s+jurisdiction\s+of\s+incorporat",
        text,
        re.MULTILINE,
    )
    if m:
        state = m.group(1).strip()
        if len(state) < 60:
            fields.append(("State of Incorporation", state))

    # Address — multi-line capture above "(Address of principal executive offices...)"
    m = re.search(
        r"\((?:Address|address)\s+of\s+principal\s+executive\s+offic",
        text,
    )
    if m:
        # Look at the 1-3 lines before this match
        before = text[:m.start()]
        lines_before = [l.strip() for l in before.splitlines() if l.strip()]
        # Take up to 3 lines before, filtering out non-address content
        addr_parts = []
        for line in reversed(lines_before[-3:]):
            # Stop if we hit something that's not an address line
            if re.match(r"(?:Commission|File\s+Number|Form\s+10|UNITED\s+STATES|SECURITIES)", line, re.IGNORECASE):
                break
            if len(line) > 120:
                break
            if re.match(r"^\(", line):  # another parenthetical descriptor
                break
            # Skip SEC cover page label fragments (continuation lines of
            # parenthetical descriptors like "of incorporation or organization)")
            if re.search(r"incorporation\b|Identification\s+N[ou]", line, re.IGNORECASE):
                continue
            addr_parts.insert(0, line)
        if addr_parts:
            address = ", ".join(addr_parts)
            if len(address) < 200:
                fields.append(("Address", address))

    # Phone — pattern like "(xxx) xxx-xxxx" or "xxx-xxx-xxxx" near
    # "Registrant's telephone number"
    m = re.search(
        r"(?:telephone\s+number|phone)[^)]*?(\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        fields.append(("Phone", m.group(1).strip()))

    # --- Fallbacks for press releases / non-standard covers ---

    labels = {label for label, _ in fields}

    # Fallback company name: "The Xyz Company today reported..."
    # or first line of text if it looks like a company name
    if "Company" not in labels:
        # Pattern: "(EXCHANGE: TICKER)" often preceded by company name
        m = re.search(
            r"([A-Z][\w &.,'-]+?)\s*\((?:NYSE|NASDAQ|Nasdaq|TSX|LSE)[:\s]+([A-Z]{1,5})\)",
            text,
        )
        if m:
            fields.append(("Company", m.group(1).strip().rstrip(",")))
            if "Ticker" not in labels:
                fields.append(("Ticker", m.group(2).strip()))
                ticker_found = True
        else:
            # Pattern: "The Xyz Company today reported/announced..."
            m = re.search(
                r"((?:The\s+)?[A-Z][\w\s&.,'-]+?(?:Company|Inc\.|Corp(?:oration)?\.?|Ltd\.?|N\.V\.|plc|Group|LP))\s+today\s+(?:reported|announced)",
                text,
            )
            if m:
                fields.append(("Company", m.group(1).strip().rstrip(",")))


    # Fallback ticker: "NYSE: KO" or "NASDAQ: NBIS" anywhere in text
    if "Ticker" not in labels and not ticker_found:
        m = re.search(
            r"(?:NYSE|NASDAQ|Nasdaq|TSX|LSE)[:\s]+([A-Z]{1,5})\b",
            text,
        )
        if m and m.group(1) not in ("THE", "LLC", "INC", "NYSE", "EACH", "NAME"):
            fields.append(("Ticker", m.group(1).strip()))

    # Fallback period: "ended December 31, 2025" or
    # "quarter and full year 2025 results" / "full-year 2025 financial results"
    if "Period" not in labels:
        m = re.search(
            r"ended\s+(\w+\s+\d{1,2},?\s+\d{4})",
            text,
            re.IGNORECASE,
        )
        if m:
            fields.append(("Period", m.group(1).strip()))

    return fields


def parse_cover_page(text: str) -> str:
    """Extract cover page metadata via regex and return a markdown table."""
    fields = extract_cover_fields(text)

    if not fields:
        return text  # fallback — return raw text if nothing matched

    lines = ["| Field | Value |", "|-------|-------|"]
    for label, value in fields:
        lines.append(f"| {label} | {value} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exhibits formatting
# ---------------------------------------------------------------------------

_EXHIBIT_NUM_RE = re.compile(
    r"^(\d{1,3}(?:\.\d{1,3})?(?:\.\w+)?)\s",
)


def format_exhibits(section_text: str) -> str:
    """Format an Exhibits section as a structured markdown list.

    Detects exhibit entries (lines starting with patterns like "31.1", "32",
    "101.INS") and converts them to markdown list items. Falls back to
    clean_prose() if no exhibit patterns are found.
    """
    lines = section_text.splitlines()
    result: list[str] = []
    exhibit_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            continue
        if re.match(r"^\s*\d{1,3}\s*$", stripped):
            continue
        if _EXHIBIT_NUM_RE.match(stripped):
            result.append(f"- {stripped}")
            exhibit_count += 1
        else:
            result.append(stripped)

    if exhibit_count < 2:
        return clean_prose(section_text)

    text = "\n".join(result)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def collapse_row(row: list[str]) -> list[str]:
    """Collapse a sparse pdfplumber row into dense cells.

    Handles:
    - Isolated '$' merging with next value: ['$', '854'] → ['$ 854']
    - Parenthetical negatives split across cells: ['(13,756', ')'] → ['(13,756)']
    - Empty cell skipping

    Example:
        ['Cash', '', '$', '854', '', '', '$', '1,212', '']
        → ['Cash', '$ 854', '$ 1,212']

        ['Net loss', '', '$', '(13,756', ')', '', '$', '(28,486', ')']
        → ['Net loss', '$ (13,756)', '$ (28,486)']
    """
    # First pass: merge currency symbols and parenthetical negatives
    merged: list[str] = []
    i = 0
    while i < len(row):
        cell = (row[i] or "").strip()

        # Currency symbol — merge with next non-empty cell
        if cell in ("$", "€", "£"):
            j = i + 1
            while j < len(row) and not (row[j] or "").strip():
                j += 1
            if j < len(row):
                next_val = (row[j] or "").strip()
                # Check if next value is an open paren negative like "(13,756"
                # and the cell after that is ")"
                if next_val.startswith("(") and not next_val.endswith(")"):
                    k = j + 1
                    while k < len(row) and not (row[k] or "").strip():
                        k += 1
                    if k < len(row) and (row[k] or "").strip() == ")":
                        merged.append(f"{cell} {next_val})")
                        i = k + 1
                        continue
                merged.append(f"{cell} {next_val}")
                i = j + 1
            else:
                merged.append(cell)
                i += 1

        # Open-paren negative without currency — "(13,756" followed by ")"
        elif cell.startswith("(") and not cell.endswith(")") and re.match(r"^\([\d,]+\.?\d*$", cell):
            j = i + 1
            while j < len(row) and not (row[j] or "").strip():
                j += 1
            if j < len(row) and (row[j] or "").strip() == ")":
                merged.append(f"{cell})")
                i = j + 1
            else:
                merged.append(cell)
                i += 1

        # Percentage symbol — merge with previous value cell
        elif cell == "%":
            if merged:
                merged[-1] = merged[-1] + "%"
            i += 1

        # Standalone closing paren — already handled above, skip if leftover
        elif cell == ")":
            i += 1

        elif cell:
            merged.append(cell)
            i += 1
        else:
            i += 1

    return merged


def _collapse_table_positional(table: list[list[str]]) -> list[list[str]]:
    """Collapse a table with position-aware alignment for wide sparse tables.

    Normal tables (< 10 raw columns) use standard collapse_row().
    Wide sparse tables (≥ 10 raw columns, e.g. stockholders' equity) get
    position-aware handling: a column map is built from the fullest rows,
    and each row's values are placed into the correct logical column based
    on their raw cell positions.

    This prevents sparse rows like SBC (which only populate APIC and Total
    columns) from being left-shifted by collapse_row()'s empty-cell stripping.
    """
    if not table:
        return []

    max_raw_cols = max(len(row) for row in table)
    if max_raw_cols < 10:
        # Normal table — standard collapse
        return [collapse_row(row) for row in table]

    # --- Wide sparse table: position-aware collapse ---

    # Step 1: Find which raw cell positions hold data across all rows.
    # Build a "column map": list of raw indices that are value columns.
    # We look at the rows with the MOST non-empty cells (typically "Balance" rows).
    row_fill_counts = []
    for ri, row in enumerate(table):
        non_empty = sum(1 for c in row if (c or "").strip())
        row_fill_counts.append((non_empty, ri))
    row_fill_counts.sort(reverse=True)

    # Use the top ~3 fullest rows to determine the column positions
    ref_positions: set[int] = set()
    for _, ri in row_fill_counts[:3]:
        row = table[ri]
        # After collapsing currency symbols ($+value), identify which raw
        # positions are "anchor" positions (where values land)
        i = 0
        while i < len(row):
            cell = (row[i] or "").strip()
            if cell in ("$", "€", "£"):
                # Currency symbol — the anchor position is the symbol position
                ref_positions.add(i)
                # Skip past the value cell
                j = i + 1
                while j < len(row) and not (row[j] or "").strip():
                    j += 1
                i = j + 1 if j < len(row) else i + 1
            elif cell:
                ref_positions.add(i)
                i += 1
            else:
                i += 1

    if not ref_positions:
        return [collapse_row(row) for row in table]

    # Sort into a column map: ordered list of raw positions → logical column indices
    col_map = sorted(ref_positions)
    num_cols = len(col_map)

    if num_cols < 3:
        # Too few columns detected — fall back to standard collapse
        return [collapse_row(row) for row in table]

    # Step 2: For each row, place values into logical columns
    result: list[list[str]] = []
    for row in table:
        # First, do the standard currency/paren merging per-cell
        # but track which raw position each merged value came from
        merged_with_pos: list[tuple[int, str]] = []
        i = 0
        while i < len(row):
            cell = (row[i] or "").strip()
            if cell in ("$", "€", "£"):
                anchor = i
                j = i + 1
                while j < len(row) and not (row[j] or "").strip():
                    j += 1
                if j < len(row):
                    next_val = (row[j] or "").strip()
                    if next_val.startswith("(") and not next_val.endswith(")"):
                        k = j + 1
                        while k < len(row) and not (row[k] or "").strip():
                            k += 1
                        if k < len(row) and (row[k] or "").strip() == ")":
                            merged_with_pos.append((anchor, f"{cell} {next_val})"))
                            i = k + 1
                            continue
                    merged_with_pos.append((anchor, f"{cell} {next_val}"))
                    i = j + 1
                else:
                    merged_with_pos.append((anchor, cell))
                    i += 1
            elif cell.startswith("(") and not cell.endswith(")") and re.match(r"^\([\d,]+\.?\d*$", cell):
                anchor = i
                j = i + 1
                while j < len(row) and not (row[j] or "").strip():
                    j += 1
                if j < len(row) and (row[j] or "").strip() == ")":
                    merged_with_pos.append((anchor, f"{cell})"))
                    i = j + 1
                else:
                    merged_with_pos.append((anchor, cell))
                    i += 1
            elif cell == "%" and merged_with_pos:
                prev_pos, prev_val = merged_with_pos[-1]
                merged_with_pos[-1] = (prev_pos, prev_val + "%")
                i += 1
            elif cell == ")":
                i += 1
            elif cell:
                merged_with_pos.append((i, cell))
                i += 1
            else:
                i += 1

        if not merged_with_pos:
            continue

        # Map each value to its nearest logical column
        out_row = [""] * num_cols
        used: set[int] = set()
        for raw_pos, val in merged_with_pos:
            # Find the closest column map position
            best_col = min(range(num_cols), key=lambda c: abs(col_map[c] - raw_pos))
            # If already used, try adjacent
            if best_col in used:
                for offset in range(1, num_cols):
                    if best_col + offset < num_cols and best_col + offset not in used:
                        best_col = best_col + offset
                        break
                    if best_col - offset >= 0 and best_col - offset not in used:
                        best_col = best_col - offset
                        break
            out_row[best_col] = val
            used.add(best_col)

        result.append(out_row)

    return result


# Numeric value token in financial tables (for splitting single-column rows)
_VALUE_TOKEN = re.compile(
    r"(?:\$\s*)?"           # optional dollar sign
    r"(?:"
    r"\([\d,]+\.?\d*\)"     # parenthetical negative like (13,756)
    r"|[\d,]+\.?\d*"        # regular number like 130,497 or 2.94
    r"|[—–]"                # em-dash, en-dash
    r")"
    r"%?"                   # optional percent
)

# Date fragments that should not be treated as values
_DATE_FRAG = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}",
    re.IGNORECASE,
)


def split_single_col_row(text: str) -> list[str]:
    """Split a single-column table row into [label, val1, val2, ...].

    pdfplumber sometimes returns financial tables as single-column data
    where all values are concatenated into one string, e.g.:
        'Revenue $ 130,497 $ 60,922 $ 26,974'
    This function splits it into:
        ['Revenue', '$ 130,497', '$ 60,922', '$ 26,974']

    Handles date fragments in labels (e.g. "Jan 30, 2022") by masking them
    so they are not mistakenly treated as numeric values.
    """
    text = text.strip()
    if not text:
        return [text]

    # Mask date fragments so they're not treated as values
    date_spans = [(m.start(), m.end()) for m in _DATE_FRAG.finditer(text)]

    # Find all value matches, skipping those inside date fragments
    values = []
    for m in _VALUE_TOKEN.finditer(text):
        in_date = any(ds <= m.start() < de for ds, de in date_spans)
        if not in_date:
            values.append(m)

    if not values:
        return [text]

    # Walk backwards from end to find contiguous trailing values
    val_spans: list[tuple[int, int, str]] = []
    for m in reversed(values):
        end_of_interest = len(text) if not val_spans else val_spans[-1][0]
        between = text[m.end():end_of_interest].strip()
        if not between:
            val_spans.append((m.start(), m.end(), m.group().strip()))
        else:
            break

    if not val_spans:
        return [text]

    val_spans.reverse()
    split_pos = val_spans[0][0]
    label = text[:split_pos].strip()
    vals = [v[2] for v in val_spans]

    if not label and vals:
        return vals
    if label:
        return [label] + vals
    return [text]


def _extract_column_headers(text: str) -> tuple[list[str], list[str]]:
    """Extract period headers and year sub-headers from section text.

    Returns (period_headers, year_columns) where:
    - period_headers: e.g. ["Three Months Ended June 30,", "Six Months Ended June 30,"]
    - year_columns: e.g. ["2025", "2024", "2025", "2024"]
    """
    period_headers: list[str] = []
    year_columns: list[str] = []

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        line_s = line.strip()

        # Match period headers — use findall to capture multiple on one line
        # e.g. "Three Months Ended June 30, Six Months Ended June 30,"
        matches = re.findall(
            r"((?:Three|Six|Nine|Twelve)\s+Months?\s+Ended\s+\w+\s+\d{1,2},?)",
            line_s,
            re.IGNORECASE,
        )
        if matches:
            period_headers.extend(matches)
            continue

        # Match "Year Ended" / "Period Ended" only on short standalone lines
        # (not embedded in a longer sentence like "for the year ended December 31, 2024")
        if len(line_s) < 60:
            m = re.match(
                r"^((?:Year|Period)\s+Ended\s+\w+\s+\d{1,2},?)\s*$",
                line_s,
                re.IGNORECASE,
            )
            if m:
                period_headers.append(m.group(1))
                continue

        # Match date headers like "June 30," / "December 31,"
        # Also handles multiple dates on one line: "September 27, September 28,"
        _MONTH = (
            r"(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December)"
        )
        date_matches = re.findall(
            _MONTH + r"\s+\d{1,2},?",
            line_s,
        )
        if date_matches and not period_headers and len(line_s) < 60:
            period_headers.extend(date_matches)
            continue

        # Match year line like "2025 2024" or "2025 2024 2025 2024"
        # Also handles lines with prefix text: "Note 2025 2024"
        year_match = re.match(r"^(\d{4}(?:\s+\d{4})+)\s*$", line_s)
        if year_match and not year_columns:
            year_columns = line_s.split()
        elif not year_columns:
            # Try to extract trailing years from lines like "Note 2025 2024"
            trailing = re.search(r"(\d{4}(?:\s+\d{4})+)\s*$", line_s)
            if trailing:
                candidate = trailing.group(1).split()
                # Only accept if all look like recent years and there are 2+
                if len(candidate) >= 2 and all(
                    1990 <= int(y) <= 2050 for y in candidate
                ):
                    year_columns = candidate

    return period_headers, year_columns


def _build_header_rows(
    period_headers: list[str],
    year_columns: list[str],
    col_count: int,
) -> list[list[str]]:
    """Build one or two header rows from detected period/year info."""
    rows: list[list[str]] = []
    data_cols = col_count - 1  # first column is the line-item label

    if period_headers and year_columns and len(year_columns) >= data_cols:
        yrs = year_columns[:data_cols]

        if len(period_headers) == 1:
            # Single period spanning all data columns — merge with years.
            # e.g. "June 30," + ["2025", "2024"] → ["June 30, 2025", "June 30, 2024"]
            merged = [""] + [f"{period_headers[0]} {y}" for y in yrs]
            rows.append(merged)
        elif len(period_headers) == data_cols:
            # One period per data column — merge 1-to-1.
            # e.g. ["September 27,", "September 28,"] + ["2025", "2024"]
            #   → ["September 27, 2025", "September 28, 2024"]
            merged = [""] + [f"{p} {y}" for p, y in zip(period_headers, yrs)]
            rows.append(merged)
        elif len(period_headers) * 2 == data_cols:
            # Two years per period (10-Q 4-column layout).
            # e.g. ["Three Months Ended Dec 31,", "Six Months Ended Dec 31,"]
            #   + ["2025", "2024", "2025", "2024"]
            merged = [""] + [
                f"{period_headers[i // 2]} {y}" for i, y in enumerate(yrs)
            ]
            rows.append(merged)
        else:
            # Fallback — keep two rows
            row1 = [""] + period_headers[:data_cols]
            while len(row1) < col_count:
                row1.append("")
            rows.append(row1)
            rows.append([""] + yrs)
    elif year_columns and len(year_columns) >= data_cols:
        rows.append([""] + year_columns[:data_cols])
    elif period_headers:
        row = [""] + period_headers[:data_cols]
        while len(row) < col_count:
            row.append("")
        rows.append(row)

    return rows


def _is_prose_table(table: list[list[str]]) -> bool:
    """Detect tables that are actually prose text split across columns.

    pdfplumber's text-based table strategy sometimes splits paragraph text into
    many columns, producing garbled multi-column "tables" where sentence
    fragments appear in each cell.  Real financial tables have many numeric
    cells; prose tables have almost none.

    Heuristics:
    1. Many columns (>6) — prose tends to get split into 8-16+ columns
    2. Low numeric ratio — financial tables are ~40-60% numeric; prose <15%
    3. Short average cell length with long joined rows — word fragments
    """
    if not table or len(table) < 2:
        return False

    # --- Hard cutoff: large tables with mostly non-numeric cells ---
    # Tables with >50 rows and >70% text cells are almost certainly prose
    # that pdfplumber split into columns. Reject before soft heuristics.
    if len(table) > 50:
        all_cells_hard = [(c or "").strip() for row in table for c in row if (c or "").strip()]
        if all_cells_hard:
            numeric_hard = sum(1 for c in all_cells_hard if _is_numeric(c) and len(c) < 30)
            if numeric_hard / len(all_cells_hard) < 0.30:
                return True

    max_cols = max(len(row) for row in table)
    if max_cols < 6:
        return False  # Financial tables commonly have 4-6 columns

    # Gather non-empty cells
    all_cells = [(c or "").strip() for row in table for c in row if (c or "").strip()]
    if len(all_cells) < 5:
        return False

    # Check numeric ratio
    numeric_count = sum(1 for c in all_cells if _is_numeric(c) and len(c) < 30)
    numeric_ratio = numeric_count / len(all_cells)
    if numeric_ratio > 0.15:
        return False  # Has substantial numeric data — likely a real table

    # Check if rows reconstruct readable prose (long joined text, short cells)
    avg_cell_len = sum(len(c) for c in all_cells) / len(all_cells)
    if avg_cell_len > 40:
        return False  # Cells are long enough to be real table content

    # Join a few data rows and check if they form prose-like text
    prose_rows = 0
    for row in table[:10]:
        joined = " ".join((c or "").strip() for c in row).strip()
        # Prose rows are long when joined and contain common English words
        if len(joined) > 60:
            # Count words (prose has many short common words)
            words = joined.split()
            if len(words) > 8:
                prose_rows += 1

    # If most sampled rows look like prose, reject this table
    sample_size = min(len(table), 10)
    if sample_size > 0 and prose_rows / sample_size >= 0.4:
        return True

    return False


def _is_numeric(cell: str) -> bool:
    """Check if a cell is numeric (including parenthetical negatives, dashes)."""
    cleaned = cell.replace("$", "").replace(",", "").replace(" ", "").strip()
    if cleaned in ("—", "-", "–", ""):
        return True
    cleaned = cleaned.strip("()")
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _render_markdown_table(
    header_rows: list[list[str]],
    data_rows: list[list[str]],
    col_count: int,
    left_cols: int = 1,
) -> str:
    """Render rows as a markdown table with proper alignment."""
    if col_count < 2:
        col_count = 2

    # Alignment: first left_cols columns left-aligned, rest right-aligned
    sep = [":---"] * left_cols + ["---:"] * (col_count - left_cols)

    lines: list[str] = []

    # Render header rows
    for i, header in enumerate(header_rows):
        padded = list(header)
        while len(padded) < col_count:
            padded.append("")
        padded = padded[:col_count]
        padded = [re.sub(r"\s+", " ", c.replace("\n", " ")).strip() for c in padded]
        lines.append("| " + " | ".join(padded) + " |")

    # If no headers were provided, add a blank header
    if not header_rows:
        lines.append("| " + " | ".join([""] * col_count) + " |")

    lines.append("| " + " | ".join(sep) + " |")

    for row in data_rows:
        padded = list(row)
        while len(padded) < col_count:
            padded.append("")
        padded = padded[:col_count]
        padded = [re.sub(r"\s+", " ", c.replace("\n", " ")).strip() for c in padded]
        lines.append("| " + " | ".join(padded) + " |")

    return "\n".join(lines)


def _strip_note_ref_columns(tables: list[list[list[str]]]) -> list[list[list[str]]]:
    """Remove Note reference columns from financial tables.

    Some filings include a column of small integers (1-30) or note references
    like "3", "8, 10", "14" between the line-item name and financial values.
    After collapse_row(), these appear as cells in some rows but not others
    (rows without note refs are shorter). Detect and strip them.

    Strategy: for rows longer than the dominant length, check if the extra cell
    at position 1 is a note ref. If enough rows have this pattern, strip it.
    """
    _NOTE_REF = re.compile(r"^\d{1,2}(?:\s*,\s*\d{1,2})*$")

    result = []
    for table in tables:
        if not table:
            result.append(table)
            continue

        # Find the two most common row lengths (excluding header/label-only rows)
        data_rows = [r for r in table if len(r) >= 2]
        if not data_rows:
            result.append(table)
            continue

        lengths = Counter(len(r) for r in data_rows)
        common_lengths = lengths.most_common(2)
        if len(common_lengths) < 2:
            # All rows same length — check column 1 directly
            col_count = common_lengths[0][0]
            if col_count < 3:
                result.append(table)
                continue
            # Check if column 1 is a note ref column
            note_cells = []
            for row in data_rows:
                cell = row[1].strip() if len(row) > 1 else ""
                if cell:
                    note_cells.append(cell)
            if note_cells:
                note_count = sum(1 for c in note_cells if _NOTE_REF.match(c))
                has_financial = any(
                    ("$" in c or ("," in c and len(c) > 3)) and not _NOTE_REF.match(c)
                    for c in note_cells
                )
                all_small = all(
                    _NOTE_REF.match(c) and all(int(x.strip()) <= 30 for x in c.split(","))
                    for c in note_cells if _NOTE_REF.match(c)
                )
                if note_count >= 3 and not has_financial and all_small:
                    stripped = [[c for i, c in enumerate(row) if i != 1] for row in table]
                    result.append(stripped)
                    continue
            result.append(table)
            continue

        # Two common lengths — the longer rows likely have a note ref column
        short_len, long_len = sorted([common_lengths[0][0], common_lengths[1][0]])
        if long_len - short_len != 1:
            result.append(table)
            continue

        # Check: in longer rows, is position 1 a note ref (small int)?
        note_ref_count = 0
        long_rows_with_data = 0
        for row in data_rows:
            if len(row) == long_len and len(row) >= 2:
                cell = row[1].strip()
                if cell:
                    long_rows_with_data += 1
                    if _NOTE_REF.match(cell):
                        # Verify it's a small number
                        try:
                            vals = [int(x.strip()) for x in cell.split(",")]
                            if all(v <= 30 for v in vals):
                                note_ref_count += 1
                        except ValueError:
                            pass

        if long_rows_with_data >= 2 and note_ref_count / long_rows_with_data >= 0.5:
            # Strip position 1 from longer rows to align with shorter rows
            stripped = []
            for row in table:
                if len(row) == long_len:
                    stripped.append([row[0]] + row[2:])
                else:
                    stripped.append(row)
            result.append(stripped)
        else:
            result.append(table)

    return result


def _recover_orphaned_text_rows(
    section_text: str,
    first_table: list[list[str]],
) -> list[list[str]]:
    """Recover financial data rows from section text not captured by pdfplumber.

    pdfplumber sometimes starts its table extraction after a leading data row
    (e.g. "Cash, cash equivalents, beginning balances $ 29,943 $ 30,737").
    This function finds such rows in the text before the first table row and
    returns them as split multi-column lists ready to prepend to the table.
    """
    if not first_table or not section_text:
        return []

    # Find the label of the first non-empty table row to locate where the
    # table starts in the raw text
    first_label = ""
    for row in first_table:
        cell = (row[0] if row else "").strip()
        if cell:
            first_label = cell
            break
    if not first_label:
        return []

    # For single-column tables, the label may include values concatenated
    # (e.g. "Operating activities:"); extract just the label part
    first_label_words = re.split(r"\s+\d", first_label)[0].strip().rstrip(":")

    text_lines = section_text.splitlines()

    # Find the line index in text where the first table row label appears
    table_start_idx = -1
    for idx, line in enumerate(text_lines):
        if first_label_words and first_label_words.lower() in line.lower():
            table_start_idx = idx
            break

    if table_start_idx <= 0:
        return []

    # Collect text lines before the table that contain financial values.
    # Join continuation lines: a line without values followed by a line with values.
    # Pattern: detect lines with $ + number patterns (actual financial data).
    _dollar_val = re.compile(r"\$\s*[\d,]+")

    orphaned: list[list[str]] = []
    i = 0
    while i < table_start_idx:
        line = text_lines[i].strip()
        # Skip headers, scale indicators, date headers, empty lines
        if not line or re.match(r"(?i)^\(?\s*in\s+(?:thousands|millions|billions)", line):
            i += 1
            continue
        # Skip title lines (all caps, short)
        if line.isupper() and len(line) < 80:
            i += 1
            continue
        # Skip standalone date/year header lines
        if re.match(r"^(?:Years?\s+ended|September|October|November|December|January|February|March|April|May|June|July|August)\s", line, re.IGNORECASE):
            i += 1
            continue
        if re.match(r"^\d{4}(?:\s+\d{4})*\s*$", line):
            i += 1
            continue

        # Check if this line has dollar values
        if _dollar_val.search(line):
            parsed = split_single_col_row(line)
            if len(parsed) >= 2:
                orphaned.append(parsed)
            i += 1
            continue

        # Check if next line has dollar values (continuation pattern)
        if i + 1 < table_start_idx:
            next_line = text_lines[i + 1].strip()
            if _dollar_val.search(next_line):
                joined = line + " " + next_line
                parsed = split_single_col_row(joined)
                if len(parsed) >= 2:
                    orphaned.append(parsed)
                i += 2
                continue

        i += 1

    return orphaned


# ---------------------------------------------------------------------------
# Text-based table parsing (for PDFs where pdfplumber tables lack row labels)
# ---------------------------------------------------------------------------

# Numeric token: digits with commas/periods, parenthesized negatives, or dashes
_TEXT_NUM_TOKEN = re.compile(r"\([\d,]+(?:\.\d+)?\)|[\d,]+(?:\.\d+)?|—|–")


def _parse_text_as_table(
    section_text: str,
    period_headers: list[str] | None = None,
    year_columns: list[str] | None = None,
) -> str | None:
    """Try to parse financial data from raw section text into a markdown table.

    Used when pdfplumber tables lack row labels (e.g. XOM where labels appear
    in the text overlay, not the table grid). Detects the dominant value column
    count, then for each data line extracts the rightmost N numeric tokens as
    values and everything before as the row label.

    Returns a markdown table string, or None if the text doesn't look tabular.
    """
    lines = section_text.splitlines()
    # Filter page numbers
    lines = [l for l in lines if not re.match(r"^\s*\d{1,3}\s*$", l)]

    # Count value tokens per line to detect the dominant column count
    val_counts: list[int] = []
    for line in lines:
        tokens = _TEXT_NUM_TOKEN.findall(line)
        # Filter small note refs (single/double digit integers)
        big_tokens = [t for t in tokens if len(t) > 2 or not t.isdigit()]
        val_counts.append(len(big_tokens))

    if not val_counts:
        return None

    count_freq = Counter(c for c in val_counts if c > 0)
    if not count_freq:
        return None

    expected_cols = count_freq.most_common(1)[0][0]
    if expected_cols < 1:
        return None

    # Need enough data lines to justify table rendering
    data_line_count = sum(1 for c in val_counts if c >= expected_cols)
    if data_line_count < 3:
        return None

    # Parse lines into header rows and data rows
    header_rows: list[list[str]] = []
    data_rows: list[list[str]] = []
    seen_data = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        matches = list(_TEXT_NUM_TOKEN.finditer(stripped))
        # Filter small note refs from matches
        big_matches = [m for m in matches if len(m.group()) > 2 or not m.group().isdigit()]

        if len(big_matches) >= expected_cols:
            seen_data = True
            value_matches = big_matches[-expected_cols:]
            label_end = value_matches[0].start()
            label = stripped[:label_end].rstrip()
            vals = [m.group() for m in value_matches]
            # Strip trailing note ref from label (single 1-2 digit number)
            label = re.sub(r"\s+\d{1,2}\s*$", "", label)
            if not label:
                label = "Total"
            data_rows.append([label] + vals)
        elif not seen_data:
            # Lines before first data row might be title/header — skip them
            # (we'll use period_headers/year_columns for the header)
            pass
        else:
            # Section sub-header within data (e.g. "Costs and other deductions")
            if stripped and len(stripped) < 80:
                data_rows.append([stripped] + [""] * expected_cols)

    if len(data_rows) < 3:
        return None

    # Build header from period_headers/year_columns or from detected years
    col_count = expected_cols + 1  # +1 for label column
    if not header_rows:
        if year_columns and len(year_columns) == expected_cols:
            header_rows = [[""] + year_columns]
        elif period_headers:
            header_rows = [[""] + period_headers[:expected_cols]]
        else:
            # Try to find year headers from the first few lines
            for line in section_text.splitlines()[:5]:
                year_matches = re.findall(r"\b(20\d{2})\b", line)
                if len(year_matches) == expected_cols:
                    header_rows = [[""] + year_matches]
                    break
            if not header_rows:
                header_rows = [[""] + [f"Col {i+1}" for i in range(expected_cols)]]

    return _render_markdown_table(header_rows, data_rows, col_count)


_FOOTER_RE = re.compile(
    r"^\s*.{3,50}\s*\|\s*\d{4}\s+Form\s+10-[KQ](?:/A)?\s*\|\s*\d{1,3}\s*$",
    re.IGNORECASE,
)
_PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}\s*$")
_FPAGE_RE = re.compile(r"^\s*F-\d{1,3}\s*$")
_SEE_NOTES_RE = re.compile(
    r"^\s*(?:See|The)\s+(?:accompanying\s+)?(?:Notes?\s+to|The\s+Notes)",
    re.IGNORECASE,
)
_FORM_FOOTER_RE = re.compile(
    r"^\s*\d{1,3}\s+.{3,40}\s+(?:Form\s+10-[KQ]|Annual\s+Report)",
    re.IGNORECASE,
)


def _clean_raw_text(text: str) -> str:
    """Clean raw section text when tables_to_markdown falls back to text.

    Strips standalone page numbers, page footers, F-N references,
    and boilerplate "See Notes" lines.
    """
    lines = text.splitlines()
    lines = [l for l in lines if not _PAGE_NUM_RE.match(l)]
    lines = [l for l in lines if not _FOOTER_RE.match(l)]
    lines = [l for l in lines if not _FPAGE_RE.match(l)]
    lines = [l for l in lines if not _SEE_NOTES_RE.match(l)]
    lines = [l for l in lines if not _FORM_FOOTER_RE.match(l)]
    return "\n".join(lines)


def tables_to_markdown(
    section_text: str,
    tables: list[list[list[str]]],
    taxonomy: dict | None = None,
    normalized_data_out: list | None = None,
) -> str:
    """Convert pdfplumber tables into clean markdown.

    - Collapses sparse rows (merging currency symbols and parenthetical negatives)
    - Detects column headers from section text
    - Merges multi-page table fragments with same column count
    - Renders aligned markdown tables with proper headers
    - When taxonomy is provided, normalizes line items and adds a Canonical column
    - When normalized_data_out is provided (a list), appends normalized rows to it
    """
    if not tables:
        return _clean_raw_text(section_text)

    # Filter out "tables" that are really just text paragraphs
    # (pdfplumber sometimes misidentifies prose as a table)
    filtered_tables: list[list[list[str]]] = []
    for table in tables:
        if not table:
            continue
        # Reject prose text that pdfplumber split into many columns
        if _is_prose_table(table):
            continue
        # Check if this looks like a text paragraph: few columns, mostly long
        # text cells, no numeric data
        all_cells = [
            (c or "").strip()
            for row in table
            for c in row
            if (c or "").strip()
        ]
        if all_cells:
            avg_len = sum(len(c) for c in all_cells) / len(all_cells)
            has_numeric = any(_is_numeric(c) for c in all_cells if len(c) < 30)
            max_cols = max(len(row) for row in table)
            if avg_len > 60 and not has_numeric and max_cols <= 3:
                continue  # skip — this is a text paragraph, not a data table
        filtered_tables.append(table)

    if not filtered_tables:
        return _clean_raw_text(section_text)

    # Collapse all rows, with position-aware handling for wide sparse tables
    # (e.g. stockholders' equity) where column alignment matters.
    collapsed_tables: list[list[list[str]]] = []
    for table in filtered_tables:
        collapsed = _collapse_table_positional(table)
        # Filter out completely empty rows
        collapsed = [r for r in collapsed if any(c.strip() for c in r)]
        if collapsed:
            collapsed_tables.append(collapsed)

    if not collapsed_tables:
        return section_text

    # Split single-column rows into multi-column data.
    # pdfplumber often returns financial tables as 1-column rows where all
    # values are concatenated (e.g. "Revenue $ 130,497 $ 60,922 $ 26,974").
    for ti, table in enumerate(collapsed_tables):
        lengths = Counter(len(r) for r in table)
        dominant_len = lengths.most_common(1)[0][0]
        if dominant_len <= 1:
            collapsed_tables[ti] = [split_single_col_row(r[0] if r else "") for r in table]

    # Recover financial data rows from section text that pdfplumber missed.
    # e.g. "Cash, cash equivalents, beginning balances $ 29,943 $ 30,737"
    # appearing in text before the first table row but not in any table.
    if collapsed_tables:
        orphaned = _recover_orphaned_text_rows(section_text, collapsed_tables[0])
        if orphaned:
            collapsed_tables[0] = orphaned + collapsed_tables[0]

    # Strip Note reference columns (small integers between label and financial data)
    collapsed_tables = _strip_note_ref_columns(collapsed_tables)

    # Fix 5A: Strip mid-table repeated headers (scale indicators only;
    # date rows are preserved — they may be column headers or data rows
    # like "Cash, beginning of period  January 26, 2025").
    _scale_re = re.compile(r"^\(?\s*in\s+(?:thousands|millions|billions)", re.IGNORECASE)
    _date_only_re = re.compile(
        r"^(?:"
        # Month Day, Year — e.g. "September 28, 2024"
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},?\s*(?:\d{4})?"
        r"|"
        # Standalone year(s) — e.g. "2024" or "2025 2024"
        r"\d{4}(?:\s+\d{4})*"
        r"|"
        # Period descriptions — e.g. "Three Months Ended June 30, 2025"
        r"(?:Three|Six|Nine|Twelve)\s+Months?\s+Ended\b.*"
        r"|"
        # Year/Period Ended — e.g. "Year Ended December 31, 2024"
        r"(?:Year|Period)\s+Ended\b.*"
        r"|"
        # Fiscal year labels — e.g. "Fiscal Year 2024"
        r"Fiscal\s+Year\s+\d{4}"
        r")\s*$",
        re.IGNORECASE,
    )
    for ti, table in enumerate(collapsed_tables):
        cleaned: list[list[str]] = []
        for ri, row in enumerate(table):
            non_empty = [c for c in row if c.strip()]
            if non_empty and all(not _is_numeric(c) for c in non_empty):
                joined = " ".join(non_empty)
                if _scale_re.match(joined):
                    continue  # skip scale indicator
                # Only strip date-only rows that appear mid-table (not first row)
                # and where every non-empty cell is just a date fragment
                if ri > 0 and all(_date_only_re.match(c.strip()) for c in non_empty):
                    continue  # skip repeated mid-table date header
            cleaned.append(row)
        collapsed_tables[ti] = cleaned

    # If tables lack meaningful row labels (e.g. IFRS PDFs where pdfplumber
    # captures numbers but labels are only in the text), fall back to section text.
    total_rows = 0
    labeled_rows = 0
    for table in collapsed_tables:
        for row in table:
            if not row:
                continue
            total_rows += 1
            # Check first two columns for labels (some tables have note refs in col 0)
            for col_idx in range(min(2, len(row))):
                cell = row[col_idx].strip()
                if cell and not _is_numeric(cell) and len(cell) > 3:
                    if not re.match(r"^(?:Q\d|FY)?\s*\d{4}$", cell):
                        labeled_rows += 1
                        break
    if total_rows > 0 and labeled_rows / total_rows < 0.2:
        return _clean_raw_text(section_text)

    # Strip standalone page number rows (single cell, 1-3 digit integer)
    for table in collapsed_tables:
        table[:] = [
            row for row in table
            if not (len(row) == 1 and re.match(r"^\s*\d{1,3}\s*$", row[0]))
        ]

    # Try to merge tables with matching column counts (multi-page continuations)
    merged: list[list[list[str]]] = []
    for table in collapsed_tables:
        if not table:
            continue
        # Determine dominant column count (most common row length)
        lengths = Counter(len(r) for r in table)
        dominant_len = lengths.most_common(1)[0][0]

        if merged:
            prev_lengths = Counter(len(r) for r in merged[-1])
            prev_dominant = prev_lengths.most_common(1)[0][0]
            if dominant_len == prev_dominant:
                # Check heuristics before merging
                first = table[0]
                filled = [c for c in first if c.strip()]
                is_title = len(filled) == 1 and not _is_numeric(filled[0])
                both_small = len(merged[-1]) < 15 and len(table) < 15

                if is_title or both_small:
                    merged.append(table)  # separate tables
                else:
                    # Multi-page continuation — merge
                    start = 1 if table[0] == merged[-1][0] else 0
                    merged[-1].extend(table[start:])
                continue
        merged.append(table)

    # Extract column headers from section text
    period_headers, year_columns = _extract_column_headers(section_text)

    parts: list[str] = []

    for table in merged:
        if not table:
            continue

        # Determine column count from the most common row length
        lengths = Counter(len(r) for r in table)
        col_count = lengths.most_common(1)[0][0]

        # Pad short data rows with "—" when they have a label + value but
        # fewer cells than expected (pdfplumber sometimes drops empty cells)
        for ri, row in enumerate(table):
            if len(row) < col_count and len(row) >= 2:
                has_label = not _is_numeric(row[0])
                has_value = any(_is_numeric(c) for c in row[1:])
                if has_label and has_value:
                    table[ri] = row + ["—"] * (col_count - len(row))

        # Check if the table's own first row serves as headers
        first_row = table[0]
        non_empty = [c for c in first_row if c.strip()]
        non_numeric_header = (
            len(non_empty) > 1
            and all(not _is_numeric(c) for c in non_empty if c.strip())
        )

        if non_numeric_header:
            # Table has its own headers (e.g. Level 1/2/3, As Reported/Adjusted)
            header_rows = [first_row]
            all_data_rows = table[1:]
            # Use header row to set column count if it has more columns
            if len(first_row) > col_count:
                col_count = len(first_row)

            # Check if the second row is a continuation header (e.g. years
            # below a date header like "December 31," / "2025  2024")
            if all_data_rows:
                second_row = all_data_rows[0]
                second_non_empty = [c for c in second_row if c.strip()]
                _year_re = re.compile(r"^\d{4}$")
                second_is_header = (
                    len(second_non_empty) >= 1
                    and all(not _is_numeric(c) or _year_re.match(c.strip()) for c in second_non_empty)
                    and any(_year_re.match(c.strip()) for c in second_non_empty)
                )
                if second_is_header:
                    # Merge: combine first and second header rows.
                    # For cells where the first row has a date fragment
                    # and the second has the year, join them.
                    merged_header = []
                    for ci in range(max(len(first_row), len(second_row))):
                        c1 = first_row[ci].strip() if ci < len(first_row) else ""
                        c2 = second_row[ci].strip() if ci < len(second_row) else ""
                        if c1 and c2:
                            merged_header.append(f"{c1} {c2}")
                        elif c2:
                            merged_header.append(c2)
                        else:
                            merged_header.append(c1)
                    header_rows = [merged_header]
                    all_data_rows = all_data_rows[1:]
        else:
            # Build header rows from detected text headers (periods/years)
            header_rows = _build_header_rows(period_headers, year_columns, col_count)
            all_data_rows = table

        # Normalize line items when taxonomy is provided
        left_cols = 1
        if taxonomy is not None:
            from .normalize import normalize_table_rows

            all_data_rows = normalize_table_rows(all_data_rows, taxonomy)
            if normalized_data_out is not None:
                normalized_data_out.extend(all_data_rows)
            col_count += 1
            left_cols = 2
            # Insert "Canonical" header at index 1 in header rows
            for hi, hrow in enumerate(header_rows):
                header_rows[hi] = [hrow[0], "Canonical"] + hrow[1:]

        md = _render_markdown_table(header_rows, all_data_rows, col_count, left_cols=left_cols)
        parts.append(md)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Notes fallback (when Gemini is unavailable)
# ---------------------------------------------------------------------------

def process_notes_fallback(
    section_text: str,
    tables: list[list[list[str]]],
) -> str:
    """Process Notes section without LLM — clean prose only.

    When Gemini is unavailable, the raw text already contains table data inline.
    Appending pdfplumber tables would duplicate content (the same data appears
    both as raw text and as fragmented pdfplumber tables). So we just clean the
    prose and return it — no table rendering.
    """
    return clean_prose(section_text)


# ---------------------------------------------------------------------------
# Prose cleanup
# ---------------------------------------------------------------------------

def clean_prose(section_text: str, tables: list[list[list[str]]] | None = None) -> str:
    """Clean up a prose section from PDF extraction artifacts.

    - Removes standalone page numbers
    - Removes repeated page headers
    - Fixes broken line breaks (mid-sentence splits)
    - Adds markdown headings for Item headers
    - Detects sub-headings (short title-case lines)
    - Renders embedded tables as markdown tables
    """
    # Render any pdfplumber tables as markdown and append after prose cleanup
    table_md = ""
    if tables:
        rendered = tables_to_markdown(section_text, tables)
        if "|" in rendered:
            table_md = rendered
    lines = section_text.splitlines()

    # Remove standalone page numbers
    lines = [l for l in lines if not re.match(r"^\s*\d{1,3}\s*$", l)]

    # Remove page footer patterns like "Apple Inc. | 2025 Form 10-K | 34"
    # or "Company Name | Year Form Type | PageNum"
    _footer_re = re.compile(
        r"^\s*.{3,50}\s*\|\s*\d{4}\s+Form\s+10-[KQ](?:/A)?\s*\|\s*\d{1,3}\s*$",
        re.IGNORECASE,
    )
    lines = [l for l in lines if not _footer_re.match(l)]

    # Remove "Table of Contents" running headers (standalone or with company suffix)
    lines = [l for l in lines if not re.match(
        r"^\s*(?:Financial\s+)?Table\s+of\s+Contents\b.*$", l, re.IGNORECASE
    )]

    # Remove standalone F-N page references
    lines = [l for l in lines if not re.match(r"^\s*F-\d{1,3}\s*$", l)]

    # Strip trailing F-N page references from prose lines (not table rows)
    lines = [
        re.sub(r"\s+F-\d{1,3}\.?\s*$", "", l) if not l.lstrip().startswith("|") else l
        for l in lines
    ]

    # Detect repeated page headers (lines appearing 3+ times)
    line_counts: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        if stripped:
            line_counts[stripped] += 1
    repeated = {text for text, count in line_counts.items() if count >= 3 and len(text) < 120}

    # Remove repeated headers
    lines = [l for l in lines if l.strip() not in repeated]

    # Rejoin lines and process
    result_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result_lines.append("")
            continue

        # Add markdown headings for Item headers
        item_match = re.match(r"^(Item\s+\d+[A-Za-z]?\.\s+.+)$", stripped, re.IGNORECASE)
        if item_match:
            result_lines.append(f"### {item_match.group(1)}")
            continue

        # Detect sub-headings: short title-case lines with most words capitalized
        # Must be short, not a sentence (no period at end unless abbreviation),
        # and have at least 2 words with most capitalized
        words = stripped.split()
        if (
            2 <= len(words) <= 10
            and len(stripped) < 80
            and not stripped.endswith((",", ";", ":", "and", "or"))
            and stripped[0].isupper()
            and not stripped.startswith(("(", "$", "•", "-", "*"))
            # Most words must start uppercase (excluding small connectors)
            and sum(1 for w in words if w[0].isupper()) / len(words) >= 0.6
            # Should not look like a regular sentence (no lowercase start after first word
            # continuing for many words)
            and not re.match(r"^[A-Z]\w+\s+[a-z].*[a-z]\s+[a-z]", stripped)
        ):
            result_lines.append(f"### {stripped}")
            continue

        result_lines.append(stripped)

    # Fix broken line breaks: rejoin lines split mid-sentence
    joined: list[str] = []
    for line in result_lines:
        if (
            joined
            and joined[-1]
            and not joined[-1].startswith("#")
            and not line.startswith(("#", "|", "-", "*", "•"))
            and line
            and line[0].islower()
        ):
            # Previous line was mid-sentence, join
            joined[-1] = joined[-1] + " " + line
        else:
            joined.append(line)

    text = "\n".join(joined)

    # Clean up excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    result = text.strip()

    # Append rendered tables if present
    if table_md:
        result = result + "\n\n" + table_md

    return result
