"""Hybrid line-item normalization: exact match -> fuzzy match -> LLM fallback."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class NormResult:
    canonical: str | None
    confidence: float
    method: str  # "exact", "fuzzy", "llm", "none"


def load_taxonomy(path: str | Path | None = None) -> dict:
    """Load taxonomy YAML. Default path: taxonomy.yaml next to this file."""
    if path is None:
        path = Path(__file__).parent / "taxonomy.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _build_alias_index(taxonomy: dict) -> dict[str, str]:
    """Build lowercase alias -> canonical name lookup dict from taxonomy.

    Includes canonical names themselves as keys.
    """
    index: dict[str, str] = {}
    for section in taxonomy.values():
        if not isinstance(section, dict):
            continue
        for item in section.values():
            if not isinstance(item, dict):
                continue
            canonical = item.get("canonical", "")
            # Add the canonical name itself as a key
            index[canonical.lower()] = canonical
            for alias in item.get("aliases", []):
                index[alias.lower()] = canonical
    return index


def match_line_item(
    label: str, taxonomy: dict, alias_index: dict[str, str] | None = None,
) -> NormResult:
    """Match a label to a canonical name using exact then fuzzy matching."""
    if not label or not label.strip():
        return NormResult(None, 0.0, "none")

    if alias_index is None:
        alias_index = _build_alias_index(taxonomy)
    label_lower = label.strip().lower()

    # Exact match
    if label_lower in alias_index:
        return NormResult(alias_index[label_lower], 1.0, "exact")

    # Fuzzy match against all aliases
    best_score = 0.0
    best_canonical = None
    for alias, canonical in alias_index.items():
        score = difflib.SequenceMatcher(None, label_lower, alias).ratio()
        if score > best_score:
            best_score = score
            best_canonical = canonical

    if best_score >= 0.85:
        return NormResult(best_canonical, best_score, "fuzzy")

    return NormResult(None, best_score, "none")


_CURRENT_HEADER = re.compile(r"(?:^|\b)current\s+(?:assets|liabilities)", re.IGNORECASE)
_NON_CURRENT_HEADER = re.compile(
    r"(?:non[- ]?current|long[- ]?term)\s+(?:assets|liabilities)", re.IGNORECASE
)

# Ambiguous labels that need current/non-current context to disambiguate
_CONTEXT_OVERRIDES: dict[str, dict[str, str]] = {
    "marketable securities": {
        "non-current": "Long-Term Investments",
        "current": "Short-Term Investments",
    },
    "other current liabilities": {
        "current": "Other Current Liabilities",
    },
    "other non-current liabilities": {
        "non-current": "Other Non-Current Liabilities",
    },
}


def normalize_table_rows(
    rows: list[list[str]], taxonomy: dict
) -> list[list[str]]:
    """Add 'Canonical' column at index 1 to each row.

    Tracks current vs non-current context from section header rows
    (e.g. "Current assets:", "Non-current liabilities:") to disambiguate
    labels that appear in both sections (e.g. "Marketable securities").
    """
    from .programmatic import _is_numeric

    alias_index = _build_alias_index(taxonomy)
    result = []
    context = ""  # "current" or "non-current"

    for row in rows:
        first_cell = row[0] if row else ""
        stripped = first_cell.strip()

        if not stripped or _is_numeric(stripped):
            canonical = ""
        else:
            # Update context from section header rows
            if _NON_CURRENT_HEADER.search(stripped):
                context = "non-current"
            elif _CURRENT_HEADER.search(stripped):
                context = "current"

            # Section sub-headers end with ":" — don't normalize them
            # Also skip rows where all value cells are empty (section headers)
            value_cells = row[1:]
            is_header_row = stripped.endswith(":") or (
                value_cells and all(not c.strip() for c in value_cells)
            )
            if is_header_row:
                canonical = ""
            else:
                # Check for context-dependent override
                override = _CONTEXT_OVERRIDES.get(stripped.lower(), {})
                if context and context in override:
                    canonical = override[context]
                else:
                    match = match_line_item(stripped, taxonomy, alias_index=alias_index)
                    canonical = match.canonical if match.canonical else ""

        new_row = [row[0], canonical] + row[1:]
        result.append(new_row)
    return result


def collect_unmapped(rows: list[list[str]], taxonomy: dict) -> list[str]:
    """Return list of labels from normalized rows that got no match.

    Expects rows already processed by normalize_table_rows (canonical at index 1).
    """
    unmapped = []
    for row in rows:
        if len(row) >= 2:
            label = row[0]
            canonical = row[1]
            if label.strip() and not canonical.strip():
                unmapped.append(label)
    return unmapped


def llm_normalize_batch(
    unmapped_labels: list[str],
    taxonomy: dict,
    verbose: bool = False,
) -> dict[str, str]:
    """Send unmapped labels to Gemini for classification.

    Returns a dict mapping original labels to canonical names.
    Labels the LLM cannot classify are omitted from the result.
    """
    try:
        from .gemini_client import generate

        # Collect all canonical names
        canonical_names = []
        for section in taxonomy.values():
            if not isinstance(section, dict):
                continue
            for item in section.values():
                if not isinstance(item, dict):
                    continue
                canonical_names.append(item.get("canonical", ""))

        canonical_list = "\n".join(f"- {name}" for name in canonical_names)
        label_list = "\n".join(f"- {label}" for label in unmapped_labels)

        prompt = (
            "You are a financial data specialist. Map each unmapped line item label "
            "to the most appropriate canonical name from the list below, or UNMAPPED "
            "if none fit.\n\n"
            f"Canonical names:\n{canonical_list}\n\n"
            f"Unmapped labels:\n{label_list}\n\n"
            "Respond with one line per label in the format:\n"
            "label -> canonical_name\n"
            "or\n"
            "label -> UNMAPPED\n"
        )

        if verbose:
            print(f"[LLM] Sending {len(unmapped_labels)} labels for classification")

        response = generate(prompt)
        result: dict[str, str] = {}
        for line in response.strip().split("\n"):
            if "->" not in line:
                continue
            parts = line.split("->", 1)
            if len(parts) == 2:
                src = parts[0].strip().strip("- ")
                dst = parts[1].strip()
                if dst != "UNMAPPED":
                    result[src] = dst

        if verbose:
            print(f"[LLM] Mapped {len(result)} of {len(unmapped_labels)} labels")

        return result

    except Exception:
        return {}
