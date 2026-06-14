"""Unit tests for the provenance tracker."""

from report_aggregator.engine.provenance import ProvenanceTracker

def test_provenance_tracker_lifecycle():
    """Test adding inputs, recording provenance, and serialization."""
    tracker = ProvenanceTracker(format_name="test_fmt")
    
    # Add inputs
    tracker.add_input(source_id="A", path="a.json", input_index=0)
    tracker.add_input(source_id="B", path="b.json", input_index=1, upload_hash_sha1="hash1")
    
    assert len(tracker.inputs) == 2
    assert tracker.inputs[1].fossology_upload_hash_sha1 == "hash1"
    
    # Record field provenance
    tracker.record_provenance("/package/id1/name", ["A", "B"])
    tracker.record_provenance("/package/id1/version", ["A"])
    
    assert tracker.field_provenance["/package/id1/name"] == ["A", "B"]
    
    # Record conflict
    tracker.record_conflict(
        path="/package/id1/copyright",
        values_by_source={"A": "Copy A", "B": "Copy B"},
        resolution="first-writer",
        chosen="Copy A"
    )
    
    assert len(tracker.conflicts) == 1
    assert tracker.conflicts[0].path == "/package/id1/copyright"
    assert tracker.conflicts[0].chosen == "Copy A"
    
    # Serialize / Deserialize
    data = tracker.to_dict()
    assert data["format"] == "test_fmt"
    assert "aggregate_id" in data
    assert data["field_provenance"] == tracker.field_provenance
    
    tracker2 = ProvenanceTracker.from_dict(data)
    assert tracker2.format_name == "test_fmt"
    assert tracker2.aggregate_id == tracker.aggregate_id
    assert tracker2.field_provenance == tracker.field_provenance
    assert tracker2.inputs[1].fossology_upload_hash_sha1 == "hash1"
    assert tracker2.conflicts[0].values == {"A": "Copy A", "B": "Copy B"}
