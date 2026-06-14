"""CycloneDX 1.4 JSON format adapter."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter
from report_aggregator.engine.identity import compute_checksum_identity
from report_aggregator.engine.mapping import MappingConfig


class CycloneDXAdapter(FormatAdapter):
    """Adapter for CycloneDX 1.4 JSON format.
    
    Implements the two-tier flat model:
    - FOSSology single upload report -> 1 library component (from metadata.component) + N file components.
    - Merges files by SHA1; promotes library components into the root components list.
    """

    def __init__(self, mapping: MappingConfig):
        self.mapping = mapping
        # Will cache original metadata structure to retain FOSSology tools list
        self._first_metadata = None

    def load(self, raw: bytes) -> dict:
        """Parse CDX JSON and validate format."""
        self._first_metadata = None
        doc = json.loads(raw)
        
        if doc.get("bomFormat") != "CycloneDX":
            raise ValueError(f"Not a CycloneDX document. Got bomFormat: {doc.get('bomFormat')}")
            
        spec = doc.get("specVersion")
        if spec != self.mapping.raw.get("spec_version", "1.4"):
            raise ValueError(f"Unsupported CycloneDX version. Expected 1.4, got: {spec}")
            
        return doc

    def entries(self, doc: dict) -> Iterable[Entry]:
        """Extract upload (metadata.component) and files (components[])."""
        # Save first metadata seen for tools assembly later
        if self._first_metadata is None and "metadata" in doc:
            self._first_metadata = copy.deepcopy(doc["metadata"])

        metadata_comp = doc.get("metadata", {}).get("component")
        if metadata_comp:
            # Upload component -> PACKAGE kind
            yield Entry(data=copy.deepcopy(metadata_comp), kind=EntryKind.PACKAGE, source_id="")
            
        for file_comp in doc.get("components", []):
            yield Entry(data=copy.deepcopy(file_comp), kind=EntryKind.FILE, source_id="")

    def identity(self, entry: Entry) -> str:
        """Resolve identity from hashes array."""
        hashes = entry.data.get("hashes", [])
        return compute_checksum_identity(hashes, preferred_alg="SHA-1")

    def local_refs(self, doc: dict) -> list[str]:
        """Collect bom-ref values to prevent cross-input collisions."""
        refs = []
        metadata_comp = doc.get("metadata", {}).get("component")
        if metadata_comp and "bom-ref" in metadata_comp:
            refs.append(metadata_comp["bom-ref"])
            
        for comp in doc.get("components", []):
            if "bom-ref" in comp:
                refs.append(comp["bom-ref"])
        return refs

    def rewrite_refs(self, doc: dict, remap: dict[str, str]) -> None:
        """Rewrite bom-ref values. FOSSology CDX has no dependency graph to rewire."""
        metadata_comp = doc.get("metadata", {}).get("component")
        if metadata_comp and "bom-ref" in metadata_comp:
            if metadata_comp["bom-ref"] in remap:
                metadata_comp["bom-ref"] = remap[metadata_comp["bom-ref"]]
                
        for comp in doc.get("components", []):
            if "bom-ref" in comp:
                if comp["bom-ref"] in remap:
                    comp["bom-ref"] = remap[comp["bom-ref"]]

    def assemble(self, entries: list[Entry], metadata: dict) -> dict:
        """Assemble the flat output document."""
        # Use cached metadata or create skeleton
        out_metadata = self._first_metadata or {"tools": []}
        
        # New timestamp and SN
        out_metadata["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Remove the FOSSology metadata.component since we are flattening it
        if "component" in out_metadata:
            del out_metadata["component"]
            
        # Optional: Add report-aggregator to tools
        out_metadata.setdefault("tools", []).append({
            "vendor": "FOSSology",
            "name": "report-aggregator",
            "version": "0.1.0"
        })

        out_doc = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": out_metadata,
            "components": []
        }
        
        for entry in entries:
            comp_data = entry.data
            
            # If this is an upload, we promote it to components array as type:library
            if entry.kind == EntryKind.PACKAGE:
                comp_data["type"] = "library"
                
            out_doc["components"].append(comp_data)
            
        return out_doc

    def render(self, doc: dict) -> bytes:
        """Serialize back to JSON."""
        return json.dumps(doc, indent=4).encode("utf-8")
