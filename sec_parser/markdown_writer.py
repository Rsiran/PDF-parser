"""Assemble final markdown output from processed sections."""

from __future__ import annotations

from pathlib import Path

from .metadata import metadata_to_yaml
from .section_split import (
    BALANCE_SHEET,
    CASH_FLOW,
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
    NOTES,
    MDA,
    MARKET_RISK,
    CONTROLS,
    LEGAL_PROCEEDINGS,
    RISK_FACTORS,
    EXHIBITS,
    SIGNATURES,
]

# Only these sections show a "not found" placeholder
REQUIRED_SECTIONS = {INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, STOCKHOLDERS_EQUITY, NOTES}

MISSING_PLACEHOLDER = "*Section not found in filing.*"


def assemble_markdown(
    source_filename: str,
    processed: dict[str, str],
    metadata: dict | None = None,
    validation_markdown: str = "",
) -> str:
    """Build the final markdown string from processed section content.

    Args:
        source_filename: Original PDF filename (used in the title).
        processed: Dict mapping section keys to their processed markdown content.
        metadata: Optional metadata dict to render as YAML front-matter.
        validation_markdown: Optional validation results rendered as markdown.

    Returns:
        Complete markdown document as a string.
    """
    parts: list[str] = []
    if metadata:
        parts.append(metadata_to_yaml(metadata))
    parts.append(f"# {Path(source_filename).stem}\n")

    for key in SECTION_ORDER:
        content = processed.get(key)

        if content is None:
            if key in REQUIRED_SECTIONS:
                # Show placeholder for required sections
                title = SECTION_TITLES[key]
                parts.append(f"## {title}\n")
                parts.append(MISSING_PLACEHOLDER)
                parts.append("")
            # Silently omit optional sections that aren't present
            continue

        title = SECTION_TITLES[key]
        parts.append(f"## {title}\n")
        parts.append(content)
        parts.append("")  # blank line between sections

    if validation_markdown:
        parts.append("## Validation\n")
        parts.append(validation_markdown)
        parts.append("")

    return "\n".join(parts) + "\n"


def write_markdown(output_path: Path, content: str) -> None:
    """Write markdown content to a file, creating parent directories as needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
