"""Unit tests for the diff-to-RFC-6902 helper used by the interactive editor."""

import copy

from report_aggregator.api.diffpatch import build_patches
from report_aggregator.engine.patch import apply_patches


def _roundtrip(old, new):
    patches = build_patches(old, new)
    result = apply_patches(copy.deepcopy(old), copy.deepcopy(patches))
    assert result == new
    return patches


def test_scalar_replace():
    patches = _roundtrip({"a": 1}, {"a": 2})
    assert any(p.op == "replace" for p in patches)


def test_add_and_remove_keys():
    _roundtrip({"a": 1, "b": 2}, {"a": 1, "c": 3})


def test_nested_change():
    _roundtrip(
        {"meta": {"name": "x", "list": [1, 2, 3]}},
        {"meta": {"name": "y", "list": [1, 2]}},
    )


def test_list_growth():
    _roundtrip({"items": [1]}, {"items": [1, 2, 3]})


def test_no_change_yields_no_patches():
    assert build_patches({"a": 1}, {"a": 1}) == []


def test_type_change_replaces():
    _roundtrip({"a": {"x": 1}}, {"a": [1, 2]})
