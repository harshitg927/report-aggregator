"""End-to-end tests for the CLI."""

import json
from pathlib import Path

from report_aggregator.cli import _detect_format, _handle_merge
from report_aggregator.engine.merge import InputFile

class MockArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_detect_format():
    """Test format detection from extension."""
    assert _detect_format([Path("test.json")]) == "cyclonedx"
    assert _detect_format([Path("test.spdx")]) == "spdx2tv"
    assert _detect_format([Path("test.txt")]) is None
    assert _detect_format([Path("test.json"), Path("test.spdx")]) is None # Mixed


def test_cli_merge_cyclonedx(tmp_path: Path, cdxfckeditor_path: Path, cdxzlib_path: Path):
    """Test the CLI end-to-end for CycloneDX."""
    out_path = tmp_path / "merged.json"
    
    args = MockArgs(
        inputs=[cdxfckeditor_path, cdxzlib_path],
        output=out_path,
        format=None
    )
    
    exit_code = _handle_merge(args)
    assert exit_code == 0
    assert out_path.exists()
    
    # Check sidecar
    prov_path = out_path.with_suffix(".provenance.json")
    assert prov_path.exists()
    
    doc = json.loads(out_path.read_text())
    assert doc["bomFormat"] == "CycloneDX"
    
    prov = json.loads(prov_path.read_text())
    assert len(prov["inputs"]) == 2


def test_cli_merge_spdx2tv(tmp_path: Path, spdx2fckeditor_path: Path, spdx2zlib_path: Path):
    """Test the CLI end-to-end for SPDX Tag-Value."""
    out_path = tmp_path / "merged.spdx"
    
    args = MockArgs(
        inputs=[spdx2fckeditor_path, spdx2zlib_path],
        output=out_path,
        format=None
    )
    
    exit_code = _handle_merge(args)
    assert exit_code == 0
    assert out_path.exists()
    
    # Check sidecar
    prov_path = out_path.with_suffix(".provenance.json")
    assert prov_path.exists()
    
    text = out_path.read_text()
    assert "SPDXVersion: SPDX-2.3" in text
