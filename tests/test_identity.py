# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for identity helpers."""

from report_aggregator.engine.identity import (
    compute_spdx3_checksum_identity,
    compute_stanza_identity,
    make_namespaced_ref,
)


def test_compute_spdx3_checksum_identity():
    verified = [
        {"type": "Hash", "algorithm": "sha1", "hashValue": "AbCdEf1234567890abcdef1234567890AbCdEf12"},
        {"type": "Hash", "algorithm": "md5", "hashValue": "deadbeef"},
    ]
    assert compute_spdx3_checksum_identity(verified) == "abcdef1234567890abcdef1234567890abcdef12"


def test_compute_stanza_identity_order_independent():
    a = compute_stanza_identity("MIT", ["b.txt", "a.txt"])
    b = compute_stanza_identity("MIT", ["a.txt", "b.txt"])
    assert a == b


def test_make_namespaced_iri_ref():
    original = "https://example.org/File#SPDXRef-item1"
    assert make_namespaced_ref(original, 2) == "https://example.org/File#SPDXRef-input2-item1"
