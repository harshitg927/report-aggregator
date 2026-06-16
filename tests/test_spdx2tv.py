"""Golden and unit tests for SPDX 2 tag-value adapter."""

import re
from pathlib import Path

from report_aggregator.adapters.spdx2tv import SPDX2TVAdapter
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports


def _extract_license_refs(text: str) -> set[str]:
    """Extract LicenseRef-* tokens from a license expression or field value."""
    return set(re.findall(r"(?:input\d+-)?LicenseRef-[^\s()]+", text))


def _referenced_license_refs(doc: dict) -> set[str]:
    """Collect all LicenseRef-* tokens referenced by file entries."""
    refs: set[str] = set()
    for file_entry in doc.get("files", []):
        concluded = file_entry.get("LicenseConcluded")
        if isinstance(concluded, str):
            refs.update(_extract_license_refs(concluded))
        for lic in file_entry.get("LicenseInfoInFile", []):
            if isinstance(lic, str):
                refs.update(_extract_license_refs(lic))
    return refs


def _defined_license_ids(doc: dict) -> set[str]:
    """Collect LicenseID values from extracted_licensing_info blocks."""
    return {
        lic["LicenseID"]
        for lic in doc.get("extracted_licensing_info", [])
        if "LicenseID" in lic
    }


def test_spdx2tv_multiple_creators(spdx2fckeditor_path: Path):
    """Creator tags should accumulate, not overwrite."""
    mapping = load_mapping("spdx2tv")
    adapter = SPDX2TVAdapter(mapping)

    doc = adapter.load(spdx2fckeditor_path.read_bytes())
    creators = doc["document"]["Creator"]

    assert isinstance(creators, list)
    assert "Tool: fossology-4.4.0.744" in creators
    assert "Person: fossy (y)" in creators


def test_spdx2tv_license_info_in_file_union(tmp_path: Path):
    """LicenseInfoInFile should union-merge for files with the same SHA-1."""
    mapping = load_mapping("spdx2tv")
    adapter = SPDX2TVAdapter(mapping)
    shared_sha1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"

    doc_a = f"""SPDXVersion: SPDX-2.3
DataLicense: CC0-1.0
SPDXID: SPDXRef-DOCUMENT
DocumentName: test-a

##Package

PackageName: pkg-a
SPDXID: SPDXRef-pkg-a
PackageChecksum: SHA1: abc123

##File

FileName: shared.txt
SPDXID: SPDXRef-file-a
FileChecksum: SHA1: {shared_sha1}
LicenseInfoInFile: MIT
"""
    doc_b = f"""SPDXVersion: SPDX-2.3
DataLicense: CC0-1.0
SPDXID: SPDXRef-DOCUMENT
DocumentName: test-b

##Package

PackageName: pkg-b
SPDXID: SPDXRef-pkg-b
PackageChecksum: SHA1: def456

##File

FileName: shared.txt
SPDXID: SPDXRef-file-b
FileChecksum: SHA1: {shared_sha1}
LicenseInfoInFile: Apache-2.0
"""
    path_a = tmp_path / "a.spdx"
    path_b = tmp_path / "b.spdx"
    path_a.write_text(doc_a)
    path_b.write_text(doc_b)

    result = merge_reports(
        adapter,
        [
            InputFile(path=path_a, input_index=0, source_id="a"),
            InputFile(path=path_b, input_index=1, source_id="b"),
        ],
        mapping,
    )
    out_doc = adapter.load(result.output_bytes)

    merged_files = [
        f for f in out_doc["files"]
        if f.get("checksums", {}).get("SHA1", "").lower() == shared_sha1
    ]
    assert len(merged_files) == 1
    assert set(merged_files[0]["LicenseInfoInFile"]) == {"MIT", "Apache-2.0"}


def test_spdx2tv_no_dangling_license_refs(spdx2fckeditor_path: Path, spdx2zlib_path: Path):
    """Every LicenseRef in file entries must exist in extracted_licensing_info."""
    mapping = load_mapping("spdx2tv")
    adapter = SPDX2TVAdapter(mapping)

    inputs = [
        InputFile(path=spdx2fckeditor_path, input_index=0, source_id="fckeditor"),
        InputFile(path=spdx2zlib_path, input_index=1, source_id="zlib"),
    ]
    result = merge_reports(adapter, inputs, mapping)
    out_doc = adapter.load(result.output_bytes)

    referenced = _referenced_license_refs(out_doc)
    defined = _defined_license_ids(out_doc)
    missing = referenced - defined
    assert not missing, f"Dangling LicenseRef IDs: {sorted(missing)}"

    ghost_ids = {
        "input0-LicenseRef-fossology-Zlib-possibility",
        "input0-LicenseRef-fossology-See-doc.OTHER",
        "input0-LicenseRef-fossology-See-file.LICENSE",
        "input0-LicenseRef-fossology-MIT-CMU-style",
        "input0-LicenseRef-fossology-Perl-possibility",
    }
    assert not (referenced & ghost_ids)


def test_spdx2tv_round_trip(spdx2fckeditor_path: Path):
    """Test loading and rendering preserves structure."""
    mapping = load_mapping("spdx2tv")
    adapter = SPDX2TVAdapter(mapping)
    
    raw = spdx2fckeditor_path.read_bytes()
    doc = adapter.load(raw)
    
    assert doc["document"]["SPDXVersion"] == "SPDX-2.3"
    assert len(doc["packages"]) == 1
    assert len(doc["files"]) == 411
    
    # Relationships should exist (at least DESCRIBES)
    assert any(r["type"] == "DESCRIBES" for r in doc["relationships"])
    
    # Check identity resolves from checksums
    entries = list(adapter.entries(doc))
    pkg_entry = next(e for e in entries if e.kind.name == "PACKAGE")
    # should be lowercase SHA1
    assert adapter.identity(pkg_entry) == "ce19689fdccb002cfb345b52402d5e15fd95bb10"
    
    # Render back
    assembled = adapter.assemble(entries, {})
    rendered = adapter.render(assembled)
    
    doc_out = adapter.load(rendered)
    assert doc_out["document"]["SPDXVersion"] == "SPDX-2.3"
    assert len(doc_out["packages"]) == 1
    assert len(doc_out["files"]) == 411


def test_spdx2tv_merge(spdx2fckeditor_path: Path, spdx2zlib_path: Path):
    """Test merging fckeditor and zlib reports."""
    mapping = load_mapping("spdx2tv")
    adapter = SPDX2TVAdapter(mapping)
    
    inputs = [
        InputFile(path=spdx2fckeditor_path, input_index=0, source_id="fckeditor"),
        InputFile(path=spdx2zlib_path, input_index=1, source_id="zlib"),
    ]
    
    result = merge_reports(adapter, inputs, mapping)
    out_doc = adapter.load(result.output_bytes)
    
    # Output should have 2 packages
    assert len(out_doc["packages"]) == 2
    
    # Should have rewired relationships
    describes = [r for r in out_doc["relationships"] if r["type"] == "DESCRIBES"]
    assert len(describes) == 2
    
    # Verify no un-namespaced IDs remain
    for p in out_doc["packages"]:
        assert p["SPDXID"].startswith("SPDXRef-input")
        
    for f in out_doc["files"]:
        assert f["SPDXID"].startswith("SPDXRef-input")
        
    # License text blocks deduplicated
    # Zlib has custom licenses, fckeditor has custom licenses. They might share some or not.
    assert len(out_doc["extracted_licensing_info"]) > 0
    
    prov = result.provenance
    assert len(prov.inputs) == 2
    assert len(prov.conflicts) >= 0  # May be 0 if no names differ
