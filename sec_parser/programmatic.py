"""Programmatic parsers for SEC filing sections — no LLM needed."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pdf_extract import PageData

_MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}
_MONTH_RE = '|'.join(_MONTH_NAMES)


# ---------------------------------------------------------------------------
# Cover Page
# ---------------------------------------------------------------------------

def parse_cover_page(text: str) -> str:
    """Extract cover page metadata via regex and return structured markdown."""
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
        if not re.match(r"Commission|File\s+Number|\d+-\d+", name, re.IGNORECASE):
            fields.append(("Company", name))

    # Period of report
    m = re.search(
        r"(?:(?:quarterly|annual)\s+period\s+ended|period\s+of\s+report)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        fields.append(("Period Ended", m.group(1).strip()))

    # Commission File Number
    m = re.search(r"Commission\s+File\s+Number[:\s]+([\d-]+)", text, re.IGNORECASE)
    if m:
        fields.append(("Commission File Number", m.group(1).strip()))

    # State of incorporation — line before "(State or other jurisdiction ...)"
    m = re.search(
        r"^(.+)\n\s*\(State\s+or\s+other\s+jurisdiction",
        text,
        re.MULTILINE,
    )
    if m:
        state = m.group(1).strip()
        if len(state) < 50:
            fields.append(("State of Incorporation", state))

    # IRS Employer ID — line before "(I.R.S. Employer"
    m = re.search(
        r"^([\d-]+)\n\s*\(I\.?R\.?S\.?\s+Employer",
        text,
        re.MULTILINE,
    )
    if m:
        fields.append(("IRS Employer ID", m.group(1).strip()))

    # Address — line before "(Address of Principal Executive Offices)"
    m = re.search(
        r"^(.+)\n\s*\(Address\s+of\s+Principal",
        text,
        re.MULTILINE,
    )
    if m:
        addr = m.group(1).strip()
        # Check next lines for zip code
        m2 = re.search(
            r"\(Address\s+of\s+Principal[^\n]*\n\s*(\d{5}(?:-\d{4})?)",
            text,
            re.IGNORECASE,
        )
        if m2:
            addr += " " + m2.group(1).strip()
        fields.append(("Address", addr))

    # Phone number — line before "(Registrant's telephone number ...)"
    m = re.search(
        r"^(.+)\n\s*\(Registrant.s\s+telephone",
        text,
        re.MULTILINE,
    )
    if m:
        phone = m.group(1).strip()
        if re.search(r"\d", phone):
            fields.append(("Phone", phone))

    # Filer status (checkboxes)
    filer_statuses = []
    if re.search(r"Non-accelerated\s+filer\s+[☒x✓]", text, re.IGNORECASE):
        filer_statuses.append("Non-accelerated filer")
    elif re.search(r"Accelerated\s+filer\s+[☒x✓]", text, re.IGNORECASE):
        filer_statuses.append("Accelerated filer")
    elif re.search(r"Large\s+accelerated\s+filer\s+[☒x✓]", text, re.IGNORECASE):
        filer_statuses.append("Large accelerated filer")
    if re.search(r"Smaller\s+reporting\s+company\s+[☒x✓]", text, re.IGNORECASE):
        filer_statuses.append("Smaller reporting company")
    if re.search(r"Emerging\s+growth\s+company\s+[☒x✓]", text, re.IGNORECASE):
        filer_statuses.append("Emerging growth company")
    if filer_statuses:
        fields.append(("Filer Status", ", ".join(filer_statuses)))

    if not fields:
        return text

    parts: list[str] = []
    parts.append("| Field | Value |")
    parts.append("|-------|-------|")
    for label, value in fields:
        parts.append(f"| {label} | {value} |")

    # Securities registered table
    # Format: "Class A common stock, $0.001 par value per share ASST The Nasdaq Stock Market LLC"
    # Split at ticker (all-caps 2-5 letter word after "per share")
    sec_lines = re.findall(
        r"^(.+\$[\d.]+\s+par\s+value\s+per\s+share)\s+([A-Z]{2,5})\s+(.*(?:NYSE|Nasdaq|Stock\s+Market)[^\n]*)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    if sec_lines:
        parts.append("")
        parts.append("### Securities Registered (Section 12(b))")
        parts.append("")
        parts.append("| Title | Trading Symbol | Exchange |")
        parts.append("|-------|---------------|----------|")
        for title, symbol, exchange in sec_lines:
            parts.append(f"| {title.strip()} | {symbol.strip()} | {exchange.strip()} |")

    # Shares outstanding — parse "had X and Y shares of Class A ... and Class B ... outstanding"
    shares_match = re.search(
        r"(?:had|outstanding[,:]?)\s+([\d,]+)\s+and\s+([\d,]+)\s+shares\s+of\s+(Class\s+\w+)\s+common\s+stock\s+and\s+(Class\s+\w+)\s+common\s+stock\s+outstanding",
        text,
        re.IGNORECASE,
    )
    if not shares_match:
        # Try simpler pattern: "X shares of Class A ... and Y shares of Class B ..."
        shares_match = re.search(
            r"([\d,]+).*?shares\s+of\s+(Class\s+\w+)\s+common\s+stock.*?([\d,]+).*?shares\s+of\s+(Class\s+\w+)\s+common\s+stock",
            text,
            re.IGNORECASE | re.DOTALL,
        )
    as_of_match = re.search(r"As\s+of\s+(\w+\s+\d{1,2},?\s+\d{4})", text, re.IGNORECASE)
    as_of_date = as_of_match.group(1) if as_of_match else ""

    if shares_match:
        parts.append("")
        parts.append("### Shares Outstanding")
        parts.append("")
        parts.append("| Class | Shares Outstanding | As of Date |")
        parts.append("|-------|-------------------|------------|")
        g = shares_match.groups()
        if len(g) == 4 and g[2].replace(",", "").isdigit():
            # Pattern: count1, class1, count2, class2
            parts.append(f"| {g[1]} common stock | {g[0]} | {as_of_date} |")
            parts.append(f"| {g[3]} common stock | {g[2]} | {as_of_date} |")
        elif len(g) == 4:
            # Pattern: count1, count2, class1, class2
            parts.append(f"| {g[2]} common stock | {g[0]} | {as_of_date} |")
            parts.append(f"| {g[3]} common stock | {g[1]} | {as_of_date} |")

    return "\n".join(parts)


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


@dataclass
class _HeaderBlock:
    """A block of column header information parsed from section text."""
    columns: list[str]  # one label per data column (e.g. 3 labels for 3 data cols)
    metadata: str = ""  # e.g. "(in thousands, except share and per share data)"
    subtitle: str = ""  # e.g. "(Quarterly)" or "(Year-to-Date)"


def _parse_header_blocks(text: str) -> list[_HeaderBlock]:
    """Parse column header blocks from financial statement section text.

    Handles:
    - Predecessor/Successor with "Period from X to Y" ranges
    - Standard "Three Months Ended June 30," + "2025  2024" year rows
    - Balance sheet date columns: "September 30, 2025  December 31, 2024"
    - Multiple header blocks (quarterly + YTD on separate pages)
    """
    blocks: list[_HeaderBlock] = []
    lines = text.splitlines()
    i = 0

    # Detect metadata line (appears near the top)
    metadata = ""
    for line in lines[:10]:
        ls = line.strip()
        if re.match(r"^\(in\s+thousands", ls, re.IGNORECASE):
            metadata = ls
            break

    while i < len(lines):
        ls = lines[i].strip()

        # --- Pattern 1: Predecessor/Successor header block ---
        # "Successor Predecessor" or "Successor  Predecessor" on one line
        if re.match(r"^Successor\s+Predecessor$", ls, re.IGNORECASE):
            # Next 1-2 lines contain the period descriptions in column layout.
            # Collect them as separate lines (not merged) for column-aware parsing.
            period_lines: list[str] = []
            j = i + 1
            while j < len(lines) and j < i + 4:
                next_ls = lines[j].strip()
                if not next_ls:
                    j += 1
                    continue
                if re.match(r"^(?:Revenues|Revenue|Cash flows|Assets|Net (?:loss|income))", next_ls, re.IGNORECASE):
                    break
                period_lines.append(next_ls)
                j += 1

            columns = _parse_predecessor_successor_columns(period_lines)
            if columns:
                subtitle = _classify_period_block(columns)
                blocks.append(_HeaderBlock(columns=columns, metadata=metadata, subtitle=subtitle))
            i = j
            continue

        # --- Pattern 2: Balance sheet dates on one line ---
        # "September 30, 2025 December 31, 2024"
        bs_match = re.match(
            r"^(\w+\s+\d{1,2},\s*\d{4})\s+(\w+\s+\d{1,2},\s*\d{4})$",
            ls,
        )
        if bs_match:
            col1 = bs_match.group(1)
            col2 = bs_match.group(2)
            # Check if next lines have entity labels like "(Successor) (Predecessor)"
            entity1, entity2 = "", ""
            if i + 1 < len(lines):
                next_ls = lines[i + 1].strip()
                ent_match = re.match(r"^\((\w+)\)\s+\((\w+)\)$", next_ls)
                if ent_match:
                    entity1 = ent_match.group(1)
                    entity2 = ent_match.group(2)
                    i += 1
            # Check for (unaudited) (audited) labels
            audit1, audit2 = "", ""
            if i + 1 < len(lines):
                next_ls = lines[i + 1].strip()
                aud_match = re.match(r"^\((\w+)\)\s+\((\w+)\)$", next_ls)
                if aud_match:
                    audit1 = aud_match.group(1)
                    audit2 = aud_match.group(2)
                    i += 1

            label1 = col1
            if entity1:
                label1 += f" ({entity1}"
                if audit1:
                    label1 += f", {audit1})"
                else:
                    label1 += ")"
            elif audit1:
                label1 += f" ({audit1})"

            label2 = col2
            if entity2:
                label2 += f" ({entity2}"
                if audit2:
                    label2 += f", {audit2})"
                else:
                    label2 += ")"
            elif audit2:
                label2 += f" ({audit2})"

            blocks.append(_HeaderBlock(columns=[label1, label2], metadata=metadata))
            i += 1
            continue

        # --- Pattern 3: Standard period headers ---
        # "Three Months Ended June 30,   Six Months Ended June 30,"
        std_matches = re.findall(
            r"((?:Three|Six|Nine|Twelve)\s+Months?\s+Ended\s+\w+\s+\d{1,2},?)",
            ls,
            re.IGNORECASE,
        )
        if std_matches:
            # Check next line for years: "2025  2024  2025  2024"
            year_cols: list[str] = []
            if i + 1 < len(lines):
                next_ls = lines[i + 1].strip()
                year_match = re.match(r"^(\d{4}(?:\s+\d{4})+)\s*$", next_ls)
                if year_match:
                    year_cols = next_ls.split()
                    i += 1

            if year_cols:
                # Build column headers: pair periods with years
                columns = []
                if len(std_matches) == 2 and len(year_cols) == 4:
                    columns = [
                        f"{std_matches[0]} {year_cols[0]}",
                        f"{std_matches[0]} {year_cols[1]}",
                        f"{std_matches[1]} {year_cols[2]}",
                        f"{std_matches[1]} {year_cols[3]}",
                    ]
                elif len(std_matches) == 1 and len(year_cols) == 2:
                    columns = [
                        f"{std_matches[0]} {year_cols[0]}",
                        f"{std_matches[0]} {year_cols[1]}",
                    ]
                else:
                    columns = [f"{std_matches[0]} {y}" for y in year_cols]
                blocks.append(_HeaderBlock(columns=columns, metadata=metadata))
            else:
                blocks.append(_HeaderBlock(columns=std_matches, metadata=metadata))
            i += 1
            continue

        i += 1

    return blocks


def _parse_predecessor_successor_periods(period_text: str) -> list[str]:
    """Parse period descriptions from Predecessor/Successor header text.

    Handles mangled multi-line text where dates are split across lines.
    Uses marker-based splitting: "Period from" and "N Months Ended" delimit columns.

    Input (after line merging): "Period from September 12, Period from July 1, 2025 to Three Months Ended 2025 to September 30, 2025 September 11, 2025 September 30, 2024"
    Output: ["Successor: September 12, 2025 to September 30, 2025", "Predecessor: July 1, 2025 to September 11, 2025", "Predecessor: Three Months Ended September 30, 2024"]
    """
    # Split at period markers to get raw segments
    marker_pat = re.compile(
        r"(Period\s+from\s+|(?:Three|Six|Nine|Twelve)\s+Months?\s+Ended\s+)",
        re.IGNORECASE,
    )
    parts = marker_pat.split(period_text)
    # parts alternates: [before, marker1, content1, marker2, content2, ...]

    segments: list[str] = []
    i = 1  # skip anything before the first marker
    while i < len(parts) - 1:
        marker = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        segments.append(f"{marker} {content}")
        i += 2

    if not segments:
        return []

    # Now extract dates from each segment.
    # Each segment looks like "Period from September 12, ... to September 30, 2025 ..."
    # The challenge is that dates might run into the next segment's leftovers.
    # Strategy: find all dates (Month Day, Year) in the entire text, then assign them.
    all_dates = list(re.finditer(
        r"(\w+)\s+(\d{1,2}),?\s*(\d{4})",
        period_text,
    ))

    columns: list[str] = []
    date_idx = 0

    for seg in segments:
        seg_lower = seg.lower()

        if seg_lower.startswith("period from"):
            # Needs two dates: start and end
            if date_idx + 1 < len(all_dates):
                d1 = all_dates[date_idx]
                d2 = all_dates[date_idx + 1]
                start_date = f"{d1.group(1)} {d1.group(2)}, {d1.group(3)}"
                end_date = f"{d2.group(1)} {d2.group(2)}, {d2.group(3)}"
                columns.append(f"{start_date} to {end_date}")
                date_idx += 2
            else:
                columns.append(seg)
        else:
            # "Three Months Ended" etc. — needs one date
            if date_idx < len(all_dates):
                d = all_dates[date_idx]
                period_label = re.match(
                    r"((?:Three|Six|Nine|Twelve)\s+Months?\s+Ended)",
                    seg,
                    re.IGNORECASE,
                ).group(1) if re.match(r"(?:Three|Six|Nine|Twelve)", seg, re.IGNORECASE) else seg.split()[0]
                date_str = f"{d.group(1)} {d.group(2)}, {d.group(3)}"
                columns.append(f"{period_label} {date_str}")
                date_idx += 1
            else:
                columns.append(seg)

    # Label: first is Successor, rest are Predecessor
    labeled: list[str] = []
    for idx, col in enumerate(columns):
        entity = "Successor" if idx == 0 else "Predecessor"
        labeled.append(f"{entity}: {col}")

    return labeled


def _parse_predecessor_successor_columns(period_lines: list[str]) -> list[str]:
    """Parse Predecessor/Successor period columns from pdfplumber text lines.

    pdfplumber reads multi-column headers left-to-right per line, interleaving
    column data.  We extract markers and dates, then use chronological ordering
    to reconstruct the correct column assignments.

    Example input (two lines):
        "Period from September 12, Period from July 1, 2025 to Three Months Ended"
        "2025 to September 30, 2025 September 11, 2025 September 30, 2024"
    Output:
        ["Successor: September 12, 2025 to September 30, 2025",
         "Predecessor: July 1, 2025 to September 11, 2025",
         "Predecessor: Three Months Ended September 30, 2024"]
    """
    if not period_lines:
        return []

    combined = " ".join(period_lines)

    # --- 1. Find column markers ---
    marker_pat = re.compile(
        r"(Period\s+from|(?:Three|Six|Nine|Twelve)\s+Months?\s+Ended)",
        re.IGNORECASE,
    )
    markers = [m.group(1) for m in marker_pat.finditer(combined)]
    if not markers:
        return []

    # --- 2. Collect all dates ---
    date_full_pat = re.compile(
        rf"({_MONTH_RE})\s+(\d{{1,2}}),?\s*(\d{{4}})", re.IGNORECASE
    )
    dates: list[tuple[str, int, int, int]] = []  # (month, day, year, pos)
    used: set[int] = set()

    for m in date_full_pat.finditer(combined):
        dates.append((m.group(1), int(m.group(2)), int(m.group(3)), m.start()))
        used.update(range(m.start(), m.end()))

    # Incomplete dates (Month Day, no year) — pair with nearest standalone year
    partial_pat = re.compile(rf"({_MONTH_RE})\s+(\d{{1,2}}),", re.IGNORECASE)
    for m in partial_pat.finditer(combined):
        if m.start() not in used:
            best_year, best_dist = None, float("inf")
            for ym in re.finditer(r"\b(\d{4})\b", combined):
                if ym.start() not in used:
                    yr = int(ym.group(1))
                    if 2020 <= yr <= 2030:
                        dist = abs(ym.start() - m.end())
                        if dist < best_dist:
                            best_dist = dist
                            best_year = yr
            if best_year is not None:
                dates.append((m.group(1), int(m.group(2)), best_year, m.start()))

    # --- 3. Sort chronologically ---
    def _date_key(d: tuple) -> tuple:
        return (d[2], _MONTH_NAMES.get(d[0].lower(), 0), d[1])

    chrono = sorted(dates, key=_date_key)

    pf_count = sum(1 for mk in markers if mk.lower().startswith("period from"))
    me_count = len(markers) - pf_count
    needed = pf_count * 2 + me_count

    if len(chrono) < needed:
        return []

    # --- 4. Assign dates to columns ---
    # "Months Ended" columns take the oldest dates (prior-year comparisons)
    me_dates = chrono[:me_count]
    pf_dates = chrono[me_count:]

    # "Period from" ranges: consecutive pairs of remaining dates
    pf_columns: list[tuple[str, tuple]] = []
    for i in range(0, min(len(pf_dates) - 1, pf_count * 2 - 1), 2):
        d1, d2 = pf_dates[i], pf_dates[i + 1]
        label = f"{d1[0]} {d1[1]}, {d1[2]} to {d2[0]} {d2[1]}, {d2[2]}"
        pf_columns.append((label, _date_key(d2)))

    # Most recent end-date first = Successor
    pf_columns.sort(key=lambda x: x[1], reverse=True)

    # "Months Ended" columns
    me_columns: list[str] = []
    me_i = 0
    for mk in markers:
        if not mk.lower().startswith("period from") and me_i < len(me_dates):
            d = me_dates[me_i]
            me_columns.append(f"{mk} {d[0]} {d[1]}, {d[2]}")
            me_i += 1

    # --- 5. Label: first = Successor, rest = Predecessor ---
    all_cols = [c[0] for c in pf_columns] + me_columns
    return [
        f"{'Successor' if i == 0 else 'Predecessor'}: {col}"
        for i, col in enumerate(all_cols)
    ]


def _parse_equity_headers(text: str) -> list[str]:
    """Parse multi-row equity statement column headers from section text.

    The equity statement header spans 3 text rows like:
      Row 1: "Predecessor Predecessor Class A ... Successor Class B Additional Earnings/ Total"
      Row 2: "Preferred Stock Common Stock ... Paid-in (Accumulated Stockholders'"
      Row 3: "Shares Amount Shares Par Value ... Capital Deficit) Equity"

    We flatten these into column names like:
      ["Pref. Stock Shares", "Pref. Stock Amount", "Class A Shares", ...]
    """
    lines = text.splitlines()

    # Find the "Shares Amount Shares Par Value ..." row (bottom header row)
    bottom_idx = None
    for i, line in enumerate(lines[:15]):
        if re.match(r"^\s*Shares\s+Amount\s+Shares\s+Par\s+Value", line.strip()):
            bottom_idx = i
            break

    if bottom_idx is None or bottom_idx < 2:
        return []

    # The 3 header rows
    row3 = lines[bottom_idx].strip()      # "Shares Amount Shares Par Value ..."
    row2 = lines[bottom_idx - 1].strip()  # "Preferred Stock Common Stock ..."
    row1 = lines[bottom_idx - 2].strip()  # "Predecessor ... Successor ... Additional ..."

    # Parse row3 to get sub-column labels
    sub_labels = row3.split()
    # Expected pattern: Shares Amount (Shares ParValue)+ Capital Deficit) Equity
    # Rebuild: pair "Par" + "Value" into single token
    merged_subs: list[str] = []
    i = 0
    while i < len(sub_labels):
        if sub_labels[i] == "Par" and i + 1 < len(sub_labels) and sub_labels[i + 1] == "Value":
            merged_subs.append("Par Value")
            i += 2
        else:
            merged_subs.append(sub_labels[i])
            i += 1

    # Parse the group names from row2
    # Groups: "Preferred Stock", "Common Stock" (repeated), "Paid-in", "(Accumulated", "Stockholders'"
    # Each "Stock" group has 2 sub-columns (Shares + Amount/Par Value)
    # The tail columns are singles

    # Build column names by matching groups to sub-column pairs
    # The standard equity structure for this filing:
    columns: list[str] = []

    # Count how many (Shares, Amount/Par Value) pairs there are
    pair_count = 0
    for s in merged_subs:
        if s in ("Shares", "Amount", "Par Value"):
            pair_count += 1
    stock_groups = pair_count // 2  # Each stock group has Shares + Amount/Par Value

    # Extract group qualifiers from row1 (Predecessor/Successor labels)
    # and group names from row2 (Preferred Stock / Common Stock)
    group_labels = re.findall(
        r"((?:Predecessor|Successor)\s+(?:Class\s+[A-Z]\s+)?|Additional|Retained|Total)",
        row1,
        re.IGNORECASE,
    )

    # Known structure for Strive-type equity: 5 stock groups + 3 tail columns
    stock_names = []
    if "Preferred Stock" in row2:
        stock_names.append("Pref. Stock")
    for m in re.finditer(r"(Class\s+[A-Z])\s*", row1, re.IGNORECASE):
        # Check if preceded by Predecessor or Successor
        prefix = ""
        before = row1[:m.start()].rstrip()
        if before.endswith("Predecessor"):
            prefix = "Pred. "
        elif before.endswith("Successor"):
            prefix = "Succ. "
        stock_names.append(f"{prefix}{m.group(1)}")

    # Build paired columns
    sub_idx = 0
    for gi, name in enumerate(stock_names):
        if sub_idx < len(merged_subs):
            columns.append(f"{name} {merged_subs[sub_idx]}")
            sub_idx += 1
        if sub_idx < len(merged_subs):
            columns.append(f"{name} {merged_subs[sub_idx]}")
            sub_idx += 1

    # Remaining sub-labels are tail columns
    tail_names = ["APIC", "Retained Earnings / (Accum. Deficit)", "Total Equity"]
    tail_idx = 0
    while sub_idx < len(merged_subs) and tail_idx < len(tail_names):
        columns.append(tail_names[tail_idx])
        sub_idx += 1
        tail_idx += 1

    return columns


def _classify_period_block(columns: list[str]) -> str:
    """Classify a header block as Quarterly or Year-to-Date based on period descriptions."""
    for col in columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in ["nine months", "six months", "twelve months",
                                           "year ended", "january", "february"]):
            # YTD indicators: multi-month period starting from January, or "Nine Months"
            if "january" in col_lower or "nine months" in col_lower or "six months" in col_lower:
                return "(Year-to-Date)"
    # Default: if periods contain "three months" or short date ranges, it's quarterly
    for col in columns:
        if "three months" in col.lower():
            return "(Quarterly)"
    # For Predecessor/Successor: check if any period spans many months
    for col in columns:
        m = re.search(r"January|February|March", col, re.IGNORECASE)
        if m:
            return "(Year-to-Date)"
    return ""


def _build_header_rows(
    header_block: _HeaderBlock | None,
    col_count: int,
) -> list[list[str]]:
    """Build header rows from a parsed header block."""
    if not header_block or not header_block.columns:
        return []

    columns = header_block.columns
    # Trim to fit available data columns (col_count - 1 for the label column)
    data_cols = col_count - 1
    if len(columns) > data_cols:
        columns = columns[:data_cols]

    row = [""] + columns
    while len(row) < col_count:
        row.append("")

    return [row]


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
) -> str:
    """Render rows as a markdown table with proper alignment."""
    if col_count < 2:
        col_count = 2

    # Alignment: first column left-aligned, rest right-aligned
    sep = [":---"] + ["---:"] * (col_count - 1)

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


def _filter_text_tables(tables: list[list[list[str]]]) -> list[list[list[str]]]:
    """Filter out pdfplumber 'tables' that are really just text paragraphs."""
    filtered: list[list[list[str]]] = []
    for table in tables:
        if not table:
            continue
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
                continue
        filtered.append(table)
    return filtered


def tables_to_markdown(
    section_text: str,
    tables: list[list[list[str]]],
    section_name: str = "",
) -> str:
    """Convert pdfplumber tables into clean markdown.

    - Collapses sparse rows (merging currency symbols and parenthetical negatives)
    - Detects column headers from section text (including Predecessor/Successor)
    - Keeps distinct tables separate (quarterly vs YTD) with subtitles
    - Merges only multi-page continuations (same col count + appears consecutive)
    - Renders aligned markdown tables with proper headers
    """
    if not tables:
        return section_text  # no tables, return raw text

    # Strip standalone page numbers from section text before header parsing
    section_text = "\n".join(
        l for l in section_text.splitlines()
        if not re.match(r"^\s*\d{1,3}\s*$", l)
    )

    filtered_tables = _filter_text_tables(tables)
    if not filtered_tables:
        return section_text

    # Collapse all rows
    collapsed_tables: list[list[list[str]]] = []
    for table in filtered_tables:
        collapsed = [collapse_row(row) for row in table]
        collapsed = [r for r in collapsed if any(c.strip() for c in r)]
        if collapsed:
            collapsed_tables.append(collapsed)

    if not collapsed_tables:
        return section_text

    # If tables lack meaningful row labels (e.g. IFRS PDFs where pdfplumber
    # captures numbers but labels are only in the text), fall back to section text.
    # Heuristic: if fewer than 20% of data rows have a non-numeric first cell
    # that looks like a label (>3 chars, not a date/year), the table is unlabeled.
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

    # Parse header blocks from section text
    header_blocks = _parse_header_blocks(section_text)

    # Special case: stockholders' equity has multi-row spanning headers
    # that need to be parsed differently (flattened from 3 text rows)
    if section_name == "stockholders_equity" and not header_blocks:
        eq_cols = _parse_equity_headers(section_text)
        if eq_cols:
            metadata = ""
            for line in section_text.splitlines()[:5]:
                if re.match(r"^\(in\s+thousands", line.strip(), re.IGNORECASE):
                    metadata = line.strip()
                    break
            header_blocks = [_HeaderBlock(columns=eq_cols, metadata=metadata)]

    # Determine if we should keep tables separate (distinct statements)
    # or merge them (multi-page continuations).
    # If we have N header blocks and N tables with same col count, they're
    # separate statements (e.g. quarterly + YTD).
    # If col counts differ, they're truly different tables.
    col_counts = []
    for table in collapsed_tables:
        lengths = Counter(len(r) for r in table)
        col_counts.append(lengths.most_common(1)[0][0])

    # Group tables: merge consecutive tables with same col count ONLY if
    # we don't have matching header blocks for each
    if len(header_blocks) >= len(collapsed_tables):
        # Each table gets its own header block — keep separate
        merged = collapsed_tables
    else:
        # Merge multi-page continuations
        merged: list[list[list[str]]] = []
        for ti, table in enumerate(collapsed_tables):
            if not table:
                continue
            dominant_len = col_counts[ti]

            if merged:
                prev_lengths = Counter(len(r) for r in merged[-1])
                prev_dominant = prev_lengths.most_common(1)[0][0]
                if dominant_len == prev_dominant:
                    start = 0
                    if table[0] == merged[-1][0]:
                        start = 1
                    merged[-1].extend(table[start:])
                    continue
            merged.append(table)

    # Extract the section title from text for subtitle generation
    section_title = ""
    for line in section_text.splitlines()[:5]:
        ls = line.strip()
        if re.match(r"(?:CONDENSED\s+)?CONSOLIDATED\s+STATEMENTS?\s+OF", ls, re.IGNORECASE):
            section_title = ls
            break

    parts: list[str] = []

    for ti, table in enumerate(merged):
        if not table:
            continue

        # Determine column count
        lengths = Counter(len(r) for r in table)
        col_count = lengths.most_common(1)[0][0]

        # Pad short data rows
        for ri, row in enumerate(table):
            if len(row) < col_count and len(row) >= 2:
                has_label = not _is_numeric(row[0])
                has_value = any(_is_numeric(c) for c in row[1:])
                if has_label and has_value:
                    table[ri] = row + ["—"] * (col_count - len(row))

        # Get matching header block
        hblock = header_blocks[ti] if ti < len(header_blocks) else None

        # Build header rows
        header_rows = _build_header_rows(hblock, col_count)

        # Filter stale pdfplumber header rows (e.g. "(unaudited)", "(audited)")
        # that duplicate info already captured in our parsed headers
        _stale_pat = re.compile(
            r"^\(?(?:unaudited|audited|Successor|Predecessor)\)?$", re.IGNORECASE
        )
        if header_rows:
            table = [
                row for row in table
                if not all(_stale_pat.match(c.strip()) or not c.strip() for c in row)
            ]

        # Fallback: check if first row is column headers from the table itself
        first_row = table[0] if table else []
        all_data_rows = table
        if not header_rows and first_row:
            non_empty = [c for c in first_row if c.strip()]
            if len(non_empty) > 1 and all(not _is_numeric(c) for c in non_empty if c.strip()):
                header_rows = [first_row]
                all_data_rows = table[1:]

        # Build subtitle heading if we have multiple distinct tables
        subtitle = ""
        if len(merged) > 1 and hblock and hblock.subtitle:
            subtitle = hblock.subtitle

        table_parts: list[str] = []
        if subtitle:
            table_parts.append(f"### {section_title} {subtitle}" if section_title else f"### {subtitle}")

        # Add metadata line once (above the first table only)
        if ti == 0 and hblock and hblock.metadata:
            table_parts.append(f"\n{hblock.metadata}\n")

        md = _render_markdown_table(header_rows, all_data_rows, col_count)
        table_parts.append(md)
        parts.append("\n".join(table_parts))

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Prose cleanup
# ---------------------------------------------------------------------------

def _clean_prose_lines(text: str) -> str:
    """Clean prose text from PDF extraction artifacts.

    Shared helper used by both clean_prose() and process_mixed_section().

    - Removes standalone page numbers
    - Removes repeated page headers
    - Fixes broken line breaks (mid-sentence splits)
    - Adds markdown headings for Item headers
    - Detects sub-headings (short title-case lines)
    """
    lines = text.splitlines()

    # Remove standalone page numbers
    lines = [l for l in lines if not re.match(r"^\s*\d{1,3}\s*$", l)]

    # Remove standalone F-N page references
    lines = [l for l in lines if not re.match(r"^\s*F-\d{1,3}\s*$", l)]

    # Strip trailing F-N page references from prose lines (not table rows)
    lines = [
        re.sub(r"\s+F-\d{1,3}\s*$", "", l) if not l.lstrip().startswith("|") else l
        for l in lines
    ]

    # Detect repeated page headers (lines appearing 3+ times)
    line_counts: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        if stripped:
            line_counts[stripped] += 1
    repeated = {txt for txt, count in line_counts.items() if count >= 3 and len(txt) < 120}

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

    result = "\n".join(joined)

    # Clean up excessive blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def clean_prose(section_text: str, tables: list[list[list[str]]] | None = None) -> str:
    """Clean up a prose section from PDF extraction artifacts.

    - Removes standalone page numbers
    - Removes repeated page headers
    - Fixes broken line breaks (mid-sentence splits)
    - Adds markdown headings for Item headers
    - Detects sub-headings (short title-case lines)
    - Converts embedded tables to markdown
    """
    return _clean_prose_lines(section_text)


def process_mixed_section(pages: list["PageData"], section_name: str = "") -> str:
    """Process a section that contains both prose and embedded tables.

    Uses page-level segments (built from pdfplumber find_tables bboxes)
    to interleave cleaned prose with properly formatted markdown tables.
    """
    parts: list[str] = []

    for page in pages:
        if not page.segments:
            # Fallback: treat entire page as prose
            cleaned = _clean_prose_lines(page.text)
            if cleaned:
                parts.append(cleaned)
            continue

        for seg in page.segments:
            if seg.kind == "prose":
                cleaned = _clean_prose_lines(seg.text)
                if cleaned:
                    parts.append(cleaned)
            elif seg.kind == "table" and seg.table:
                # Collapse sparse rows and render as markdown
                collapsed = [collapse_row(row) for row in seg.table]
                collapsed = [r for r in collapsed if any(c.strip() for c in r)]
                if not collapsed:
                    continue
                # Determine column count from most common row length
                lengths = Counter(len(r) for r in collapsed)
                col_count = lengths.most_common(1)[0][0]
                # Check if first row looks like a header (all non-numeric)
                header_rows: list[list[str]] = []
                data_rows = collapsed
                if collapsed:
                    first = collapsed[0]
                    non_empty = [c for c in first if c.strip()]
                    if len(non_empty) > 1 and all(not _is_numeric(c) for c in non_empty if c.strip()):
                        header_rows = [first]
                        data_rows = collapsed[1:]
                md = _render_markdown_table(header_rows, data_rows, col_count)
                parts.append(md)

    return "\n\n".join(parts)
