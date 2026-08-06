# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Unit and integration tests for the SPDX 3 JSON adapter."""

import json
from collections import Counter
from pathlib import Path

from report_aggregator.adapters.base import EntryKind
from report_aggregator.adapters.spdx3json import SPDX3JSONAdapter
from report_aggregator.engine.identity import make_namespaced_ref
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports


def _count_types(nodes: list[dict]) -> Counter:
    return Counter(n.get("type") for n in nodes)


def test_spdx3json_parse_zlib(spdx3zlib_path: Path):
    mapping = load_mapping("spdx3json")
    adapter = SPDX3JSONAdapter(mapping)
    doc = adapter.load(spdx3zlib_path.read_bytes())
    counts = _count_types(doc["nodes"])

    assert counts["software_Package"] == 1
    assert counts["software_File"] == 412
    assert counts["Annotation"] >= 400
    assert counts["expandedlicensing_CustomLicense"] == 9

    entries = list(adapter.entries(doc))
    kinds = Counter(e.kind for e in entries)
    assert kinds[EntryKind.PACKAGE] == 1
    assert kinds[EntryKind.FILE] == 412
    assert kinds[EntryKind.LICENSE_TEXT] == 9


def test_spdx3json_round_trip_zlib(spdx3zlib_path: Path):
    mapping = load_mapping("spdx3json")
    adapter = SPDX3JSONAdapter(mapping)
    doc = adapter.load(spdx3zlib_path.read_bytes())
    rendered = adapter.load(adapter.render({"nodes": doc["nodes"]}))

    assert len(rendered["nodes"]) == len(doc["nodes"])


def test_spdx3json_verified_using_identity(spdx3zlib_path: Path):
    mapping = load_mapping("spdx3json")
    adapter = SPDX3JSONAdapter(mapping)
    doc = adapter.load(spdx3zlib_path.read_bytes())

    for entry in adapter.entries(doc):
        if entry.kind in (EntryKind.PACKAGE, EntryKind.FILE):
            key = adapter.identity(entry)
            assert key == key.lower()
            assert len(key) == 40


def test_spdx3json_iri_namespacing():
    original = "https://spdx.org/rdf/3.0.0/terms/Software/File#SPDXRef-item932"
    namespaced = make_namespaced_ref(original, 0)
    assert namespaced == "https://spdx.org/rdf/3.0.0/terms/Software/File#SPDXRef-input0-item932"


def test_spdx3json_two_input_merge(spdx3zlib_path: Path, spdx3fckeditor_path: Path):
    mapping = load_mapping("spdx3json")
    adapter = SPDX3JSONAdapter(mapping)

    result = merge_reports(
        adapter,
        [
            InputFile(path=spdx3zlib_path, input_index=0, source_id="zlib"),
            InputFile(path=spdx3fckeditor_path, input_index=1, source_id="fc"),
        ],
        mapping,
    )
    nodes = json.loads(result.output_bytes)
    counts = _count_types(nodes)

    assert counts["software_Package"] == 2
    assert counts["software_File"] == 792  # 412 zlib + 411 fckeditor - 31 overlapping SHA1s
    assert any(n.get("type") == "SpdxDocument" for n in nodes)
    assert len(result.provenance.inputs) == 2

    file_ids = [
        n["spdxId"]
        for n in nodes
        if n.get("type") == "software_File"
    ]
    assert any("input0-" in i for i in file_ids)
    assert any("input1-" in i for i in file_ids)


def test_spdx3json_annotation_subject_rewired(spdx3zlib_path: Path):
    mapping = load_mapping("spdx3json")
    adapter = SPDX3JSONAdapter(mapping)

    result = merge_reports(
        adapter,
        [
            InputFile(path=spdx3zlib_path, input_index=0, source_id="zlib"),
            InputFile(path=spdx3zlib_path, input_index=1, source_id="zlib-copy"),
        ],
        mapping,
    )
    nodes = json.loads(result.output_bytes)
    file_ids = {n["spdxId"] for n in nodes if n.get("type") == "software_File"}

    for node in nodes:
        if node.get("type") != "Annotation":
            continue
        subject = node.get("subject")
        if subject and "software/File" in subject:
            assert subject in file_ids or "input" in subject
