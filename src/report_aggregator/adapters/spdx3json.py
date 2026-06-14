"""SPDX 3 JSON graph format adapter."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter
from report_aggregator.engine.identity import (
    compute_spdx3_checksum_identity,
    compute_text_identity,
    rewrite_refs_in_structure,
)
from report_aggregator.engine.mapping import MappingConfig

_PACKAGE_TYPE = "software_Package"
_FILE_TYPE = "software_File"
_CUSTOM_LICENSE_TYPE = "expandedlicensing_CustomLicense"

_ENTRY_NODE_TYPES = {_PACKAGE_TYPE, _FILE_TYPE, _CUSTOM_LICENSE_TYPE}
_META_NODE_TYPES = frozenset({
    "NamespaceMap", "CreationInfo", "SpdxDocument", "Tool", "Person",
    "PackageVerificationCode",
})


def _sanitize_json_text(raw: bytes) -> str:
    """Prepare FOSSology SPDX3 JSON for stdlib parsing."""
    text = raw.decode("utf-8")
    return text.replace("\t", " ")


def _extract_text_from_spdx_field(value: str) -> str:
    if value.startswith("<text>") and value.endswith("</text>"):
        return value[6:-7].strip()
    return value


class SPDX3JSONAdapter(FormatAdapter):
    """Adapter for FOSSology SPDX 3 plain JSON (array of typed nodes)."""

    def __init__(self, mapping: MappingConfig):
        self.mapping = mapping
        self._primary_meta: dict[str, Any] = {}

    def load(self, raw: bytes) -> dict[str, Any]:
        nodes = json.loads(_sanitize_json_text(raw))
        if not isinstance(nodes, list):
            raise ValueError("SPDX 3 JSON must be a top-level array of nodes")

        by_id: dict[str, dict[str, Any]] = {}
        for node in nodes:
            node_id = node.get("spdxId") or node.get("@id")
            if node_id:
                by_id[node_id] = node

        return {"nodes": nodes, "by_id": by_id}

    def _collect_satellites(self, doc: dict[str, Any], subject_id: str) -> list[dict[str, Any]]:
        satellites: list[dict[str, Any]] = []
        prefix = subject_id + "#"
        for node in doc["nodes"]:
            node_type = node.get("type", "")
            if node_type in _META_NODE_TYPES or node_type in _ENTRY_NODE_TYPES:
                continue
            node_id = node.get("spdxId") or node.get("@id", "")
            if node.get("subject") == subject_id or node_id.startswith(prefix):
                satellites.append(copy.deepcopy(node))
        return satellites

    def entries(self, doc: dict[str, Any]) -> Iterable[Entry]:
        if not self._primary_meta:
            for node in doc["nodes"]:
                node_type = node.get("type", "")
                if node_type in _META_NODE_TYPES:
                    self._primary_meta[node_type] = copy.deepcopy(node)

        for node in doc["nodes"]:
            node_type = node.get("type", "")
            if node_type == _PACKAGE_TYPE:
                data = copy.deepcopy(node)
                data["_satellites"] = self._collect_satellites(doc, node["spdxId"])
                yield Entry(data=data, kind=EntryKind.PACKAGE, source_id="")
            elif node_type == _FILE_TYPE:
                data = copy.deepcopy(node)
                data["_satellites"] = self._collect_satellites(doc, node["spdxId"])
                yield Entry(data=data, kind=EntryKind.FILE, source_id="")
            elif node_type == _CUSTOM_LICENSE_TYPE:
                yield Entry(data=copy.deepcopy(node), kind=EntryKind.LICENSE_TEXT, source_id="")

    def identity(self, entry: Entry) -> str:
        if entry.kind in (EntryKind.PACKAGE, EntryKind.FILE):
            verified = entry.data.get("verifiedUsing", [])
            return compute_spdx3_checksum_identity(verified)
        if entry.kind == EntryKind.LICENSE_TEXT:
            text = entry.data.get("simplelicensing_licenseText", "")
            return compute_text_identity(_extract_text_from_spdx_field(text))
        return ""

    def local_refs(self, doc: dict[str, Any]) -> list[str]:
        refs: list[str] = []
        for node in doc["nodes"]:
            node_id = node.get("spdxId") or node.get("@id")
            if isinstance(node_id, str):
                refs.append(node_id)
            for field in ("subject", "from", "creationInfo"):
                val = node.get(field)
                if isinstance(val, str):
                    refs.append(val)
                elif isinstance(val, list):
                    refs.extend(v for v in val if isinstance(v, str))
            to_val = node.get("to")
            if isinstance(to_val, list):
                refs.extend(v for v in to_val if isinstance(v, str))
            elif isinstance(to_val, str):
                refs.append(to_val)
            elements = node.get("element")
            if isinstance(elements, list):
                refs.extend(v for v in elements if isinstance(v, str))
        return list(dict.fromkeys(refs))

    def rewrite_refs(self, doc: dict[str, Any], remap: dict[str, str]) -> None:
        doc["nodes"] = rewrite_refs_in_structure(doc["nodes"], remap)
        doc["by_id"] = {
            (remap.get(k, k)): rewrite_refs_in_structure(v, remap)
            for k, v in doc.get("by_id", {}).items()
        }

    def assemble(self, entries: list[Entry], metadata: dict[str, Any]) -> dict[str, Any]:
        output_nodes: list[dict[str, Any]] = []
        element_ids: list[str] = []
        relationships: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        namespace = f"http://report-aggregator/spdx3/{uuid.uuid4()}.json"
        creation_info_id = f"{namespace}#creationInfo1"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        output_nodes.append({
            "type": "NamespaceMap",
            "namespace": namespace,
            "prefix": "URI",
        })

        primary_creation = self._primary_meta.get("CreationInfo", {})
        output_nodes.append({
            "@id": creation_info_id,
            "type": "CreationInfo",
            "specVersion": primary_creation.get("specVersion", "3.0.0"),
            "created": now,
            "createdBy": primary_creation.get("createdBy", []),
            "createdUsing": primary_creation.get("createdUsing", []),
            "comment": "<text>Merged by report-aggregator.</text>",
        })

        for node_type in ("Tool", "Person"):
            if node_type in self._primary_meta:
                meta_node = copy.deepcopy(self._primary_meta[node_type])
                meta_node.pop("@id", None)
                output_nodes.append(meta_node)
                spdx_id = meta_node.get("spdxId")
                if spdx_id:
                    element_ids.append(spdx_id)

        packages: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        licenses: list[dict[str, Any]] = []

        for entry in entries:
            data = copy.deepcopy(entry.data)
            satellites = data.pop("_satellites", [])
            if entry.kind == EntryKind.PACKAGE:
                packages.append(data)
            elif entry.kind == EntryKind.FILE:
                files.append(data)
            elif entry.kind == EntryKind.LICENSE_TEXT:
                licenses.append(data)

            node_id = data.get("spdxId")
            if node_id and node_id not in seen_ids:
                seen_ids.add(node_id)
                output_nodes.append(data)
                if entry.kind in (EntryKind.PACKAGE, EntryKind.FILE):
                    element_ids.append(node_id)

            for sat in satellites:
                sat_id = sat.get("spdxId") or sat.get("@id")
                if sat_id and sat_id in seen_ids:
                    continue
                if sat.get("type") == "Relationship":
                    relationships.append(sat)
                else:
                    output_nodes.append(sat)
                if sat_id:
                    seen_ids.add(sat_id)

        document_id = "https://spdx.org/rdf/3.0.0/terms/Core/SpdxDocument#SpdxRef-DOCUMENT"
        doc_name = packages[0].get("name", "Merged Report") if packages else "Merged Report"
        output_nodes.append({
            "type": "SpdxDocument",
            "spdxId": document_id,
            "creationInfo": creation_info_id,
            "name": doc_name,
            "profileConformance": [
                "core", "software", "simpleLicensing", "expandedLicensing",
            ],
            "element": element_ids,
        })

        for rel in relationships:
            rel_id = rel.get("spdxId")
            if rel_id and rel_id not in seen_ids:
                output_nodes.append(rel)
                seen_ids.add(rel_id)

        if "PackageVerificationCode" in self._primary_meta and packages:
            pvc = copy.deepcopy(self._primary_meta["PackageVerificationCode"])
            output_nodes.append(pvc)

        return {"nodes": output_nodes}

    def render(self, doc: dict[str, Any]) -> bytes:
        return json.dumps(doc["nodes"], indent=2).encode("utf-8")
