# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Human-readable summaries for provenance edit entries (UI / CLI display)."""

from __future__ import annotations

import difflib
import json
from typing import Any

from report_aggregator.engine.patch import Patch, PatchPathError, get_value_at_path, parse_json_pointer

MAX_SUMMARY_LEN = 400
MAX_VALUE_PREVIEW = 120
MAX_DIFF_LINES = 8


def _preview_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    if len(text) <= MAX_VALUE_PREVIEW:
        return text
    return text[:MAX_VALUE_PREVIEW - 1] + "…"


def summarize_text_diff(old_text: str, new_text: str, max_lines: int = MAX_DIFF_LINES) -> str:
    """Compact +/- line summary for full-document text edits."""
    if old_text == new_text:
        return "(no textual change)"

    hunks: list[str] = []
    for line in difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        lineterm="",
    ):
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("+") or line.startswith("-"):
            hunks.append(line)

    if not hunks:
        return "Document updated"

    preview = "\n".join(hunks[:max_lines])
    if len(hunks) > max_lines:
        preview += f"\n… ({len(hunks) - max_lines} more changed lines)"

    if len(preview) > MAX_SUMMARY_LEN:
        return preview[:MAX_SUMMARY_LEN - 1] + "…"
    return preview


def summarize_patch(
    patch: Patch,
    *,
    old_text: str | None = None,
    new_text: str | None = None,
    old_value: Any | None = None,
) -> str:
    """Build a short display string for an edit stored in provenance."""
    op = patch.op
    path = patch.path or "/"

    if op == "remove":
        if old_value is not None:
            return f"Removed {_preview_value(old_value)} at {path}"
        return f"Removed {path}"

    if op in {"move", "copy"}:
        return f"{op} {patch.from_} → {path}"

    if op == "replace" and path == "/" and isinstance(patch.value, str):
        if old_text is not None and new_text is not None:
            return summarize_text_diff(old_text, new_text)
        if len(patch.value) > MAX_VALUE_PREVIEW:
            return f"Full document updated ({len(patch.value):,} characters)"
        return _preview_value(patch.value)

    if patch.value is None:
        return f"{op} {path}"

    new_preview = _preview_value(patch.value)
    if old_value is not None and op in {"replace", "test"}:
        summary = f"{_preview_value(old_value)} → {new_preview}"
    elif op == "add":
        summary = new_preview
    else:
        summary = new_preview

    if len(summary) > MAX_SUMMARY_LEN:
        return summary[:MAX_SUMMARY_LEN - 1] + "…"
    return summary


def value_at_path(doc: Any, path: str) -> Any | None:
    """Return the value at ``path``, or None if the path does not exist."""
    if not path or path == "/":
        return doc
    try:
        return get_value_at_path(doc, parse_json_pointer(path))
    except (PatchPathError, ValueError):
        return None
