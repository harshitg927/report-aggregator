"""Golden and unit tests for CycloneDX adapter."""

import json
from pathlib import Path

from report_aggregator.adapters.cyclonedx import CycloneDXAdapter
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports

def test_cyclonedx_round_trip(cdxfckeditor_path: Path):
    """Test loading and rendering preserves structure."""
    mapping = load_mapping("cyclonedx")
    adapter = CycloneDXAdapter(mapping)
    
    raw = cdxfckeditor_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    # 411 files + 1 upload component
    assert len(entries) == 412
    
    # Check identity uses SHA-1 and lowercases
    upload_entry = next(e for e in entries if e.kind.name == "PACKAGE")
    assert adapter.identity(upload_entry) == "ce19689fdccb002cfb345b52402d5e15fd95bb10"
    
    # Round-trip assembly
    assembled = adapter.assemble(entries, {})
    rendered = adapter.render(assembled)
    
    doc_out = json.loads(rendered)
    assert doc_out["bomFormat"] == "CycloneDX"
    assert doc_out["specVersion"] == "1.4"
    assert "serialNumber" in doc_out
    
    # Flat model: all 412 entries should be in components
    assert len(doc_out["components"]) == 412
    
    # Upload component promoted to library
    libs = [c for c in doc_out["components"] if c["type"] == "library"]
    assert len(libs) == 1
    assert libs[0]["name"] == "fckeditor-2.4.8.zip"
    
    # File components remain files
    files = [c for c in doc_out["components"] if c["type"] == "file"]
    assert len(files) == 411

def test_cyclonedx_merge(cdxfckeditor_path: Path, cdxzlib_path: Path):
    """Test merging fckeditor and zlib reports."""
    mapping = load_mapping("cyclonedx")
    adapter = CycloneDXAdapter(mapping)
    
    inputs = [
        InputFile(path=cdxfckeditor_path, input_index=0, source_id="fckeditor"),
        InputFile(path=cdxzlib_path, input_index=1, source_id="zlib"),
    ]
    
    result = merge_reports(adapter, inputs, mapping)
    out_doc = json.loads(result.output_bytes)
    
    # There should be 2 library components (the two uploads)
    libs = [c for c in out_doc["components"] if c["type"] == "library"]
    assert len(libs) == 2
    assert libs[0]["name"] == "fckeditor-2.4.8.zip"
    assert libs[1]["name"] == "zlib132.zip"
    
    # Files should be combined and deduplicated.
    # Total merged files = 792 (some files overlap by SHA1)
    files = [c for c in out_doc["components"] if c["type"] == "file"]
    assert len(files) == 792
    
    # Check bom-ref uniqueness
    bom_refs = [c["bom-ref"] for c in out_doc["components"] if "bom-ref" in c]
    assert len(bom_refs) == len(set(bom_refs)), "bom-refs should be strictly unique"
    
    # Check provenance
    prov = result.provenance
    assert len(prov.inputs) == 2
    assert prov.inputs[0].id == "fckeditor"
    assert prov.inputs[1].id == "zlib"
    
    # Conflicts are expected! 
    # Even within a single report, identical files (by SHA-1) with different names 
    # (e.g. transparent GIFs) are merged and will raise a name conflict.
    assert len(prov.conflicts) > 0


def test_cyclonedx_adapter_reuse(cdxfckeditor_path: Path, cdxzlib_path: Path):
    """Reusing one adapter instance must not leak metadata from prior merges."""
    mapping = load_mapping("cyclonedx")
    adapter = CycloneDXAdapter(mapping)

    merge_reports(
        adapter,
        [InputFile(path=cdxfckeditor_path, input_index=0, source_id="fckeditor")],
        mapping,
    )
    result = merge_reports(
        adapter,
        [InputFile(path=cdxzlib_path, input_index=0, source_id="zlib")],
        mapping,
    )
    out_doc = json.loads(result.output_bytes)

    aggregator_tools = [
        t for t in out_doc["metadata"]["tools"]
        if t.get("name") == "report-aggregator"
    ]
    assert len(aggregator_tools) == 1

    fossology_tools = [
        t for t in out_doc["metadata"]["tools"]
        if t.get("name") == "FOSSology"
    ]
    assert len(fossology_tools) == 1
    assert fossology_tools[0]["version"] == "4.4.0.744"
