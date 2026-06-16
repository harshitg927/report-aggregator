"""CycloneDX 1.4 JSON format adapter."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter, validate_unique_local_refs
from report_aggregator.engine.identity import compute_checksum_identity, entry_display_name
from report_aggregator.engine.mapping import MappingConfig


class CycloneDXAdapter(FormatAdapter):
    """Adapter for CycloneDX 1.4 JSON format.
    
    Implements the two-tier flat model:
    - FOSSology single upload report -> 1 library component (from metadata.component) + N file components.
    - Merges files by SHA1; promotes library components into the root components list.
    """

    def __init__(self, mapping: MappingConfig):
        self.mapping = mapping

    def load(self, raw: bytes) -> dict:
        """Parse CDX JSON and validate format."""
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in CycloneDX file: {e}") from e
        
        if doc.get("bomFormat") != "CycloneDX":
            raise ValueError(f"Not a CycloneDX document. Got bomFormat: {doc.get('bomFormat')}")
            
        spec = doc.get("specVersion")
        if spec != self.mapping.raw.get("spec_version", "1.4"):
            raise ValueError(f"Unsupported CycloneDX version. Expected 1.4, got: {spec}")

        if "metadata" in doc:
            doc["_metadata_snapshot"] = copy.deepcopy(doc["metadata"])

        self._validate_components(doc)
        if not doc.get("metadata", {}).get("component") and not doc.get("components"):
            raise ValueError("Empty CycloneDX report: no components found")

        return doc

    def _validate_components(self, doc: dict) -> None:
        """Ensure each component has required CycloneDX fields."""
        metadata_comp = doc.get("metadata", {}).get("component")
        if metadata_comp:
            self._validate_component(metadata_comp, "metadata.component")
        for idx, comp in enumerate(doc.get("components", [])):
            self._validate_component(comp, f"components[{idx}]")

    @staticmethod
    def _validate_component(comp: dict, location: str) -> None:
        if not comp.get("name"):
            raise ValueError(
                f"CycloneDX component at {location} missing required field 'name'"
            )
        if not comp.get("type"):
            raise ValueError(
                f"CycloneDX component at {location} missing required field 'type'"
            )

    def entries(self, doc: dict) -> Iterable[Entry]:
        """Extract upload (metadata.component) and files (components[])."""
        metadata_comp = doc.get("metadata", {}).get("component")
        upload_ref = metadata_comp.get("bom-ref") if metadata_comp else None

        if metadata_comp:
            yield Entry(data=metadata_comp, kind=EntryKind.PACKAGE, source_id="")
            
        for file_comp in doc.get("components", []):
            if upload_ref and isinstance(file_comp, dict):
                file_comp["_upload_bom_ref"] = upload_ref
            yield Entry(data=file_comp, kind=EntryKind.FILE, source_id="")

    def identity(self, entry: Entry) -> str:
        """Resolve identity from hashes array."""
        hashes = entry.data.get("hashes", [])
        if not hashes:
            name = entry_display_name(entry.data)
            raise ValueError(
                f"Cannot compute identity for {entry.kind.value} '{name}': "
                f"no hashes/checksums present"
            )
        context = f"{entry.kind.value} '{entry_display_name(entry.data)}'"
        return compute_checksum_identity(hashes, preferred_alg="SHA-1", context=context)

    def local_refs(self, doc: dict) -> list[str]:
        """Collect bom-ref values to prevent cross-input collisions."""
        refs = []
        metadata_comp = doc.get("metadata", {}).get("component")
        if metadata_comp and "bom-ref" in metadata_comp:
            refs.append(metadata_comp["bom-ref"])
            
        for comp in doc.get("components", []):
            if "bom-ref" in comp:
                refs.append(comp["bom-ref"])
        validate_unique_local_refs(refs)
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
        out_metadata = copy.deepcopy(
            metadata.get("primary_metadata") or {"tools": []}
        )
        
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
            comp_data = dict(entry.data)
            upload_ref = comp_data.pop("_upload_bom_ref", None)
            
            # If this is an upload, we promote it to components array as type:library
            if entry.kind == EntryKind.PACKAGE:
                comp_data["type"] = "library"
            elif upload_ref:
                comp_data.setdefault("properties", []).append({
                    "name": "report-aggregator:upload-bom-ref",
                    "value": upload_ref,
                })
                
            out_doc["components"].append(comp_data)
            
        return out_doc

    def render(self, doc: dict) -> bytes:
        """Serialize back to JSON."""
        return json.dumps(doc, indent=4).encode("utf-8")
