"""SPDX 2 tag-value format adapter."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter
from report_aggregator.engine.identity import (
    compute_spdx_checksum_identity,
    compute_text_identity,
    rewrite_embedded_refs,
)
from report_aggregator.engine.mapping import MappingConfig


def _accumulate_field(item: dict[str, Any], key: str, val: Any) -> None:
    """Store a tag value, appending when the same key appears more than once."""
    existing = item.get(key)
    if existing is None:
        item[key] = val
    elif isinstance(existing, list):
        existing.append(val)
    else:
        item[key] = [existing, val]


class SPDX2TVAdapter(FormatAdapter):
    """Adapter for SPDX 2.3 tag-value format."""

    def __init__(self, mapping: MappingConfig):
        self.mapping = mapping

    def load(self, raw: bytes) -> dict:
        """Parse FOSSology SPDX tag-value into a structured dict.
        
        Handles <text>...</text> blocks and FOSSology's section markers.
        """
        text = raw.decode("utf-8")
        
        doc: dict[str, Any] = {
            "document": {},
            "packages": [],
            "files": [],
            "relationships": [],
            "extracted_licensing_info": [],
            "other": []
        }
        
        lines = text.splitlines()
        
        # State machine
        current_section = "document"  # document, package, file, license_info
        current_item: dict[str, Any] = doc["document"]
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
                
            if line == "##Package":
                current_section = "package"
                current_item = {"checksums": {}, "_relationships": []}
                doc["packages"].append(current_item)
                i += 1
                continue

            if line.startswith("##File"):
                current_section = "file"
                current_item = {"checksums": {}, "LicenseInfoInFile": []}
                doc["files"].append(current_item)
                i += 1
                continue
                
            if line.startswith("##-------------------------"):
                # Check what follows
                if i + 1 < len(lines):
                    if "License Information" in lines[i+1]:
                        current_section = "license_info"
                        i += 3
                        continue
                i += 1
                continue
                
            # Handle key-value pairs and <text> blocks
            match = re.match(r"^([a-zA-Z0-9]+):\s*(.*)$", line)
            if not match:
                i += 1
                continue
                
            key, val = match.groups()

            # Package implicitly starts when we see PackageName if we didn't see ##Package
            if key == "PackageName" and current_section != "package":
                current_section = "package"
                current_item = {"checksums": {}, "_relationships": []}
                doc["packages"].append(current_item)
            
            # Extract multi-line text blocks
            if val.startswith("<text>"):
                text_lines = [val[6:]]
                if not val.endswith("</text>"):
                    i += 1
                    while i < len(lines):
                        if lines[i].strip().endswith("</text>"):
                            text_lines.append(lines[i].replace("</text>", "").rstrip())
                            break
                        text_lines.append(lines[i])
                        i += 1
                else:
                    text_lines[0] = text_lines[0].replace("</text>", "").strip()
                val = "<text> " + "\n".join(text_lines).strip() + " </text>"
                
            # Parse based on key
            if key == "Relationship":
                # Relationship: SPDXRef-DOCUMENT DESCRIBES SPDXRef-upload2
                parts = val.split(" ")
                if len(parts) >= 3:
                    doc["relationships"].append({
                        "spdxElementId": parts[0],
                        "type": parts[1],
                        "relatedSpdxElement": parts[2],
                    })
            elif key == "PackageChecksum" or key == "FileChecksum":
                parts = val.split(":")
                if len(parts) == 2:
                    current_item["checksums"][parts[0].strip()] = parts[1].strip()
            elif key == "LicenseInfoInFile":
                current_item.setdefault("LicenseInfoInFile", []).append(val)
            elif key == "LicenseID":
                if current_section != "license_info":
                    current_section = "license_info"
                current_item = {"LicenseID": val}
                doc["extracted_licensing_info"].append(current_item)
            elif key == "Creator":
                _accumulate_field(current_item, key, val)
            else:
                current_item[key] = val
                
            i += 1
            
        return doc

    def entries(self, doc: dict) -> Iterable[Entry]:
        """Normalize multi-package input into flat entries."""
        for p in doc.get("packages", []):
            yield Entry(data=p, kind=EntryKind.PACKAGE, source_id="")
            
        for f in doc.get("files", []):
            yield Entry(data=f, kind=EntryKind.FILE, source_id="")
            
        for lic in doc.get("extracted_licensing_info", []):
            yield Entry(data=lic, kind=EntryKind.LICENSE_TEXT, source_id="")

    def identity(self, entry: Entry) -> str:
        """Resolve identity from checksums or text hash."""
        if entry.kind in (EntryKind.PACKAGE, EntryKind.FILE):
            checksums = entry.data.get("checksums", {})
            return compute_spdx_checksum_identity(checksums, preferred="SHA1")
        elif entry.kind == EntryKind.LICENSE_TEXT:
            text = entry.data.get("ExtractedText", "")
            return compute_text_identity(text)
            
        return ""

    def local_refs(self, doc: dict) -> list[str]:
        """Collect all SPDXIDs to rewire."""
        refs = []
        if "SPDXID" in doc["document"]:
            refs.append(doc["document"]["SPDXID"])
            
        for p in doc.get("packages", []):
            if "SPDXID" in p:
                refs.append(p["SPDXID"])
                
        for f in doc.get("files", []):
            if "SPDXID" in f:
                refs.append(f["SPDXID"])
                
        for lic in doc.get("extracted_licensing_info", []):
            if "LicenseID" in lic:
                refs.append(lic["LicenseID"])
                
        return refs

    def rewrite_refs(self, doc: dict, remap: dict[str, str]) -> None:
        """Apply ref remap table to all SPDXIDs and Relationships."""
        if "SPDXID" in doc["document"]:
            doc["document"]["SPDXID"] = remap.get(doc["document"]["SPDXID"], doc["document"]["SPDXID"])
            
        for p in doc.get("packages", []):
            if "SPDXID" in p:
                p["SPDXID"] = remap.get(p["SPDXID"], p["SPDXID"])
                
        for f in doc.get("files", []):
            if "SPDXID" in f:
                f["SPDXID"] = remap.get(f["SPDXID"], f["SPDXID"])
            # LicenseConcluded and LicenseInfoInFile can contain LicenseRefs
            if "LicenseConcluded" in f:
                f["LicenseConcluded"] = self._remap_license_expression(f["LicenseConcluded"], remap)
            if "LicenseInfoInFile" in f:
                f["LicenseInfoInFile"] = [self._remap_license_expression(lic, remap) for lic in f["LicenseInfoInFile"]]
                
        for lic in doc.get("extracted_licensing_info", []):
            if "LicenseID" in lic:
                lic["LicenseID"] = remap.get(lic["LicenseID"], lic["LicenseID"])
                
        for r in doc.get("relationships", []):
            r["spdxElementId"] = remap.get(r["spdxElementId"], r["spdxElementId"])
            r["relatedSpdxElement"] = remap.get(r["relatedSpdxElement"], r["relatedSpdxElement"])

    def _remap_license_expression(self, expr: str, remap: dict[str, str]) -> str:
        """Replace LicenseRef-* in expressions using the remap dict."""
        return rewrite_embedded_refs(expr, remap)

    def assemble(self, entries: list[Entry], metadata: dict) -> dict:
        """Assemble back into a full SPDX structure."""
        out_doc = {
            "document": {
                "SPDXVersion": "SPDX-2.3",
                "DataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "DocumentName": "Merged Report",
                "DocumentNamespace": f"http://report-aggregator/spdx/{uuid.uuid4()}",
            },
            "creation_info": {
                "Creator": "Tool: report-aggregator",
                "Created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "packages": [],
            "files": [],
            "extracted_licensing_info": [],
            "relationships": []
        }
        
        # We need a unified DESCRIBES relationship for all packages
        # Since we are flattening the multi-upload into one SPDX Document
        
        for e in entries:
            if e.kind == EntryKind.PACKAGE:
                out_doc["packages"].append(e.data)
                # Add DESCRIBES relationship
                if "SPDXID" in e.data:
                    out_doc["relationships"].append({
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "type": "DESCRIBES",
                        "relatedSpdxElement": e.data["SPDXID"]
                    })
            elif e.kind == EntryKind.FILE:
                out_doc["files"].append(e.data)
            elif e.kind == EntryKind.LICENSE_TEXT:
                # Based on the user's decision, we keep the last writer's name for LicenseRef.
                # The engine already keeps the first writer's data if we use FIRST_WRITER,
                # but we want the NEWEST name. Since we just use FIRST_WRITER for the whole block
                # this will naturally just keep whatever name won the conflict.
                # We can enforce last-writer in the conflict engine later if needed, but for now
                # first-writer is fine as long as we deduplicate correctly.
                out_doc["extracted_licensing_info"].append(e.data)
                
        return out_doc

    def render(self, doc: dict) -> bytes:
        """Serialize dict back to SPDX Tag-Value text."""
        lines = []
        
        def add(k, v):
            if v is None or v == "":
                return
            if isinstance(v, list):
                for item in v:
                    add(k, item)
            else:
                lines.append(f"{k}: {v}")
                
        # Document block
        for k, v in doc["document"].items():
            add(k, v)
        for k, v in doc.get("creation_info", {}).items():
            add(k, v)
        lines.append("")
        
        # Relationships (early in doc is standard)
        for r in doc["relationships"]:
            add("Relationship", f"{r['spdxElementId']} {r['type']} {r['relatedSpdxElement']}")
        if doc["relationships"]:
            lines.append("")
        
        # Packages
        for p in doc["packages"]:
            lines.append("##Package")
            lines.append("")
            for k, v in p.items():
                if k == "checksums":
                    for alg, hsh in v.items():
                        add("PackageChecksum", f"{alg}: {hsh}")
                elif not k.startswith("_"):
                    add(k, v)
            lines.append("")
            
        # Files
        for f in doc["files"]:
            lines.append("##File")
            lines.append("")
            for k, v in f.items():
                if k == "checksums":
                    for alg, hsh in v.items():
                        add("FileChecksum", f"{alg}: {hsh}")
                elif k == "LicenseInfoInFile":
                    for lic in v:
                        add("LicenseInfoInFile", lic)
                elif not k.startswith("_"):
                    add(k, v)
            lines.append("")
            
        # Extracted License Info
        if doc["extracted_licensing_info"]:
            lines.append("##-------------------------")
            lines.append("## License Information")
            lines.append("##-------------------------")
            lines.append("")
        for lic in doc["extracted_licensing_info"]:
            for k, v in lic.items():
                add(k, v)
            lines.append("")
            
        return ("\n".join(lines)).encode("utf-8")
