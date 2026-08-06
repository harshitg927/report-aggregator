# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Unit tests for the conflict/field merge policy engine."""

import pytest
from report_aggregator.engine.conflict import (
    FieldPolicy,
    merge_conflict_field,
    merge_first_writer_field,
    merge_union_field,
)


class TestMergeUnionField:
    """Tests for the UNION merge strategy."""

    def test_union_simple_lists(self):
        """Union of two disjoint lists."""
        values = [(["MIT"], "src1"), (["GPL-2.0"], "src2")]
        merged, sources = merge_union_field(values)
        assert set(merged) == {"MIT", "GPL-2.0"}
        assert sources == ["src1", "src2"]

    def test_union_overlapping_lists(self):
        """Overlapping items are deduplicated."""
        values = [(["MIT", "GPL"], "src1"), (["MIT", "Apache"], "src2")]
        merged, sources = merge_union_field(values)
        assert len(merged) == 3
        assert set(merged) == {"MIT", "GPL", "Apache"}

    def test_union_single_values(self):
        """Non-list values are promoted to single-item lists."""
        values = [("MIT", "src1"), ("GPL", "src2")]
        merged, sources = merge_union_field(values)
        assert set(merged) == {"MIT", "GPL"}

    def test_union_dict_dedup(self):
        """Dict items are deduplicated by stable key."""
        d = {"id": "MIT", "url": "https://mit.example"}
        values = [([d], "src1"), ([d.copy()], "src2")]
        merged, sources = merge_union_field(values)
        assert len(merged) == 1  # Same dict, deduplicated

    def test_union_deterministic_order(self):
        """Union output is sorted for deterministic merge results."""
        values = [(["C", "A"], "src1"), (["B", "A"], "src2")]
        merged, _ = merge_union_field(values)
        assert merged == ["A", "B", "C"]

    def test_union_empty(self):
        """Empty input returns empty list."""
        merged, sources = merge_union_field([])
        assert merged == []
        assert sources == []


class TestMergeConflictField:
    """Tests for the CONFLICT_CHECK merge strategy."""

    def test_all_agree(self):
        """No conflict when all values are identical."""
        values = [("foo", "src1"), ("foo", "src2")]
        chosen, sources, conflict = merge_conflict_field("/test/field", values)
        assert chosen == "foo"
        assert sources == ["src1", "src2"]
        assert conflict is None

    def test_disagreement_first_writer_wins(self):
        """First writer wins when values disagree."""
        values = [("foo", "src1"), ("bar", "src2")]
        chosen, sources, conflict = merge_conflict_field("/test/field", values)
        assert chosen == "foo"
        assert sources == ["src1"]
        assert conflict is not None
        assert conflict.path == "/test/field"
        assert conflict.resolution == "first-writer"
        assert conflict.chosen == "foo"

    def test_disagreement_records_all_values(self):
        """Conflict entry captures all disagreeing values."""
        values = [("v1", "src1"), ("v2", "src2"), ("v3", "src3")]
        _, _, conflict = merge_conflict_field("/test/field", values)
        assert conflict is not None
        assert conflict.values["src1"] == "v1"
        assert conflict.values["src2"] == "v2"
        assert conflict.values["src3"] == "v3"

    def test_intra_report_collision(self):
        """Same source with different values doesn't lose data."""
        values = [("name_a", "src1"), ("name_b", "src1")]
        _, _, conflict = merge_conflict_field("/test/field", values)
        assert conflict is not None
        # Both values should be captured (with suffixed keys)
        assert len(conflict.values) == 2
        assert "src1" in conflict.values
        assert "src1#2" in conflict.values

    def test_all_agree_dedupes_source_ids(self):
        """Agreeing values from the same source appear once in provenance."""
        values = [("foo", "src1"), ("foo", "src1"), ("foo", "src2")]
        _, sources, conflict = merge_conflict_field("/test/field", values)
        assert conflict is None
        assert sources == ["src1", "src2"]

    def test_empty_input(self):
        """Empty input returns None for all."""
        chosen, sources, conflict = merge_conflict_field("/test/field", [])
        assert chosen is None
        assert sources == []
        assert conflict is None


class TestMergeFirstWriterField:
    """Tests for the FIRST_WRITER merge strategy."""

    def test_first_value_wins(self):
        """First value always wins."""
        values = [("first", "src1"), ("second", "src2")]
        chosen, sources = merge_first_writer_field(values)
        assert chosen == "first"
        assert sources == ["src1"]

    def test_single_value(self):
        """Single value passes through."""
        values = [("only", "src1")]
        chosen, sources = merge_first_writer_field(values)
        assert chosen == "only"
        assert sources == ["src1"]

    def test_empty_input(self):
        """Empty input returns None."""
        chosen, sources = merge_first_writer_field([])
        assert chosen is None
        assert sources == []
