"""Unit tests for identity helpers."""

import pytest
from report_aggregator.engine.identity import (
    normalize_checksum,
    normalize_text,
    compute_text_identity,
    compute_checksum_identity,
    compute_spdx_checksum_identity,
    make_namespaced_ref,
    rewrite_embedded_refs,
)

def test_normalize_checksum():
    assert normalize_checksum(" CE19689F ") == "ce19689f"

def test_normalize_text():
    # Windows CRLF
    assert normalize_text("line 1\r\nline 2") == "line 1\nline 2"
    # Trailing spaces
    assert normalize_text("line 1   \nline 2") == "line 1\nline 2"
    # Keep blank lines
    assert normalize_text("\n\nline 1\n\n") == "\n\nline 1\n\n"

def test_compute_text_identity():
    id1 = compute_text_identity("Same text  \r\n")
    id2 = compute_text_identity("Same text\n")
    assert id1 == id2

def test_compute_checksum_identity():
    hashes = [
        {"alg": "MD5", "content": "1234"},
        {"alg": "SHA-1", "content": "ABCD"},
    ]
    # Resolves preferred and lowercases
    assert compute_checksum_identity(hashes, preferred_alg="SHA-1") == "abcd"
    
    # Fallback to MD5
    hashes2 = [{"alg": "MD5", "content": "1234"}]
    assert compute_checksum_identity(hashes2, preferred_alg="SHA-1", fallback_algs=["MD5"]) == "1234"

def test_compute_checksum_identity_error():
    with pytest.raises(ValueError, match="No recognized hash"):
        compute_checksum_identity([{"alg": "UNKNOWN", "content": "1"}])

def test_compute_spdx_checksum_identity():
    checksums = {"MD5": "1234", "SHA1": "ABCD"}
    assert compute_spdx_checksum_identity(checksums, preferred="SHA1") == "abcd"
    assert compute_spdx_checksum_identity({"MD5": "1234"}, preferred="SHA1") == "1234"

def test_make_namespaced_ref():
    assert make_namespaced_ref("SPDXRef-upload2", 0) == "SPDXRef-input0-upload2"
    assert make_namespaced_ref("SPDXRef-item32", 1) == "SPDXRef-input1-item32"
    assert make_namespaced_ref("2-932", 0) == "input0-2-932"


def test_rewrite_embedded_refs_replaces_known_tokens():
    remap = {
        "LicenseRef-fossology-GPL": "input0-LicenseRef-fossology-GPL",
    }
    expr = "LicenseRef-fossology-GPL AND MIT"
    assert rewrite_embedded_refs(expr, remap) == "input0-LicenseRef-fossology-GPL AND MIT"


def test_rewrite_embedded_refs_avoids_prefix_corruption():
    """Shorter ref IDs must not corrupt longer IDs that share a prefix."""
    remap = {
        "LicenseRef-fossology-Zlib": "input0-LicenseRef-fossology-Zlib",
    }
    expr = "LicenseRef-fossology-Zlib-possibility"
    assert rewrite_embedded_refs(expr, remap) == expr

    spdx_remap = {
        "SPDXRef-item3": "SPDXRef-input0-item3",
    }
    spdx_expr = "SPDXRef-item32"
    assert rewrite_embedded_refs(spdx_expr, spdx_remap) == spdx_expr


def test_rewrite_embedded_refs_replaces_longer_token_first():
    remap = {
        "LicenseRef-fossology-Zlib": "input0-LicenseRef-fossology-Zlib",
        "LicenseRef-fossology-Zlib-possibility": "input0-LicenseRef-fossology-Zlib-possibility",
    }
    expr = (
        "LicenseRef-fossology-Zlib-possibility OR "
        "LicenseRef-fossology-Zlib"
    )
    assert rewrite_embedded_refs(expr, remap) == (
        "input0-LicenseRef-fossology-Zlib-possibility OR "
        "input0-LicenseRef-fossology-Zlib"
    )
