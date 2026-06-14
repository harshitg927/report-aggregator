"""Unit tests for the mapping loader."""

import pytest
from pathlib import Path

from report_aggregator.engine.mapping import MappingError, load_mapping, get_mappings_dir

def test_load_mapping_valid():
    """Test loading a valid mapping file."""
    # We should have cyclonedx.toml by now
    mapping = load_mapping("cyclonedx")
    assert mapping.format_name == "cyclonedx"
    assert mapping.category == "graph"
    assert mapping.entries_path == "components"
    assert mapping.raw["upload_entry_path"] == "metadata.component" # From raw
    assert "hashes.SHA-1" in mapping.identity_fields
    assert "licenses" in mapping.union_fields
    assert "name" in mapping.conflict_fields

def test_load_mapping_not_found(tmp_path: Path):
    """Test loading a non-existent mapping file."""
    with pytest.raises(MappingError, match="Mapping file not found"):
        load_mapping("nonexistent", tmp_path)

def test_load_mapping_invalid_toml(tmp_path: Path):
    """Test loading a malformed TOML file."""
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("invalid = [toml\n")
    with pytest.raises(MappingError, match="Invalid TOML"):
        load_mapping("bad", tmp_path)

def test_load_mapping_missing_category(tmp_path: Path):
    """Test loading a mapping missing the category key."""
    toml = tmp_path / "missing.toml"
    toml.write_text("[missing]\nfoo = 'bar'")
    with pytest.raises(MappingError, match="missing required key 'category'"):
        load_mapping("missing", tmp_path)

def test_load_mapping_invalid_category(tmp_path: Path):
    """Test loading a mapping with an invalid category."""
    toml = tmp_path / "invalid.toml"
    toml.write_text("[invalid]\ncategory = 'foo'")
    with pytest.raises(MappingError, match="must be 'graph' or 'stanza'"):
        load_mapping("invalid", tmp_path)
