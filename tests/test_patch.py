# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for RFC-6902 patch engine."""

import pytest

from report_aggregator.engine.patch import (
    Patch,
    PatchError,
    PatchPathError,
    PatchTestFailed,
    PatchValidationError,
    apply_patch,
    apply_patches,
    parse_json_pointer,
    path_exists,
    validate_patch,
)


class TestJSONPointerParser:
    """Test JSON Pointer parsing."""

    def test_parse_empty(self):
        assert parse_json_pointer("") == []

    def test_parse_root(self):
        assert parse_json_pointer("/") == []

    def test_parse_simple_path(self):
        assert parse_json_pointer("/foo") == ["foo"]
        assert parse_json_pointer("/foo/bar") == ["foo", "bar"]

    def test_parse_array_index(self):
        assert parse_json_pointer("/items/0") == ["items", 0]
        assert parse_json_pointer("/items/0/name") == ["items", 0, "name"]

    def test_parse_escapes(self):
        # ~0 -> ~ and ~1 -> /
        assert parse_json_pointer("/foo~0bar") == ["foo~bar"]
        assert parse_json_pointer("/foo~1bar") == ["foo/bar"]
        assert parse_json_pointer("/a~1b~0c") == ["a/b~c"]

    def test_parse_invalid_path(self):
        with pytest.raises(PatchValidationError, match="must start with"):
            parse_json_pointer("foo")


class TestPatchValidation:
    """Test patch validation."""

    def test_validate_valid_operations(self):
        for op in ["add", "remove", "replace", "move", "copy", "test"]:
            patch = Patch(op=op, path="/foo", value="bar" if op in ["add", "replace", "test"] else None,
                         from_="/old" if op in ["move", "copy"] else "")
            validate_patch(patch)

    def test_validate_invalid_operation(self):
        patch = Patch(op="invalid", path="/foo")
        with pytest.raises(PatchValidationError, match="Invalid operation"):
            validate_patch(patch)

    def test_validate_add_requires_value(self):
        patch = Patch(op="add", path="/foo")
        with pytest.raises(PatchValidationError, match="requires 'value'"):
            validate_patch(patch)

    def test_validate_move_requires_from(self):
        patch = Patch(op="move", path="/foo")
        with pytest.raises(PatchValidationError, match="requires 'from'"):
            validate_patch(patch)

    def test_validate_invalid_path_syntax(self):
        patch = Patch(op="add", path="foo", value="bar")
        with pytest.raises(PatchValidationError, match="Invalid path"):
            validate_patch(patch)


class TestPathExists:
    """Test path existence checking."""

    def test_path_exists_simple(self):
        doc = {"foo": "bar"}
        assert path_exists(doc, "/foo")
        assert not path_exists(doc, "/baz")

    def test_path_exists_nested(self):
        doc = {"a": {"b": {"c": 123}}}
        assert path_exists(doc, "/a/b/c")
        assert not path_exists(doc, "/a/b/d")

    def test_path_exists_array(self):
        doc = {"items": [1, 2, 3]}
        assert path_exists(doc, "/items/0")
        assert path_exists(doc, "/items/2")
        assert not path_exists(doc, "/items/3")


class TestAddOperation:
    """Test 'add' operation."""

    def test_add_simple_property(self):
        doc = {"existing": "value"}
        patch = Patch(op="add", path="/new", value="data")
        result = apply_patch(doc, patch)
        assert result["new"] == "data"
        assert result["existing"] == "value"

    def test_add_nested_property(self):
        doc = {"a": {"b": 1}}
        patch = Patch(op="add", path="/a/c", value=2)
        result = apply_patch(doc, patch)
        assert result["a"]["c"] == 2

    def test_add_creates_missing_parents(self):
        doc = {}
        patch = Patch(op="add", path="/a/b/c", value="deep")
        result = apply_patch(doc, patch)
        assert result["a"]["b"]["c"] == "deep"

    def test_add_to_array_middle(self):
        doc = {"items": [1, 2, 3]}
        patch = Patch(op="add", path="/items/1", value=99)
        result = apply_patch(doc, patch)
        assert result["items"] == [1, 99, 2, 3]

    def test_add_to_array_end(self):
        doc = {"items": [1, 2, 3]}
        patch = Patch(op="add", path="/items/3", value=4)
        result = apply_patch(doc, patch)
        assert result["items"] == [1, 2, 3, 4]

    def test_add_array_out_of_bounds(self):
        doc = {"items": [1, 2]}
        patch = Patch(op="add", path="/items/10", value=99)
        with pytest.raises(PatchPathError, match="out of bounds"):
            apply_patch(doc, patch)


class TestRemoveOperation:
    """Test 'remove' operation."""

    def test_remove_property(self):
        doc = {"a": 1, "b": 2}
        patch = Patch(op="remove", path="/a")
        result = apply_patch(doc, patch)
        assert "a" not in result
        assert result["b"] == 2

    def test_remove_nested_property(self):
        doc = {"a": {"b": 1, "c": 2}}
        patch = Patch(op="remove", path="/a/b")
        result = apply_patch(doc, patch)
        assert "b" not in result["a"]
        assert result["a"]["c"] == 2

    def test_remove_from_array(self):
        doc = {"items": [1, 2, 3]}
        patch = Patch(op="remove", path="/items/1")
        result = apply_patch(doc, patch)
        assert result["items"] == [1, 3]

    def test_remove_nonexistent_property(self):
        doc = {"a": 1}
        patch = Patch(op="remove", path="/b")
        with pytest.raises(PatchPathError, match="Path does not exist"):
            apply_patch(doc, patch)

    def test_remove_root(self):
        doc = {"a": 1}
        patch = Patch(op="remove", path="/")
        with pytest.raises(PatchPathError, match="Cannot remove root"):
            apply_patch(doc, patch)


class TestReplaceOperation:
    """Test 'replace' operation."""

    def test_replace_property(self):
        doc = {"a": 1, "b": 2}
        patch = Patch(op="replace", path="/a", value=99)
        result = apply_patch(doc, patch)
        assert result["a"] == 99
        assert result["b"] == 2

    def test_replace_nested_property(self):
        doc = {"a": {"b": 1}}
        patch = Patch(op="replace", path="/a/b", value="new")
        result = apply_patch(doc, patch)
        assert result["a"]["b"] == "new"

    def test_replace_array_element(self):
        doc = {"items": [1, 2, 3]}
        patch = Patch(op="replace", path="/items/1", value=99)
        result = apply_patch(doc, patch)
        assert result["items"] == [1, 99, 3]

    def test_replace_nonexistent_property(self):
        doc = {"a": 1}
        patch = Patch(op="replace", path="/b", value=2)
        with pytest.raises(PatchPathError, match="Path does not exist"):
            apply_patch(doc, patch)

    def test_replace_root(self):
        doc = {"a": 1}
        patch = Patch(op="replace", path="/", value={"b": 2})
        result = apply_patch(doc, patch)
        assert result == {"b": 2}


class TestMoveOperation:
    """Test 'move' operation."""

    def test_move_property(self):
        doc = {"a": 1, "b": 2}
        patch = Patch(op="move", path="/c", from_="/a")
        result = apply_patch(doc, patch)
        assert "a" not in result
        assert result["c"] == 1
        assert result["b"] == 2

    def test_move_nested_property(self):
        doc = {"a": {"b": {"c": 1}}, "d": {}}
        patch = Patch(op="move", path="/d/c", from_="/a/b/c")
        result = apply_patch(doc, patch)
        assert result["d"]["c"] == 1
        assert "c" not in result["a"]["b"]

    def test_move_array_element(self):
        doc = {"items": [1, 2, 3], "target": []}
        patch = Patch(op="move", path="/target/0", from_="/items/1")
        result = apply_patch(doc, patch)
        assert result["items"] == [1, 3]
        assert result["target"] == [2]


class TestCopyOperation:
    """Test 'copy' operation."""

    def test_copy_property(self):
        doc = {"a": 1, "b": 2}
        patch = Patch(op="copy", path="/c", from_="/a")
        result = apply_patch(doc, patch)
        assert result["a"] == 1  # Original still exists
        assert result["c"] == 1
        assert result["b"] == 2

    def test_copy_nested_property(self):
        doc = {"a": {"b": {"c": 1}}, "d": {}}
        patch = Patch(op="copy", path="/d/c", from_="/a/b/c")
        result = apply_patch(doc, patch)
        assert result["d"]["c"] == 1
        assert result["a"]["b"]["c"] == 1  # Original unchanged

    def test_copy_array_element(self):
        doc = {"items": [1, 2, 3], "target": []}
        patch = Patch(op="copy", path="/target/0", from_="/items/1")
        result = apply_patch(doc, patch)
        assert result["items"] == [1, 2, 3]  # Original unchanged
        assert result["target"] == [2]


class TestTestOperation:
    """Test 'test' operation."""

    def test_test_success(self):
        doc = {"a": 1, "b": "text"}
        patch = Patch(op="test", path="/a", value=1)
        result = apply_patch(doc, patch)
        assert result == doc  # No change

    def test_test_failure(self):
        doc = {"a": 1}
        patch = Patch(op="test", path="/a", value=2)
        with pytest.raises(PatchTestFailed, match="expected 2, got 1"):
            apply_patch(doc, patch)

    def test_test_nested(self):
        doc = {"a": {"b": [1, 2, 3]}}
        patch = Patch(op="test", path="/a/b/1", value=2)
        result = apply_patch(doc, patch)
        assert result == doc


class TestBatchPatches:
    """Test applying multiple patches sequentially."""

    def test_apply_multiple_patches(self):
        doc = {"a": 1}
        patches = [
            Patch(op="add", path="/b", value=2),
            Patch(op="replace", path="/a", value=99),
            Patch(op="add", path="/c", value=3),
        ]
        result = apply_patches(doc, patches)
        assert result == {"a": 99, "b": 2, "c": 3}

    def test_patches_are_sequential(self):
        doc = {"a": 1}
        patches = [
            Patch(op="add", path="/b", value={"nested": 1}),
            Patch(op="add", path="/b/nested2", value=2),
        ]
        result = apply_patches(doc, patches)
        assert result["b"] == {"nested": 1, "nested2": 2}

    def test_patch_chain_with_test(self):
        doc = {"counter": 0}
        patches = [
            Patch(op="test", path="/counter", value=0),
            Patch(op="replace", path="/counter", value=1),
            Patch(op="test", path="/counter", value=1),
        ]
        result = apply_patches(doc, patches)
        assert result["counter"] == 1

    def test_failed_test_stops_chain(self):
        doc = {"a": 1}
        patches = [
            Patch(op="test", path="/a", value=99),  # This will fail
            Patch(op="replace", path="/a", value=2),
        ]
        with pytest.raises(PatchTestFailed):
            apply_patches(doc, patches)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_nested_dict_replacement(self):
        doc = {"a": {"b": {"c": 1}}}
        patch = Patch(op="replace", path="/a/b", value={"d": 2})
        result = apply_patch(doc, patch)
        assert result["a"]["b"] == {"d": 2}

    def test_list_replacement(self):
        doc = {"items": [1, 2, 3]}
        patch = Patch(op="replace", path="/items", value=[9, 8, 7])
        result = apply_patch(doc, patch)
        assert result["items"] == [9, 8, 7]

    def test_type_mismatch_error(self):
        doc = {"a": "string"}
        patch = Patch(op="add", path="/a/b", value=1)  # Can't navigate into string
        with pytest.raises(PatchPathError, match="non-container"):
            apply_patch(doc, patch)

    def test_empty_value(self):
        doc = {"a": 1}
        patch = Patch(op="add", path="/b", value="")
        result = apply_patch(doc, patch)
        assert result["b"] == ""

    def test_complex_value(self):
        doc = {"a": 1}
        complex_value = {"nested": [1, 2, {"deep": "value"}]}
        patch = Patch(op="add", path="/b", value=complex_value)
        result = apply_patch(doc, patch)
        assert result["b"] == complex_value
