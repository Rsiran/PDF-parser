"""Multi-filing consistency: ensure same line items get same canonical names."""

from __future__ import annotations


def enforce_consistent_mappings(
    filing_mappings: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Ensure the same line item label maps to the same canonical name across filings.

    Takes a list of {original_label: canonical_name} dicts (one per filing).
    If a label is mapped in one filing but not another, the known mapping is applied.
    """
    if not filing_mappings:
        return []

    # Build global mapping: label -> canonical (first non-empty wins)
    global_map: dict[str, str] = {}
    for mapping in filing_mappings:
        for label, canonical in mapping.items():
            if canonical and label not in global_map:
                global_map[label] = canonical

    # Apply global mapping to all filings
    result = []
    for mapping in filing_mappings:
        updated = dict(mapping)
        for label in updated:
            if not updated[label] and label in global_map:
                updated[label] = global_map[label]
        result.append(updated)

    return result
