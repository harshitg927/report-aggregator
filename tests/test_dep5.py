# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Unit and integration tests for the DEP5 adapter."""

from pathlib import Path

from report_aggregator.adapters.base import EntryKind
from report_aggregator.adapters.dep5 import DEP5Adapter
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports


def test_dep5_parse_fckeditor(dep5fckeditor_path: Path):
    mapping = load_mapping("dep5")
    adapter = DEP5Adapter(mapping)
    doc = adapter.load(dep5fckeditor_path.read_bytes())

    assert doc["header"]["Format"].startswith("https://www.debian.org/doc/packaging-manuals/copyright-format/")
    assert doc["header"]["Upstream-Name"] == "fckeditor-2.4.8.zip"
    assert "<text>" in doc["header"]["Disclaimer"]
    assert len(doc["stanzas"]) == 5
    assert len(doc["licenses"]) == 1


def test_dep5_parse_zlib(dep5zlib_path: Path):
    mapping = load_mapping("dep5")
    adapter = DEP5Adapter(mapping)
    doc = adapter.load(dep5zlib_path.read_bytes())

    assert len(doc["stanzas"]) == 19
    assert len(doc["licenses"]) == 9


def test_dep5_round_trip(dep5fckeditor_path: Path, dep5zlib_path: Path):
    mapping = load_mapping("dep5")

    for path in (dep5fckeditor_path, dep5zlib_path):
        adapter = DEP5Adapter(mapping)
        doc = adapter.load(path.read_bytes())
        roundtrip = adapter.load(adapter.render(doc))
        assert len(roundtrip["stanzas"]) == len(doc["stanzas"])
        assert len(roundtrip["licenses"]) == len(doc["licenses"])


def test_dep5_two_input_merge(tmp_path: Path, dep5fckeditor_path: Path, dep5zlib_path: Path):
    mapping = load_mapping("dep5")
    adapter = DEP5Adapter(mapping)
    out = tmp_path / "merged.txt"

    inputs = [
        InputFile(path=dep5fckeditor_path, input_index=0, source_id="fc"),
        InputFile(path=dep5zlib_path, input_index=1, source_id="zlib"),
    ]
    result = merge_reports(adapter, inputs, mapping)
    out.write_bytes(result.output_bytes)

    merged = adapter.load(result.output_bytes)
    assert merged["header"]["Format"].startswith("https://www.debian.org/doc/packaging-manuals/copyright-format/")
    assert len(merged["stanzas"]) == 24
    assert len(merged["licenses"]) == 5  # deduped: many zlib LicenseRef blocks share "License by Nomos."
    assert len(result.provenance.inputs) == 2


def test_dep5_license_text_dedup(tmp_path: Path):
    mapping = load_mapping("dep5")
    adapter = DEP5Adapter(mapping)

    text_a = b"""Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: a

License: LicenseRef-test
 Same license body.
"""
    text_b = b"""Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: b

License: LicenseRef-other-name
 Same license body.
"""
    path_a = tmp_path / "a.txt"
    path_b = tmp_path / "b.txt"
    path_a.write_bytes(text_a)
    path_b.write_bytes(text_b)

    result = merge_reports(
        adapter,
        [
            InputFile(path=path_a, input_index=0, source_id="a"),
            InputFile(path=path_b, input_index=1, source_id="b"),
        ],
        mapping,
    )
    merged = adapter.load(result.output_bytes)
    assert len(merged["licenses"]) == 1


def test_dep5_glob_overlap_conflict(tmp_path: Path):
    mapping = load_mapping("dep5")
    adapter = DEP5Adapter(mapping)

    text_a = b"""Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: a

Files: shared/path.txt
Copyright: UNKNOWN
License: MIT
"""
    text_b = b"""Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: b

Files: shared/path.txt
Copyright: UNKNOWN
License: GPL-2.0-only
"""
    path_a = tmp_path / "a.txt"
    path_b = tmp_path / "b.txt"
    path_a.write_bytes(text_a)
    path_b.write_bytes(text_b)

    result = merge_reports(
        adapter,
        [
            InputFile(path=path_a, input_index=0, source_id="a"),
            InputFile(path=path_b, input_index=1, source_id="b"),
        ],
        mapping,
    )
    overlap = [c for c in result.provenance.conflicts if "glob-overlap" in c.path]
    assert len(overlap) == 1


def test_dep5_unknown_comment_stanzas(dep5fckeditor_path: Path):
    mapping = load_mapping("dep5")
    adapter = DEP5Adapter(mapping)
    doc = adapter.load(dep5fckeditor_path.read_bytes())

    unknown_stanzas = [s for s in doc["stanzas"] if s.get("license") == "UNKNOWN"]
    assert len(unknown_stanzas) >= 2
    assert any("comment" in s for s in unknown_stanzas)
