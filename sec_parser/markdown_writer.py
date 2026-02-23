"""Assemble final markdown output from processed sections."""

from __future__ import annotations

import re
from pathlib import Path

from .ifrs_section_split import (
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_INCOME_STATEMENT,
    IFRS_NOTES,
    IFRS_SECTION_TITLES,
)
from .metadata import metadata_to_yaml
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
)

# Ordered output mirroring 10-Q structure
SECTION_ORDER = [
    COVER_PAGE,
    BALANCE_SHEET,
    INCOME_STATEMENT,
    CASH_FLOW,
    STOCKHOLDERS_EQUITY,
    COMPREHENSIVE_INCOME,
    NOTES,
    MDA,
    MARKET_RISK,
    CONTROLS,
    LEGAL_PROCEEDINGS,
    RISK_FACTORS,
    EXHIBITS,
    SIGNATURES,
]

IFRS_SECTION_ORDER = [
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_EQUITY_CHANGES,
    IFRS_CASH_FLOW,
    IFRS_NOTES,
]

IFRS_REQUIRED_SECTIONS = {
    IFRS_INCOME_STATEMENT,
    IFRS_BALANCE_SHEET,
    IFRS_CASH_FLOW,
    IFRS_EQUITY_CHANGES,
    IFRS_NOTES,
}

# Only these sections show a "not found" placeholder
REQUIRED_SECTIONS = {INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, STOCKHOLDERS_EQUITY, NOTES}

MISSING_PLACEHOLDER = "*Section not found in filing.*"


def assemble_markdown(
    source_filename: str,
    processed: dict[str, str],
    section_order: list[str] | None = None,
    section_titles: dict[str, str] | None = None,
    required_sections: set[str] | None = None,
    metadata: dict | None = None,
    validation_markdown: str = "",
    confidence_markdown: str = "",
) -> str:
    """Build the final markdown string from processed section content.

    Args:
        source_filename: Original PDF filename (used in the title).
        processed: Dict mapping section keys to their processed markdown content.
        section_order: Optional override for section ordering.
        section_titles: Optional override for section display titles.
        required_sections: Optional override for required sections set.
        metadata: Optional metadata dict to render as YAML front-matter.
        validation_markdown: Optional validation results rendered as markdown.

    Returns:
        Complete markdown document as a string.
    """
    order = section_order or SECTION_ORDER
    titles = section_titles or SECTION_TITLES
    required = required_sections or REQUIRED_SECTIONS

    parts: list[str] = []
    if metadata:
        parts.append(metadata_to_yaml(metadata))
    parts.append(f"# {Path(source_filename).stem}\n")

    for key in order:
        content = processed.get(key)

        if content is None:
            if key in required:
                # Show placeholder for required sections
                title = titles[key]
                parts.append(f"## {title}\n")
                parts.append(MISSING_PLACEHOLDER)
                parts.append("")
            # Silently omit optional sections that aren't present
            continue

        title = titles[key]
        parts.append(f"## {title}\n")
        # Strip duplicate section heading from content
        title_pattern = re.compile(
            r"^\s*#{0,4}\s*" + re.escape(title) + r"\s*\n*",
            re.IGNORECASE,
        )
        content = title_pattern.sub("", content, count=1).lstrip("\n")
        parts.append(content)
        parts.append("")  # blank line between sections

    if validation_markdown:
        parts.append("## Validation\n")
        parts.append(validation_markdown)
        parts.append("")

    if confidence_markdown:
        parts.append("## Data Confidence\n")
        parts.append(confidence_markdown)
        parts.append("")

    return "\n".join(parts) + "\n"


def write_markdown(output_path: Path, content: str) -> None:
    """Write markdown content to a file, creating parent directories as needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
