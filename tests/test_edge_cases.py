"""Tests for error paths, edge cases, and advanced merge scenarios."""

import json
from pathlib import Path

import pytest

from report_aggregator.adapters.cyclonedx import CycloneDXAdapter
from report_aggregator.adapters.spdx2tv import SPDX2TVAdapter
from report_aggregator.cli import _handle_merge
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports
from report_aggregator.engine.provenance import ProvenanceTracker


class MockArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# -- CLI error path tests --


class TestCLIErrors:
    def test_nonexistent_input(self, tmp_path: Path):
        """CLI should error on non-existent input files."""
        args = MockArgs(
            inputs=[tmp_path / "does_not_exist.json"],
            output=tmp_path / "out.json",
            format="cyclonedx",
        )
        assert _handle_merge(args) == 1

    def test_unrecognized_format(self, tmp_path: Path, cdxfckeditor_path: Path):
        """CLI should error when format is unknown."""
        # Create a fake file with unknown extension
        fake = tmp_path / "report.xyz"
        fake.write_text("fake content")
        args = MockArgs(
            inputs=[fake],
            output=tmp_path / "out.xyz",
            format=None,
        )
        assert _handle_merge(args) == 1


# -- CycloneDX edge cases --


class TestCycloneDXEdgeCases:
    def test_version_mismatch_rejection(self, tmp_path: Path):
        """CycloneDX adapter should reject specVersion != 1.4."""
        mapping = load_mapping("cyclonedx")
        adapter = CycloneDXAdapter(mapping)

        bad_doc = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [],
        }
        with pytest.raises(ValueError, match="Unsupported CycloneDX version"):
            adapter.load(json.dumps(bad_doc).encode())

    def test_invalid_bom_format(self, tmp_path: Path):
        """CycloneDX adapter should reject non-CycloneDX bomFormat."""
        mapping = load_mapping("cyclonedx")
        adapter = CycloneDXAdapter(mapping)

        bad_doc = {"bomFormat": "NotCycloneDX", "specVersion": "1.4"}
        with pytest.raises(ValueError, match="Not a CycloneDX document"):
            adapter.load(json.dumps(bad_doc).encode())


# -- Single-input merge (degenerate case) --


class TestSingleInputMerge:
    def test_single_cyclonedx_input(self, cdxfckeditor_path: Path):
        """Merging a single file should deduplicate by SHA1."""
        mapping = load_mapping("cyclonedx")
        adapter = CycloneDXAdapter(mapping)

        inputs = [InputFile(path=cdxfckeditor_path, input_index=0, source_id="single")]
        result = merge_reports(adapter, inputs, mapping)

        doc = json.loads(result.output_bytes)
        assert doc["bomFormat"] == "CycloneDX"
        # Single input: 1 library + deduplicated files
        # Files with same SHA1 (e.g. identical transparent GIFs) are merged
        libs = [c for c in doc["components"] if c["type"] == "library"]
        files = [c for c in doc["components"] if c["type"] == "file"]
        assert len(libs) == 1
        assert len(files) <= 411  # Some intra-report dedup expected
        assert len(files) > 350  # But still most files are unique
        assert len(result.provenance.inputs) == 1

    def test_single_spdx_input(self, spdx2fckeditor_path: Path):
        """Merging a single SPDX file deduplicates by SHA1."""
        mapping = load_mapping("spdx2tv")
        adapter = SPDX2TVAdapter(mapping)

        inputs = [InputFile(path=spdx2fckeditor_path, input_index=0, source_id="single")]
        result = merge_reports(adapter, inputs, mapping)

        doc = adapter.load(result.output_bytes)
        assert len(doc["packages"]) == 1
        # Files with same SHA1 are merged (intra-report dedup)
        assert len(doc["files"]) <= 411
        assert len(doc["files"]) > 350
        assert len(result.provenance.inputs) == 1


# -- 3+ input merge --


class TestTripleInputMerge:
    def test_three_input_cyclonedx(self, cdxfckeditor_path: Path, cdxzlib_path: Path):
        """Merging 3 inputs (fckeditor twice + zlib) should deduplicate correctly."""
        mapping = load_mapping("cyclonedx")
        adapter = CycloneDXAdapter(mapping)

        inputs = [
            InputFile(path=cdxfckeditor_path, input_index=0, source_id="fck1"),
            InputFile(path=cdxfckeditor_path, input_index=1, source_id="fck2"),
            InputFile(path=cdxzlib_path, input_index=2, source_id="zlib"),
        ]
        result = merge_reports(adapter, inputs, mapping)
        doc = json.loads(result.output_bytes)

        # fckeditor deduplicates with itself → still 1 library for fckeditor
        # zlib adds 1 more library → 2 libraries total
        libs = [c for c in doc["components"] if c["type"] == "library"]
        assert len(libs) == 2

        # 3 inputs tracked
        assert len(result.provenance.inputs) == 3


# -- Provenance sidecar writing --


class TestProvenanceSidecar:
    def test_write_and_read_sidecar(self, tmp_path: Path):
        """Test the full write_sidecar → read round-trip."""
        tracker = ProvenanceTracker(format_name="test")
        tracker.add_input("src1", "/path/1.json", 0)
        tracker.record_provenance("/pkg/id1", ["src1"])
        tracker.record_conflict(
            path="/pkg/id1/name",
            values_by_source={"src1": "v1"},
            resolution="first-writer",
            chosen="v1",
        )

        output_path = tmp_path / "merged.json"
        output_path.write_text("{}")  # Dummy output

        sidecar = tracker.write_sidecar(output_path)
        assert sidecar.exists()
        assert sidecar.name == "merged.provenance.json"

        # Read it back
        data = json.loads(sidecar.read_text())
        restored = ProvenanceTracker.from_dict(data)
        assert restored.format_name == "test"
        assert len(restored.inputs) == 1
        assert restored.field_provenance["/pkg/id1"] == ["src1"]
        assert len(restored.conflicts) == 1
