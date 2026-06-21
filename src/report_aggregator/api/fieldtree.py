"""Field-tree builder for the transparent editable view.

Flattens a merged report's native document into a list of nodes, each with a
real RFC-6901 JSON Pointer ``path`` (so it can be edited via the RFC-6902 edit
layer), the value, and — where determinable — provenance ``sources`` and
``conflict`` information.

Provenance/conflict overlay
---------------------------
The engine records provenance with identity-based keys of the form
``/{kind}/{identity}`` and ``/{kind}/{identity}/{field}`` (see engine/merge.py),
which are NOT positional JSON Pointers. To map them onto the rendered document
we:

1. Ask the adapter for its entries and compute each entry's identity, building a
   map from the Python object id of each entry container to its identity key.
2. Walk the document; when we enter a container that is a known entry, its
   direct children are matched to provenance/conflicts by ``(identity, field)``,
   ignoring the ``kind`` prefix (kinds can shift between merge and reload, e.g.
   a promoted CycloneDX upload component).
"""

from __future__ import annotations

from typing import Any

from report_aggregator.engine.mapping import load_mapping
from report_aggregator.formats import get_adapter_registry

MAX_NODES = 20000


def _escape_token(token: str) -> str:
    """Escape a JSON Pointer reference token (RFC-6901)."""
    return token.replace("~", "~0").replace("/", "~1")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def load_adapter_and_doc(fmt: str, raw: bytes):
    """Load the adapter for ``fmt`` and parse ``raw`` into a native doc."""
    mapping = load_mapping(fmt)
    registry = get_adapter_registry()
    if fmt not in registry:
        raise ValueError(f"Adapter for '{fmt}' is not available")
    adapter = registry[fmt](mapping)
    doc = adapter.load(raw)
    return adapter, doc


def build_identity_map(adapter, doc) -> dict[int, str]:
    """Map id(entry_container) -> identity_key for dict-shaped entries."""
    identity_map: dict[int, str] = {}
    try:
        entries = list(adapter.entries(doc))
    except Exception:
        return identity_map
    for entry in entries:
        if not isinstance(entry.data, dict):
            continue
        try:
            identity_map[id(entry.data)] = adapter.identity(entry)
        except Exception:
            continue
    return identity_map


def _index_provenance(provenance: dict):
    """Build (identity, field|None) -> sources and -> conflict indexes."""
    prov_index: dict[tuple[str, str | None], list[str]] = {}
    conflict_index: dict[tuple[str, str | None], dict] = {}

    for path, sources in (provenance.get("field_provenance") or {}).items():
        ident, fieldname = _split_identity_path(path)
        if ident is not None:
            prov_index[(ident, fieldname)] = sources

    for conflict in provenance.get("conflicts") or []:
        ident, fieldname = _split_identity_path(conflict.get("path", ""))
        if ident is not None:
            conflict_index[(ident, fieldname)] = conflict

    return prov_index, conflict_index


def _split_identity_path(path: str) -> tuple[str | None, str | None]:
    """Parse ``/{kind}/{identity}[/{field}]`` -> (identity, field|None)."""
    parts = [p for p in path.split("/") if p != ""]
    if len(parts) < 2:
        return None, None
    identity = parts[1]
    field = "/".join(parts[2:]) if len(parts) > 2 else None
    return identity, field


def build_field_tree(fmt: str, raw: bytes, provenance: dict, max_nodes: int = MAX_NODES) -> dict:
    """Return ``{"nodes": [...], "sources": [...], "truncated": bool}``."""
    adapter, doc = load_adapter_and_doc(fmt, raw)
    identity_map = build_identity_map(adapter, doc)
    prov_index, conflict_index = _index_provenance(provenance)

    source_ids = [i.get("id") for i in (provenance.get("inputs") or []) if i.get("id")]

    nodes: list[dict] = []
    truncated = False

    def emit(node: dict) -> bool:
        nonlocal truncated
        if len(nodes) >= max_nodes:
            truncated = True
            return False
        nodes.append(node)
        return True

    def walk(value: Any, path: str, key: str | None, depth: int,
             parent_identity: str | None) -> None:
        if truncated:
            return

        node_identity = identity_map.get(id(value)) if isinstance(value, dict) else None

        # Resolve provenance/conflict for THIS node.
        sources = None
        conflict = None
        if parent_identity is not None and key is not None:
            sources = prov_index.get((parent_identity, key))
            conflict = conflict_index.get((parent_identity, key))
        elif node_identity is not None:
            sources = prov_index.get((node_identity, None))

        if _is_scalar(value):
            emit({
                "path": path,
                "key": key,
                "value": value,
                "valueType": type(value).__name__ if value is not None else "null",
                "isLeaf": True,
                "depth": depth,
                "sources": sources,
                "conflict": conflict,
            })
            return

        # Container node.
        if isinstance(value, dict):
            child_count = sum(1 for k in value if not str(k).startswith("_"))
        else:
            child_count = len(value)

        if not emit({
            "path": path,
            "key": key,
            "value": None,
            "valueType": "object" if isinstance(value, dict) else "array",
            "isLeaf": False,
            "depth": depth,
            "childCount": child_count,
            "sources": sources,
            "conflict": conflict,
        }):
            return

        active_identity = node_identity if node_identity is not None else None
        if isinstance(value, dict):
            for k, v in value.items():
                if str(k).startswith("_"):
                    continue
                walk(v, f"{path}/{_escape_token(str(k))}", str(k), depth + 1, active_identity)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}/{i}", str(i), depth + 1, active_identity)

    walk(doc, "", None, 0, None)

    return {"nodes": nodes, "sources": source_ids, "truncated": truncated}
