"""Tests for the high-level public API (``report_aggregator.merge``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import report_aggregator as ra


def test_merge_autodetect_returns_structured_result(spdx2fckeditor_path, spdx2zlib_path):
    result = ra.merge([spdx2fckeditor_path, spdx2zlib_path])
    assert isinstance(result, ra.MergeOutput)
    assert result.format == "spdx2tv"
    assert result.output_bytes  # non-empty merged report
    assert result.output_text.startswith("SPDXVersion") or "SPDX" in result.output_text
    assert set(result.provenance) >= {"format", "inputs", "field_provenance", "conflicts"}
    assert result.conflicts == result.provenance["conflicts"]
    # No files written when output_path is omitted.
    assert result.output_path is None
    assert result.provenance_path is None


def test_merge_accepts_string_paths(cdxfckeditor_path, cdxzlib_path):
    result = ra.merge([str(cdxfckeditor_path), str(cdxzlib_path)])
    assert result.format == "cyclonedx"


def test_merge_writes_output_and_sidecar(spdx2fckeditor_path, spdx2zlib_path, tmp_path):
    out = tmp_path / "merged.spdx"
    result = ra.merge([spdx2fckeditor_path, spdx2zlib_path], output_path=out)
    assert result.output_path == out
    assert out.exists()
    sidecar = tmp_path / "merged.provenance.json"
    assert result.provenance_path == sidecar
    assert sidecar.exists()
    written = json.loads(sidecar.read_text())
    assert written["format"] == "spdx2tv"


def test_merge_explicit_format_ok(spdx2fckeditor_path, spdx2zlib_path):
    result = ra.merge([spdx2fckeditor_path, spdx2zlib_path], format="spdx2tv")
    assert result.format == "spdx2tv"


def test_merge_format_mismatch_raises(spdx2fckeditor_path, spdx2zlib_path):
    with pytest.raises(ra.FormatMismatchError):
        ra.merge([spdx2fckeditor_path, spdx2zlib_path], format="cyclonedx")


def test_merge_missing_file_raises(spdx2fckeditor_path, tmp_path):
    with pytest.raises(ra.InputError):
        ra.merge([spdx2fckeditor_path, tmp_path / "nope.spdx"])


def test_merge_empty_inputs_raises():
    with pytest.raises(ra.InputError):
        ra.merge([])


def test_merge_undetectable_format_raises(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("nothing recognizable\n")
    b.write_text("also nothing\n")
    with pytest.raises(ra.FormatDetectionError):
        ra.merge([a, b])


def test_errors_share_base_class():
    for exc in (
        ra.FormatDetectionError,
        ra.FormatMismatchError,
        ra.InputError,
        ra.MappingError,
    ):
        assert issubclass(exc, ra.ReportAggregatorError) or exc is ra.MappingError


def test_merge_scales_to_many_inputs(spdx2fckeditor_path, spdx2zlib_path, tmp_path):
    """Sanity check the 50-75 report batch size the FOSSology agent targets."""
    inputs: list[Path] = []
    for i in range(60):
        src = spdx2fckeditor_path if i % 2 == 0 else spdx2zlib_path
        dst = tmp_path / f"input_{i:02d}.spdx"
        dst.write_bytes(Path(src).read_bytes())
        inputs.append(dst)
    result = ra.merge(inputs)
    assert result.format == "spdx2tv"
    # Deduplication: 60 copies of 2 uploads collapse back to the 2 uploads' content.
    assert len(result.provenance["inputs"]) == 60
    assert result.output_bytes
