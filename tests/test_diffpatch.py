"""Unit tests for the diff-to-RFC-6902 helper used by the interactive editor."""

import copy
import xml.etree.ElementTree as ET

from report_aggregator.api.diffpatch import build_patches
from report_aggregator.engine.patch import apply_document_patch, apply_patches


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


def test_non_json_native_falls_back_to_raw_content():
    old = [ET.Element("ComponentLicenseInformation")]
    new = [ET.Element("ComponentLicenseInformation")]
    new[0].set("component", "edited")
    raw = "<ComponentLicenseInformation component='edited'/>"
    patches = build_patches(old, new, raw_new=raw)
    assert len(patches) == 1
    assert patches[0].op == "replace"
    assert patches[0].path == "/"
    assert patches[0].value == raw


def test_document_patch_reloads_raw_text():
    old = [ET.Element("a")]
    patch = build_patches(old, [ET.Element("b")], raw_new="<b/>")[0]

    def load(raw: bytes):
        root = ET.fromstring(raw)
        return [root]

    result = apply_document_patch(old, patch, load)
    assert len(result) == 1
    assert result[0].tag == "b"


def test_verify_false_still_returns_granular_patches():
    """verify=False skips the deepcopy re-check but still returns granular patches."""
    old = {"a": 1, "b": "hello", "c": [1, 2, 3]}
    new = {"a": 2, "b": "hello", "c": [1, 2, 3, 4]}
    patches_verified = build_patches(old, new, verify=True)
    patches_unverified = build_patches(old, new, verify=False)
    # Both should produce the same granular patches.
    assert len(patches_unverified) == len(patches_verified)
    for pv, pu in zip(patches_verified, patches_unverified):
        assert pv.op == pu.op
        assert pv.path == pu.path


def test_verify_false_no_change_yields_no_patches():
    assert build_patches({"x": 1}, {"x": 1}, verify=False) == []


def test_verify_false_non_json_falls_back_to_raw():
    import xml.etree.ElementTree as ET
    old = [ET.Element("A")]
    new = [ET.Element("B")]
    patches = build_patches(old, new, raw_new="<B/>", verify=False)
    assert len(patches) == 1
    assert patches[0].value == "<B/>"
