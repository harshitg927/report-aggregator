# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Disk + in-process cache for built field trees.

Field-tree construction parses the full merged report. Caching the flattened
result (keyed on merged output + provenance sidecar signatures) makes repeat
/details-page loads near-instant, matching the diffview cache strategy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from report_aggregator.api import diffview, fieldtree, storage
from report_aggregator.api.storage import AggregateMeta

FIELD_TREE_VERSION = 1

# In-process cache keyed by (cache_path, mtime_ns).
_TREE_CACHE: dict[tuple[str, int], dict] = {}


def _file_signature(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}-{st.st_mtime_ns}"


def _signature_hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def cache_path(
    aggregate_id: str,
    merged: Path,
    sidecar: Path,
    max_nodes: int = fieldtree.MAX_NODES,
) -> Path:
    """Return the on-disk cache path for the current merged + sidecar signatures."""
    h = _signature_hash(
        "fields",
        str(merged),
        _file_signature(merged),
        str(sidecar),
        _file_signature(sidecar),
        str(max_nodes),
    )
    return diffview.cache_dir(aggregate_id) / f"fields-{h}.json"


def get_or_build(
    aggregate_id: str,
    meta: AggregateMeta,
    prov: dict | None = None,
    max_nodes: int = fieldtree.MAX_NODES,
) -> dict:
    """Return a cached field tree, building and persisting it on first use."""
    merged = storage.merged_path(aggregate_id, meta)
    sidecar = storage.sidecar_path(aggregate_id, meta)
    if prov is None:
        prov = storage.load_provenance(aggregate_id, meta)

    path = cache_path(aggregate_id, merged, sidecar, max_nodes)

    if path.exists():
        key = (str(path), path.stat().st_mtime_ns)
        cached = _TREE_CACHE.get(key)
        if cached is not None:
            return cached
        tree = json.loads(path.read_text(encoding="utf-8"))
        if tree.get("version") == FIELD_TREE_VERSION:
            _TREE_CACHE[key] = tree
            return tree

    raw = merged.read_bytes()
    tree = fieldtree.build_field_tree(meta.format, raw, prov, max_nodes=max_nodes)
    payload = {
        "version": FIELD_TREE_VERSION,
        "nodes": tree["nodes"],
        "sources": tree["sources"],
        "truncated": tree["truncated"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    _TREE_CACHE[(str(path), path.stat().st_mtime_ns)] = payload
    return payload


def warm(aggregate_id: str, meta: AggregateMeta) -> dict:
    """Build and persist the field tree cache (e.g. after merge or edit)."""
    return get_or_build(aggregate_id, meta)
