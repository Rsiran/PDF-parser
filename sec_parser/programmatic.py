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
        r"^(.+)\n\s*\((?:Exact|exact)\s+name\s+of\s+registrant",
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
    header_match = re.search(
        r"Title\s+of\s+Each\s+Class\s+Trading\s+Symbol",
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
            if not line_s or "exchange" in line_s.lower() or "registered" in line_s.lower():
                continue
            if line_s.lower().startswith("indicate"):
                break
            # Data line pattern: description ending with "par value [per share]",
            # "stock", "warrant", etc., then TICKER (2-5 uppercase letters),
            # then exchange name. Also handle "N/A" as no ticker.
            ticker_m = re.search(
                r"(?:par\s+value(?:\s+per\s+share)?|per\s+share|stock|warrant[s]?|unit[s]?|right[s]?|debenture[s]?|shares)\s+([A-Z]{2,5})\s",
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
            r"Trading\s+Symbol\(?s?\)?[:\s]+([A-Z]{2,5})\b",
            text,
            re.IGNORECASE,
        )
        if m and m.group(1).upper() not in ("NAME", "THE", "OF", "EACH"):
            fields.append(("Ticker", m.group(1).strip()))

    # Exchange
    m = re.search(
        r"(?:Name\s+of\s+.*exchange|registered)[:\s]*((?:NYSE|NASDAQ|New\s+York\s+Stock\s+Exchange)[^\n]*)",
        text,
        re.IGNORECASE,
    )
    if m:
        exchange = m.group(1).strip().rstrip(".")
        fields.append(("Exchange", exchange))

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

        # Standalone closing paren — already handled above, skip if leftover
        elif cell == ")":
            i += 1

        elif cell:
            merged.append(cell)
            i += 1
        else:
            i += 1

    return merged


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
        m = re.match(
            r"^(\w+\s+\d{1,2},?)$",
            line_s,
        )
        if m and not year_columns:
            # This might be a standalone date header for balance sheet
            period_headers.append(m.group(1))
            continue

        # Match year line like "2025 2024" or "2025 2024 2025 2024"
        year_match = re.match(r"^(\d{4}(?:\s+\d{4})+)\s*$", line_s)
        if year_match and not year_columns:
            year_columns = line_s.split()

    return period_headers, year_columns


def _build_header_rows(
    period_headers: list[str],
    year_columns: list[str],
    col_count: int,
) -> list[list[str]]:
    """Build one or two header rows from detected period/year info."""
    rows: list[list[str]] = []

    if period_headers and year_columns and len(year_columns) >= col_count - 1:
        # Two-row header: periods spanning columns, then years
        # e.g. ["", "Three Months Ended June 30,", "", "Six Months Ended June 30,", ""]
        if len(period_headers) >= 2 and col_count == 5:
            # 4-data-column layout: 2 periods × 2 years each
            row1 = ["", period_headers[0], "", period_headers[1], ""]
            rows.append(row1)
        elif len(period_headers) == 1 and col_count == 3:
            row1 = ["", period_headers[0], ""]
            rows.append(row1)

        row2 = [""] + year_columns[: col_count - 1]
        rows.append(row2)
    elif year_columns and len(year_columns) >= col_count - 1:
        rows.append([""] + year_columns[: col_count - 1])
    elif period_headers:
        row = [""] + period_headers[: col_count - 1]
        while len(row) < col_count:
            row.append("")
        rows.append(row)

    return rows


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
        lines.append("| " + " | ".join(padded) + " |")

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
        return section_text  # no tables, return raw text

    # Filter out "tables" that are really just text paragraphs
    # (pdfplumber sometimes misidentifies prose as a table)
    filtered_tables: list[list[list[str]]] = []
    for table in tables:
        if not table:
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
        return section_text

    # Collapse all rows
    collapsed_tables: list[list[list[str]]] = []
    for table in filtered_tables:
        collapsed = [collapse_row(row) for row in table]
        # Filter out completely empty rows
        collapsed = [r for r in collapsed if any(c.strip() for c in r)]
        if collapsed:
            collapsed_tables.append(collapsed)

    if not collapsed_tables:
        return section_text

    # If tables lack meaningful row labels (e.g. IFRS PDFs where pdfplumber
    # captures numbers but labels are only in the text), fall back to section text.
    total_rows = 0
    labeled_rows = 0
    for table in collapsed_tables:
        for row in table:
            if not row:
                continue
            total_rows += 1
            first = row[0].strip()
            if first and not _is_numeric(first) and len(first) > 3:
                if not re.match(r"^(?:Q\d|FY)?\s*\d{4}$", first):
                    labeled_rows += 1
    if total_rows > 0 and labeled_rows / total_rows < 0.2:
        return section_text

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
                # Skip header row of continuation if it looks like the first table's header
                start = 0
                if table[0] == merged[-1][0]:
                    start = 1
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

        # Check if first row looks like a section label (single non-numeric cell)
        # rather than data — use it as the first data row, not header
        first_row = table[0]
        all_data_rows = table

        # Build header rows from detected text headers
        header_rows = _build_header_rows(period_headers, year_columns, col_count)

        # If first row is a label-only row (e.g. "Revenue"), keep it as data
        # If first row looks like column headers, use it instead
        if not header_rows:
            # Check if first row has mostly non-numeric content (could be headers)
            non_empty = [c for c in first_row if c.strip()]
            if len(non_empty) > 1 and all(not _is_numeric(c) for c in non_empty if c.strip()):
                header_rows = [first_row]
                all_data_rows = table[1:]

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
# Prose cleanup
# ---------------------------------------------------------------------------

def clean_prose(section_text: str, tables: list[list[list[str]]] | None = None) -> str:
    """Clean up a prose section from PDF extraction artifacts.

    - Removes standalone page numbers
    - Removes repeated page headers
    - Fixes broken line breaks (mid-sentence splits)
    - Adds markdown headings for Item headers
    - Detects sub-headings (short title-case lines)
    - Converts embedded tables to markdown
    """
    lines = section_text.splitlines()

    # Remove standalone page numbers
    lines = [l for l in lines if not re.match(r"^\s*\d{1,3}\s*$", l)]

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
            result_lines.append(f"## {item_match.group(1)}")
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

    return text.strip()
