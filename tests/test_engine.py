# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Unit tests for the generic merge engine using a mock adapter."""

import json
from pathlib import Path
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter
from report_aggregator.engine.mapping import MappingConfig
from report_aggregator.engine.merge import InputFile, merge_reports


class MockAdapter:
    """A mock adapter that works with JSON-like dictionaries."""

    def __init__(self, mapping: MappingConfig):
        self.mapping = mapping

    def load(self, raw: bytes) -> dict:
        return json.loads(raw)

    def entries(self, doc: dict) -> Iterable[Entry]:
        for p in doc.get("packages", []):
            yield Entry(data=p, kind=EntryKind.PACKAGE, source_id="")
        for f in doc.get("files", []):
            yield Entry(data=f, kind=EntryKind.FILE, source_id="")

    def identity(self, entry: Entry) -> str:
        # Use simple id field for mock
        return str(entry.data.get("id", ""))

    def local_refs(self, doc: dict) -> list[str]:
        refs = []
        for p in doc.get("packages", []):
            if "ref" in p:
                refs.append(p["ref"])
        return refs

    def rewrite_refs(self, doc: dict, remap: dict[str, str]) -> None:
        for p in doc.get("packages", []):
            if "ref" in p and p["ref"] in remap:
                p["ref"] = remap[p["ref"]]

    def assemble(self, entries: list[Entry], metadata: dict) -> dict:
        doc = {"packages": [], "files": [], "metadata": metadata}
        for e in entries:
            if e.kind == EntryKind.PACKAGE:
                doc["packages"].append(e.data)
            elif e.kind == EntryKind.FILE:
                doc["files"].append(e.data)
        return doc

    def render(self, doc: dict) -> bytes:
        return json.dumps(doc, sort_keys=True).encode()


def test_merge_reports_engine(tmp_path: Path):
    """Test the full engine loop with a mock adapter."""
    
    # 1. Setup mock mapping
    mapping = MappingConfig(
        format_name="mock",
        category="graph",
        entries_path="",
        union_fields=["licenses"],
        conflict_fields=["name"],
        local_ref_field="ref",
    )
    adapter = MockAdapter(mapping)

    # 2. Setup mock inputs
    doc1 = {
        "packages": [{"id": "p1", "name": "foo", "licenses": ["MIT"], "ref": "local1"}],
        "files": [{"id": "f1", "name": "f1.c"}]
    }
    doc2 = {
        "packages": [{"id": "p1", "name": "bar", "licenses": ["GPL"], "ref": "local2"}],
        "files": [{"id": "f2", "name": "f2.c"}]
    }
    
    path1 = tmp_path / "1.json"
    path1.write_text(json.dumps(doc1))
    path2 = tmp_path / "2.json"
    path2.write_text(json.dumps(doc2))
    
    inputs = [
        InputFile(path=path1, input_index=0, source_id="1"),
        InputFile(path=path2, input_index=1, source_id="2"),
    ]

    # 3. Run merge
    result = merge_reports(adapter, inputs, mapping)
    
    # 4. Verify assembled output
    out = json.loads(result.output_bytes)
    
    assert len(out["packages"]) == 1
    pkg = out["packages"][0]
    assert pkg["id"] == "p1"
    
    # Union field merged
    assert set(pkg["licenses"]) == {"MIT", "GPL"}
    
    # Conflict field - first writer wins
    assert pkg["name"] == "foo"
    
    # Ref re-namespaced (first input index)
    assert pkg["ref"] == "input0-local1"
    
    assert len(out["files"]) == 2
    
    # 5. Verify provenance
    prov = result.provenance
    assert len(prov.inputs) == 2
    
    # Conflict recorded
    assert len(prov.conflicts) == 1
    conf = prov.conflicts[0]
    assert conf.path == "/package/p1/name"
    assert conf.values == {"1": "foo", "2": "bar"}
    assert conf.chosen == "foo"
    
    # Provenance tracked
    assert set(prov.field_provenance["/package/p1/licenses"]) == {"1", "2"}
