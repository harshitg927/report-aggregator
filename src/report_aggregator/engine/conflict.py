"""Field-level merge conflict policy.

Implements three merge strategies from architecture §5:
- UNION: set-union values (for lists like licenses, hashes)
- FIRST_WRITER: keep the first input's value, record provenance
- CONFLICT_CHECK: if values disagree → first-writer + conflict entry
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from report_aggregator.engine.provenance import ConflictEntry


class FieldPolicy(Enum):
    """How to merge a field when multiple inputs provide it."""

    UNION = "union"
    FIRST_WRITER = "first-writer"
    CONFLICT_CHECK = "conflict-check"


def merge_union_field(
    values_with_sources: list[tuple[Any, str]],
) -> tuple[list[Any], list[str]]:
    """Set-union merge for list fields (licenses, hashes, etc.).

    Args:
        values_with_sources: List of (value, source_id) pairs. Each value may
            be a list or a single item.

    Returns:
        Tuple of (merged_list, contributing_source_ids).
    """
    # Validate type consistency - all values must be same type or compatible
    types = {type(v).__name__ for v, _ in values_with_sources}
    if len(types) > 1:
        # Allow mixing None with other types, but not mixing different non-None types
        non_none_types = types - {"NoneType"}
        if len(non_none_types) > 1:
            raise TypeError(
                f"Union field has inconsistent types: {types}. "
                f"All inputs must use same type (list or scalar)."
            )
    
    seen: list[Any] = []
    seen_keys: set[str] = set()
    all_sources: list[str] = []

    for value, source_id in values_with_sources:
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            # Use JSON-stable key for dedup
            key = _stable_key(item)
            if key not in seen_keys:
                seen_keys.add(key)
                seen.append(item)
        if source_id not in all_sources:
            all_sources.append(source_id)

    seen.sort(key=_stable_key)
    all_sources.sort()
    return seen, all_sources


def merge_conflict_field(
    field_path: str,
    values_with_sources: list[tuple[Any, str]],
) -> tuple[Any, list[str], ConflictEntry | None]:
    """Merge a conflict-checked field.

    If all inputs agree, keeps the value. If they disagree,
    applies first-writer policy and produces a conflict entry.
    """
    if not values_with_sources:
        return None, [], None

    # Check if all values agree
    first_value, first_source = values_with_sources[0]
    all_agree = all(_values_equal(v, first_value) for v, _ in values_with_sources)
    all_sources = list(dict.fromkeys(s for _, s in values_with_sources))

    if all_agree:
        return first_value, all_sources, None

    # Disagreement — first-writer wins
    values_by_source: dict[str, Any] = {}
    for val, src in values_with_sources:
        key = src
        idx = 2
        while key in values_by_source:
            key = f"{src}#{idx}"
            idx += 1
        values_by_source[key] = val
    conflict = ConflictEntry(
        path=field_path,
        values=values_by_source,
        resolution="first-writer",
        chosen=first_value,
    )
    return first_value, [first_source], conflict


def merge_first_writer_field(
    values_with_sources: list[tuple[Any, str]],
) -> tuple[Any, list[str]]:
    """First-writer-wins merge: keeps the first input's value."""
    if not values_with_sources:
        return None, []
    first_value, first_source = values_with_sources[0]
    return first_value, [first_source]


def _values_equal(a: Any, b: Any) -> bool:
    """Deep equality check for field values.

    Python's built-in ``==`` already handles dict/list deep comparison,
    so this is a thin wrapper for readability.
    """
    return a == b


def _stable_key(item: Any) -> str:
    """Produce a stable string key for dedup within set-union.

    For dicts, sort keys to ensure consistent comparison.
    """
    if isinstance(item, dict):
        parts = sorted(f"{k}={_stable_key(v)}" for k, v in item.items())
        return "{" + ",".join(parts) + "}"
    if isinstance(item, list):
        return "[" + ",".join(_stable_key(i) for i in item) + "]"
    return str(item)
