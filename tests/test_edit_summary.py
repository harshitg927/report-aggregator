# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for human-readable edit summaries stored in provenance."""

from report_aggregator.api.edit_summary import summarize_patch, summarize_text_diff
from report_aggregator.engine.patch import Patch


def test_summarize_text_diff_shows_changed_lines():
    summary = summarize_text_diff("line one\nline two", "line one\nline THREE")
    assert "-line two" in summary
    assert "+line THREE" in summary


def test_summarize_patch_field_replace():
    patch = Patch(op="replace", path="/components/0/name", value="NEW")
    summary = summarize_patch(patch, old_value="OLD")
    assert summary == "OLD → NEW"


def test_summarize_patch_full_document():
    old = "<ComponentName>NA</ComponentName>"
    new = "<ComponentName>EDITED</ComponentName>"
    patch = Patch(op="replace", path="/", value=new)
    summary = summarize_patch(patch, old_text=old, new_text=new)
    assert "EDITED" in summary
    assert summary.startswith("-")


def test_summarize_patch_truncates_large_value():
    patch = Patch(op="replace", path="/foo", value="x" * 200)
    summary = summarize_patch(patch)
    assert summary.endswith("…")
    assert len(summary) <= 121
