# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Unit and integration tests for the ReadMeOSS adapter."""

from pathlib import Path

from report_aggregator.adapters.readmeoss import ReadMeOSSAdapter
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports


def test_readmeoss_parse_fckeditor(readmeossfckeditor_path: Path):
    mapping = load_mapping("readmeoss")
    adapter = ReadMeOSSAdapter(mapping)
    doc = adapter.load(readmeossfckeditor_path.read_bytes())

    assert doc["header"]["package_name"] == "fckeditor-2.4.8.zip"
    assert len(doc["sections"]) == 1
    assert doc["sections"][0]["name"] == "OTHER LICENSES"
    assert len(doc["sections"][0]["blocks"]) == 4


def test_readmeoss_parse_zlib_other_only(readmeosszlib_path: Path):
    mapping = load_mapping("readmeoss")
    adapter = ReadMeOSSAdapter(mapping)
    doc = adapter.load(readmeosszlib_path.read_bytes())

    assert doc["header"]["package_name"] == "zlib132.zip"
    assert len(doc["sections"]) == 1
    assert doc["sections"][0]["name"] == "OTHER LICENSES"
    assert len(doc["sections"][0]["blocks"]) == 2
    assert doc["footer"]["copyright_notices"] == "<Copyright notices>"


def test_readmeoss_round_trip(readmeossfckeditor_path: Path, readmeosszlib_path: Path):
    mapping = load_mapping("readmeoss")

    for path in (readmeossfckeditor_path, readmeosszlib_path):
        adapter = ReadMeOSSAdapter(mapping)
        doc = adapter.load(path.read_bytes())
        roundtrip = adapter.load(adapter.render(doc))
        assert roundtrip["header"]["package_name"] == doc["header"]["package_name"]
        assert sum(len(s["blocks"]) for s in roundtrip["sections"]) == sum(
            len(s["blocks"]) for s in doc["sections"]
        )


def test_readmeoss_crlf_normalization(tmp_path: Path):
    mapping = load_mapping("readmeoss")
    adapter = ReadMeOSSAdapter(mapping)
    raw = (
        "=" * 120 + "\r\n\r\n"
        "pkg.zip\r\n\r\n"
        + "-" * 120 + "\r\n\r\n"
        + "=" * 120 + "\r\n\r\n"
        " OTHER LICENSES \r\n\r\n"
        + "-" * 120 + "\r\n\r\n"
        "MIT\r\n\r\n"
        "Permission granted.\r\n\r\n"
        + "-" * 120 + "\r\n\r\n"
        "<Copyright notices>\r\n\r\n"
        "<notices>\r\n"
    ).encode("utf-8")

    doc = adapter.load(raw)
    assert doc["header"]["package_name"] == "pkg.zip"
    assert len(doc["sections"][0]["blocks"]) == 1


def test_readmeoss_two_input_merge(
    tmp_path: Path, readmeossfckeditor_path: Path, readmeosszlib_path: Path
):
    mapping = load_mapping("readmeoss")
    adapter = ReadMeOSSAdapter(mapping)

    result = merge_reports(
        adapter,
        [
            InputFile(path=readmeossfckeditor_path, input_index=0, source_id="fc"),
            InputFile(path=readmeosszlib_path, input_index=1, source_id="zlib"),
        ],
        mapping,
    )
    merged = adapter.load(result.output_bytes)
    total_blocks = sum(len(s["blocks"]) for s in merged["sections"])
    assert total_blocks == 6
    assert len(result.provenance.inputs) == 2


def test_readmeoss_license_dedup(tmp_path: Path):
    mapping = load_mapping("readmeoss")
    adapter = ReadMeOSSAdapter(mapping)

    def make_report(name: str, block_name: str) -> bytes:
        return (
            "=" * 120 + "\n\n"
            f"{name}\n\n"
            + "-" * 120 + "\n\n"
            + "=" * 120 + "\n\n"
            " OTHER LICENSES \n\n"
            + "-" * 120 + "\n\n"
            f"{block_name}\n\n"
            "Shared license text line.\n\n"
            + "-" * 120 + "\n\n"
            "<Copyright notices>\n\n"
            "<notices>\n"
        ).encode("utf-8")

    path_a = tmp_path / "a.txt"
    path_b = tmp_path / "b.txt"
    path_a.write_bytes(make_report("a.zip", "GPL-2.0-only"))
    path_b.write_bytes(make_report("b.zip", "GPL-2.0-or-later"))

    result = merge_reports(
        adapter,
        [
            InputFile(path=path_a, input_index=0, source_id="a"),
            InputFile(path=path_b, input_index=1, source_id="b"),
        ],
        mapping,
    )
    merged = adapter.load(result.output_bytes)
    assert sum(len(s["blocks"]) for s in merged["sections"]) == 1
