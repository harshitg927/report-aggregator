"""Integration tests for edit layer and replay functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from report_aggregator.cli import main
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports
from report_aggregator.engine.patch import Patch, apply_patch
from report_aggregator.engine.provenance import ProvenanceTracker


# Test formats with available fixtures
FORMATS_TO_TEST = [
    ("cyclonedx", "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json", "CYCLONEDX_JSON_zlib132.zip.json"),
    ("spdx2tv", "SPDX2TV_fckeditor-2.4.8.zip.spdx", "SPDX2TV_zlib132.zip.spdx"),
    ("dep5", "DEP5_fckeditor-2.4.8.zip.txt", "DEP5_zlib132.zip.txt"),
    ("readmeoss", "ReadMe_OSS_fckeditor-2.4.8.zip.txt", "ReadMe_OSS_zlib132.zip.txt"),
    ("spdx3json", "SPDX3JSON_fckeditor-2.4.8.zip.json", "SPDX3JSON_zlib132.zip.json"),
]


@pytest.fixture
def fixtures_dir():
    """Return path to fixtures directory."""
    return Path(__file__).parent / "fixtures" / "fossology-reports"


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestEditReplayIntegration:
    """Test edit layer with actual merge operations."""

    @pytest.mark.parametrize("format_name,file1,file2", FORMATS_TO_TEST)
    def test_edit_survives_remerge(self, format_name, file1, file2, fixtures_dir, temp_output_dir):
        """Test that edit history is preserved when inputs are re-merged."""
        input1 = fixtures_dir / file1
        input2 = fixtures_dir / file2
        output = temp_output_dir / f"merged.{format_name}"

        if not input1.exists() or not input2.exists():
            pytest.skip(f"Fixtures not available for {format_name}")

        # Register adapters
        from report_aggregator.cli import _register_adapters
        _register_adapters()

        # First merge
        mapping = load_mapping(format_name)
        from report_aggregator.adapters import get_adapter_class
        adapter = get_adapter_class(format_name)(mapping)

        inputs = [
            InputFile(path=input1, input_index=0, source_id="input1"),
            InputFile(path=input2, input_index=1, source_id="input2"),
        ]

        result = merge_reports(adapter, inputs, mapping, output)
        output.write_bytes(result.output_bytes)
        result.provenance.write_sidecar(output)

        # Add an edit to provenance (we test that edit history survives, not the patch itself)
        provenance = result.provenance
        patch = Patch(op="add", path="/test_field", value="test")
        provenance.add_edit(who="test_user", patch=patch, reason="Test edit")
        provenance.write_sidecar(output)

        # Verify edit added
        sidecar_path = output.parent / f"{output.stem}.provenance.json"
        prov_data = json.loads(sidecar_path.read_text())
        assert len(prov_data["edits"]) == 1

        # Re-merge with same inputs
        result2 = merge_reports(adapter, inputs, mapping, output)
        output.write_bytes(result2.output_bytes)
        result2.provenance.write_sidecar(output)

        # Verify edit history preserved
        assert len(result2.provenance.edits) == 1
        assert result2.provenance.edits[0].who == "test_user"
        assert result2.provenance.edits[0].reason == "Test edit"

    @pytest.mark.parametrize("format_name,file1,file2", FORMATS_TO_TEST)
    def test_edit_survives_new_input(self, format_name, file1, file2, fixtures_dir, temp_output_dir):
        """Test that edit history is preserved when a new input is added."""
        input1 = fixtures_dir / file1
        input2 = fixtures_dir / file2
        output = temp_output_dir / f"merged.{format_name}"

        if not input1.exists() or not input2.exists():
            pytest.skip(f"Fixtures not available for {format_name}")

        from report_aggregator.cli import _register_adapters
        _register_adapters()

        mapping = load_mapping(format_name)
        from report_aggregator.adapters import get_adapter_class
        adapter = get_adapter_class(format_name)(mapping)

        # Initial merge with one input
        inputs = [InputFile(path=input1, input_index=0, source_id="input1")]
        result = merge_reports(adapter, inputs, mapping, output)
        output.write_bytes(result.output_bytes)
        result.provenance.write_sidecar(output)

        # Add edit to provenance
        patch = Patch(op="add", path="/new_input_test", value="preserved")
        provenance = result.provenance
        provenance.add_edit(who="tester", patch=patch, reason="Before new input")
        provenance.write_sidecar(output)

        # Re-merge with additional input
        inputs.append(InputFile(path=input2, input_index=1, source_id="input2"))
        result2 = merge_reports(adapter, inputs, mapping, output)
        output.write_bytes(result2.output_bytes)
        result2.provenance.write_sidecar(output)

        # Verify edit history persisted
        assert len(result2.provenance.edits) == 1
        assert result2.provenance.edits[0].who == "tester"
        assert result2.provenance.edits[0].reason == "Before new input"

    def test_invalid_patch_skipped_with_warning(self, fixtures_dir, temp_output_dir):
        """Test that invalid patches are skipped without failing the merge."""
        format_name = "cyclonedx"
        input1 = fixtures_dir / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"
        input2 = fixtures_dir / "CYCLONEDX_JSON_zlib132.zip.json"
        output = temp_output_dir / "merged.json"

        if not input1.exists() or not input2.exists():
            pytest.skip("CycloneDX fixtures not available")

        from report_aggregator.cli import _register_adapters
        _register_adapters()

        mapping = load_mapping(format_name)
        from report_aggregator.adapters import get_adapter_class
        adapter = get_adapter_class(format_name)(mapping)

        inputs = [
            InputFile(path=input1, input_index=0, source_id="input1"),
            InputFile(path=input2, input_index=1, source_id="input2"),
        ]

        result = merge_reports(adapter, inputs, mapping, output)
        output.write_bytes(result.output_bytes)
        
        # Add an invalid patch (path doesn't exist)
        provenance = result.provenance
        invalid_patch = Patch(op="replace", path="/nonexistent/path/field", value="new")
        provenance.add_edit(who="tester", patch=invalid_patch, reason="Invalid test")
        provenance.write_sidecar(output)

        # Re-merge should succeed despite invalid patch
        result2 = merge_reports(adapter, inputs, mapping, output)
        assert result2.output_bytes is not None
        
        # Edit history should be preserved
        assert len(result2.provenance.edits) == 1


class TestEditCLI:
    """Test edit CLI commands."""

    def test_edit_command_cyclonedx(self, fixtures_dir, temp_output_dir):
        """Test edit command on CycloneDX format."""
        input1 = fixtures_dir / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"
        output = temp_output_dir / "merged.json"

        if not input1.exists():
            pytest.skip("CycloneDX fixture not available")

        # First merge
        result = main([
            "merge",
            str(input1),
            "-o", str(output),
            "--format", "cyclonedx"
        ])
        assert result == 0
        assert output.exists()

        # Apply edit
        patch_json = json.dumps({"op": "add", "path": "/test_field", "value": "cli_test"})
        result = main([
            "edit",
            str(output),
            "--patch", patch_json,
            "--who", "cli_tester",
            "--reason", "CLI test edit"
        ])
        assert result == 0

        # Verify edit in provenance
        sidecar_path = output.parent / f"{output.stem}.provenance.json"
        provenance_data = json.loads(sidecar_path.read_text())
        assert len(provenance_data["edits"]) == 1
        assert provenance_data["edits"][0]["who"] == "cli_tester"
        assert provenance_data["edits"][0]["reason"] == "CLI test edit"

    def test_list_edits_command(self, fixtures_dir, temp_output_dir):
        """Test list-edits command."""
        input1 = fixtures_dir / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"
        output = temp_output_dir / "merged.json"

        if not input1.exists():
            pytest.skip("CycloneDX fixture not available")

        # Merge and add edits
        main(["merge", str(input1), "-o", str(output), "--format", "cyclonedx"])
        
        patch1 = json.dumps({"op": "add", "path": "/field1", "value": "v1"})
        main(["edit", str(output), "--patch", patch1, "--who", "user1"])
        
        patch2 = json.dumps({"op": "add", "path": "/field2", "value": "v2"})
        main(["edit", str(output), "--patch", patch2, "--who", "user2", "--reason", "Second edit"])

        # List edits
        result = main(["list-edits", str(output)])
        assert result == 0

    def test_undo_command(self, fixtures_dir, temp_output_dir):
        """Test undo command."""
        input1 = fixtures_dir / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"
        output = temp_output_dir / "merged.json"

        if not input1.exists():
            pytest.skip("CycloneDX fixture not available")

        # Merge and add edits
        main(["merge", str(input1), "-o", str(output), "--format", "cyclonedx"])
        
        patch1 = json.dumps({"op": "add", "path": "/field1", "value": "v1"})
        main(["edit", str(output), "--patch", patch1])
        
        patch2 = json.dumps({"op": "add", "path": "/field2", "value": "v2"})
        main(["edit", str(output), "--patch", patch2])

        # Undo last edit
        result = main(["undo", str(output)])
        assert result == 0

        # Verify only one edit remains
        sidecar_path = output.parent / f"{output.stem}.provenance.json"
        provenance_data = json.loads(sidecar_path.read_text())
        assert len(provenance_data["edits"]) == 1

    def test_replay_command(self, fixtures_dir, temp_output_dir):
        """Test replay command."""
        input1 = fixtures_dir / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"
        output = temp_output_dir / "merged.json"

        if not input1.exists():
            pytest.skip("CycloneDX fixture not available")

        # Merge and add edit
        main(["merge", str(input1), "-o", str(output), "--format", "cyclonedx"])
        
        patch = json.dumps({"op": "add", "path": "/replay_test", "value": "replayed"})
        main(["edit", str(output), "--patch", patch])

        # Manually remove the field to test replay
        from report_aggregator.cli import _register_adapters
        _register_adapters()
        mapping = load_mapping("cyclonedx")
        from report_aggregator.adapters import get_adapter_class
        adapter = get_adapter_class("cyclonedx")(mapping)
        
        doc = adapter.load(output.read_bytes())
        if "replay_test" in doc:
            del doc["replay_test"]
        output.write_bytes(adapter.render(doc))

        # Replay should restore the field
        result = main(["replay", str(output)])
        assert result == 0

        # Verify field restored
        doc = adapter.load(output.read_bytes())
        assert doc.get("replay_test") == "replayed"


class TestProvenanceEditSerialization:
    """Test provenance edit serialization and deserialization."""

    def test_edit_roundtrip(self):
        """Test that edits serialize and deserialize correctly."""
        provenance = ProvenanceTracker(format_name="test")
        
        patch1 = Patch(op="add", path="/field", value="value1")
        provenance.add_edit(who="user1", patch=patch1, reason="First edit")
        
        patch2 = Patch(op="replace", path="/field", value="value2")
        provenance.add_edit(who="user2", patch=patch2, reason="Second edit")

        # Serialize
        data = provenance.to_dict()
        assert len(data["edits"]) == 2
        assert data["edits"][0]["who"] == "user1"
        assert data["edits"][0]["patch"]["op"] == "add"
        assert data["edits"][1]["reason"] == "Second edit"

        # Deserialize
        restored = ProvenanceTracker.from_dict(data)
        assert len(restored.edits) == 2
        assert restored.edits[0].who == "user1"
        assert restored.edits[0].patch.op == "add"
        assert restored.edits[0].patch.path == "/field"
        assert restored.edits[1].reason == "Second edit"

    def test_empty_edits(self):
        """Test provenance with no edits."""
        provenance = ProvenanceTracker(format_name="test")
        data = provenance.to_dict()
        
        assert "edits" in data
        assert data["edits"] == []
        
        restored = ProvenanceTracker.from_dict(data)
        assert len(restored.edits) == 0
