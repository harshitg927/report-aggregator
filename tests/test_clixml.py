# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Golden and unit tests for CLIXML adapter."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from report_aggregator.adapters.base import EntryKind
from report_aggregator.adapters.clixml import CLIXMLAdapter
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports


# --- Parsing and Loading ---

def test_parse_single_root(clixmlzlib_path: Path):
    """Test loading a single-root CLIXML document."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    assert len(doc) == 1
    assert doc[0].tag == "ComponentLicenseInformation"
    assert doc[0].get("componentSHA1") == "d8bbc9cd0a4fa123f0d591f8e6f14fb296232a0a"


def test_parse_multi_root(clixmlfckeditor_path: Path, clixmlzlib_path: Path):
    """Test parsing concatenated multi-root XML."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    # Concatenate two files
    fck_raw = clixmlfckeditor_path.read_bytes()
    zlib_raw = clixmlzlib_path.read_bytes()
    multi_root = fck_raw + b'\n' + zlib_raw
    
    doc = adapter.load(multi_root)
    
    assert len(doc) == 2
    assert doc[0].get("componentSHA1") == "ce19689fdccb002cfb345b52402d5e15fd95bb10"
    assert doc[1].get("componentSHA1") == "d8bbc9cd0a4fa123f0d591f8e6f14fb296232a0a"


def test_invalid_xml():
    """Test error handling for malformed XML."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    with pytest.raises(ValueError, match="Invalid CLIXML"):
        adapter.load(b"<invalid>xml")


def test_missing_component_sha1():
    """Test error when componentSHA1 attribute is missing."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    xml_str = b'<?xml version="1.0"?><ComponentLicenseInformation></ComponentLicenseInformation>'
    doc = adapter.load(xml_str)
    
    entries = list(adapter.entries(doc))
    with pytest.raises(ValueError, match="Missing componentSHA1"):
        adapter.identity(entries[0])


# --- Identity Extraction ---

def test_component_identity(clixmlzlib_path: Path):
    """Test component identity extraction (lowercased SHA1)."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    comp_entry = next(e for e in entries if e.kind == EntryKind.PACKAGE)
    
    identity = adapter.identity(comp_entry)
    assert identity == "d8bbc9cd0a4fa123f0d591f8e6f14fb296232a0a"
    # Verify it's lowercase
    assert identity == identity.lower()


def test_license_identity(clixmlzlib_path: Path):
    """Test license identity (md5 of normalized content)."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    lic_entries = [e for e in entries if e.kind == EntryKind.LICENSE_TEXT]
    
    assert len(lic_entries) == 2  # Zlib and BSL-1.0
    
    # Each license should have a unique identity
    identities = [adapter.identity(e) for e in lic_entries]
    assert len(set(identities)) == 2


def test_obligation_identity():
    """Test obligation identity includes topic+text+sorted_licenses."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    # Create test obligation
    ob_xml = """<?xml version="1.0"?>
    <ComponentLicenseInformation componentSHA1="abc123">
        <Obligation>
            <Topic>Source code</Topic>
            <Text>Provide source</Text>
            <Licenses>
                <License>GPL-2.0</License>
                <License>LGPL-2.1</License>
            </Licenses>
        </Obligation>
    </ComponentLicenseInformation>
    """
    
    doc = adapter.load(ob_xml.encode('utf-8'))
    entries = list(adapter.entries(doc))
    
    ob_entry = next(e for e in entries if e.data.find("Topic") is not None)
    identity = adapter.identity(ob_entry)
    
    # Identity should be md5 of combined data
    assert len(identity) == 32  # MD5 hex length


# --- Text Normalization ---

def test_na_normalization():
    """Test NA strings treated as empty."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    # Test CDATA normalization directly
    assert adapter._normalize_cdata("NA") == ""
    assert adapter._normalize_cdata("  NA  ") == ""
    assert adapter._normalize_cdata("NA\n") == ""


def test_cdata_normalization():
    """Test CDATA content normalization."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    # Line endings
    text = "line1\r\nline2\rline3\n"
    normalized = adapter._normalize_cdata(text)
    assert "\r" not in normalized
    # splitlines() removes trailing newline, so we don't expect it
    assert normalized == "line1\nline2\nline3"
    
    # Trailing whitespace
    text = "line1  \nline2\t\n"
    normalized = adapter._normalize_cdata(text)
    assert normalized == "line1\nline2"


def test_cdata_escape_handling():
    """Test ]]> escape sequences."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    text = "Some text ]]> with escape"
    rendered = adapter._render_cdata(text)
    
    # The ]]> in the text should be escaped to ]]&gt;
    assert "]]&gt;" in rendered
    # There should only be one unescaped ]]> at the end (closing marker)
    assert rendered.endswith("]]>")
    # Check the middle doesn't have unescaped ]]>
    content = rendered[len("<![CDATA["):-len("]]>")]
    assert "]]>" not in content


def test_hash_prefix_stripping():
    """Test hash format normalization (plain vs sha1: prefixed)."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    # Plain hash
    assert adapter._normalize_hash("ABC123") == "abc123"
    
    # Prefixed hashes
    assert adapter._normalize_hash("sha1:ABC123") == "abc123"
    assert adapter._normalize_hash("md5:DEF456") == "def456"
    assert adapter._normalize_hash("sha256:789GHI") == "789ghi"


# --- Entry Extraction ---

def test_entries_component(clixmlzlib_path: Path):
    """Test component entry extraction."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    comp_entries = [e for e in entries if e.kind == EntryKind.PACKAGE]
    
    assert len(comp_entries) == 1
    assert comp_entries[0].data.tag == "ComponentLicenseInformation"


def test_entries_licenses(clixmlzlib_path: Path):
    """Test license entry extraction."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    lic_entries = [e for e in entries if e.kind == EntryKind.LICENSE_TEXT]
    
    assert len(lic_entries) == 2


def test_file_list_parsing(clixmlzlib_path: Path):
    """Test newline-separated file list parsing."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    # Get first license
    lic = doc[0].find("License")
    files_text = lic.findtext("Files", "")
    
    files = adapter._parse_file_list(files_text)
    assert len(files) > 0
    assert "LICENSE" in files
    assert "zlib.h" in files


def test_hash_list_parsing(clixmlzlib_path: Path):
    """Test hash list extraction from FileHash CDATA."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    lic = doc[0].find("License")
    hash_text = lic.findtext("FileHash", "")
    
    hashes = adapter._parse_hash_list(hash_text)
    assert len(hashes) > 0
    # All hashes should be lowercase
    assert all(h == h.lower() for h in hashes)


def test_optional_sections(clixmlzlib_path: Path):
    """Test missing optional sections don't cause errors."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    
    # Zlib fixture has no Copyright, Obligations, Patents, etc.
    copyright_entries = [e for e in entries if e.kind == EntryKind.STANZA and e.data.tag == "Copyright"]
    assert len(copyright_entries) == 0


# --- Round-Trip and Integration ---

def test_clixml_round_trip(clixmlzlib_path: Path):
    """Test load → render → load preserves structure."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    assembled = adapter.assemble(entries, {})
    rendered = adapter.render(assembled)
    
    # Re-parse
    doc_out = adapter.load(rendered)
    
    assert len(doc_out) == 1
    assert doc_out[0].get("componentSHA1") == "d8bbc9cd0a4fa123f0d591f8e6f14fb296232a0a"


def test_clixml_merge_two_inputs(clixmlfckeditor_path: Path, clixmlzlib_path: Path):
    """Test merging fckeditor and zlib CLIXML reports."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    inputs = [
        InputFile(path=clixmlfckeditor_path, input_index=0, source_id="fckeditor"),
        InputFile(path=clixmlzlib_path, input_index=1, source_id="zlib"),
    ]
    
    result = merge_reports(adapter, inputs, mapping)
    
    # Parse merged output
    doc_out = adapter.load(result.output_bytes)
    
    # Should have 2 components (different SHA1)
    assert len(doc_out) == 2
    
    # Verify component identities
    sha1s = [root.get("componentSHA1") for root in doc_out]
    assert "ce19689fdccb002cfb345b52402d5e15fd95bb10" in sha1s
    assert "d8bbc9cd0a4fa123f0d591f8e6f14fb296232a0a" in sha1s
    
    # Check provenance
    prov = result.provenance
    assert len(prov.inputs) == 2


def test_license_text_dedup(clixmlzlib_path: Path):
    """Test same license text across inputs → one entry."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    # Use same file twice (simulating duplicate license)
    inputs = [
        InputFile(path=clixmlzlib_path, input_index=0, source_id="zlib-a"),
        InputFile(path=clixmlzlib_path, input_index=1, source_id="zlib-b"),
    ]
    
    result = merge_reports(adapter, inputs, mapping)
    doc_out = adapter.load(result.output_bytes)
    
    # Should only have 1 component (deduplicated by SHA1)
    assert len(doc_out) == 1


def test_empty_cdata_section():
    """Test empty CDATA handled gracefully."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    rendered = adapter._render_cdata("")
    assert rendered == "<![CDATA[]]>"


def test_trailing_newlines_cdata():
    """Test file lists normalization."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    text = "file1.c\nfile2.c\n"
    # Normalization with splitlines() removes the final trailing newline
    normalized = adapter._normalize_cdata(text)
    assert normalized == "file1.c\nfile2.c"


def test_special_characters():
    """Test unicode and special characters in CDATA."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    text = "Copyright © 2024 <Company> & Sons"
    rendered = adapter._render_cdata(text)
    
    assert "©" in rendered
    assert "&" in rendered or "&amp;" in rendered


# --- Edge Cases ---

def test_duplicate_licenses_in_input():
    """Test same license twice in one input deduplicated."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    xml_str = """<?xml version="1.0"?>
    <ComponentLicenseInformation componentSHA1="abc123">
        <License type="otherwhite" name="MIT" spdxidentifier="MIT">
            <Content><![CDATA[MIT License text]]></Content>
        </License>
        <License type="otherwhite" name="MIT" spdxidentifier="MIT">
            <Content><![CDATA[MIT License text]]></Content>
        </License>
    </ComponentLicenseInformation>
    """
    
    doc = adapter.load(xml_str.encode('utf-8'))
    entries = list(adapter.entries(doc))
    
    lic_entries = [e for e in entries if e.kind == EntryKind.LICENSE_TEXT]
    
    # Should have identities computed
    identities = [adapter.identity(e) for e in lic_entries]
    
    # Both should have same identity (deduplicated during merge)
    assert identities[0] == identities[1]


def test_empty_license_content():
    """Test empty license Content handled gracefully."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    xml_str = """<?xml version="1.0"?>
    <ComponentLicenseInformation componentSHA1="abc123">
        <License type="otherwhite" name="Test" spdxidentifier="Test">
            <Content><![CDATA[]]></Content>
        </License>
    </ComponentLicenseInformation>
    """
    
    doc = adapter.load(xml_str.encode('utf-8'))
    entries = list(adapter.entries(doc))
    
    lic_entries = [e for e in entries if e.kind == EntryKind.LICENSE_TEXT]
    assert len(lic_entries) == 1
    
    identity = adapter.identity(lic_entries[0])
    # Empty content should still generate a valid (albeit trivial) md5
    assert len(identity) == 32


def test_large_license_text(clixmlfckeditor_path: Path):
    """Test large license texts handled efficiently."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlfckeditor_path.read_bytes()
    doc = adapter.load(raw)
    
    entries = list(adapter.entries(doc))
    lic_entries = [e for e in entries if e.kind == EntryKind.LICENSE_TEXT]
    
    # fckeditor has 4 licenses, some with substantial text
    assert len(lic_entries) == 4
    
    # All should have valid identities
    for lic in lic_entries:
        identity = adapter.identity(lic)
        assert len(identity) == 32


# --- Ref handling (no-ops for stanza format) ---

def test_local_refs_empty(clixmlzlib_path: Path):
    """Test CLIXML returns no local refs."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    refs = adapter.local_refs(doc)
    assert refs == []


def test_rewrite_refs_noop(clixmlzlib_path: Path):
    """Test rewrite_refs is a no-op."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    raw = clixmlzlib_path.read_bytes()
    doc = adapter.load(raw)
    
    # Should not raise
    adapter.rewrite_refs(doc, {"old": "new"})


# --- Performance ---

def test_identity_caching():
    """Test identity computation caching works."""
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    text = "Test license text"
    
    # First call
    identity1 = adapter._text_identity(text)
    
    # Second call should use cache
    identity2 = adapter._text_identity(text)
    
    assert identity1 == identity2
    assert len(adapter._identity_cache) > 0


def test_merge_performance(clixmlfckeditor_path: Path, clixmlzlib_path: Path):
    """Test merge completes in reasonable time."""
    import time
    
    mapping = load_mapping("clixml")
    adapter = CLIXMLAdapter(mapping)
    
    inputs = [
        InputFile(path=clixmlfckeditor_path, input_index=0, source_id="fckeditor"),
        InputFile(path=clixmlzlib_path, input_index=1, source_id="zlib"),
    ]
    
    start = time.time()
    result = merge_reports(adapter, inputs, mapping)
    elapsed = time.time() - start
    
    # Should complete in < 2 seconds (requirement from PHASE_4.md)
    assert elapsed < 2.0, f"Merge took {elapsed:.2f}s, expected < 2s"
    assert result.output_bytes is not None
