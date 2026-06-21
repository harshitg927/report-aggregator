"""Core merge engine — the heart of the report aggregator.

Implements the format-agnostic merge loop from architecture §5:
  Step 1: Collect entries from all inputs
  Step 2: Group by identity key
  Step 3: Merge each bucket (union/conflict/first-writer)
  Step 4: Re-namespace local refs (graph formats only)
  Step 5: Record provenance
  Step 6: Assemble and render the output document
  Step 7: Replay edits (Phase 3)
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from report_aggregator.adapters.base import Entry, EntryKind, FormatAdapter
from report_aggregator.engine.conflict import (
    FieldPolicy,
    merge_conflict_field,
    merge_first_writer_field,
    merge_union_field,
)
from report_aggregator.engine.identity import (
    make_namespaced_ref,
)
from report_aggregator.engine.mapping import MappingConfig
from report_aggregator.engine.patch import PatchError, apply_patches
from report_aggregator.engine.provenance import ProvenanceTracker

logger = logging.getLogger(__name__)


@dataclass
class InputFile:
    """An input report file to be merged."""

    path: Path
    input_index: int
    source_id: str


@dataclass
class MergeResult:
    """Result of a merge operation."""

    output_bytes: bytes
    provenance: ProvenanceTracker


def load_provenance_if_exists(output_path: Path) -> ProvenanceTracker | None:
    """Load existing provenance sidecar if it exists.

    Args:
        output_path: Path where the merged output will be written

    Returns:
        ProvenanceTracker if sidecar exists, None otherwise
    """
    sidecar_path = output_path.parent / f"{output_path.stem}.provenance.json"
    if not sidecar_path.exists():
        return None

    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        return ProvenanceTracker.from_dict(data)
    except Exception as e:
        logger.warning(f"Failed to load existing provenance from {sidecar_path}: {e}")
        return None


def merge_reports(
    adapter: FormatAdapter,
    inputs: list[InputFile],
    mapping: MappingConfig,
    output_path: Path | None = None,
) -> MergeResult:
    """Run the full merge pipeline on N input reports.

    Args:
        adapter: Format-specific adapter implementing FormatAdapter.
        inputs: List of input files to merge.
        mapping: Parsed mapping configuration for the format.
        output_path: Optional output path to check for existing edits.

    Returns:
        MergeResult with rendered output bytes and provenance tracker.
    """
    provenance = ProvenanceTracker(format_name=mapping.format_name)

    # -- Step 0a: Check for existing provenance with edits --
    existing_provenance = None
    if output_path:
        existing_provenance = load_provenance_if_exists(output_path)

    # -- Step 0b: Load all inputs --
    loaded_docs: list[tuple[InputFile, Any]] = []
    for inp in inputs:
        raw = inp.path.read_bytes()
        doc = adapter.load(raw)
        loaded_docs.append((inp, doc))
        provenance.add_input(
            source_id=inp.source_id,
            path=str(inp.path),
            input_index=inp.input_index,
        )

    # -- Step 0c: Per-input local-ref namespacing (graph formats only) --
    # Each input independently uses SPDXRef-upload<id> / bom-ref / IRI values
    # that COLLIDE across documents produced by different FOSSology instances.
    # Namespace every input's local refs with its own input-index prefix BEFORE
    # grouping, so two *distinct* entries that merely share an ID across inputs
    # stay distinct (and don't overwrite each other in a shared remap table).
    #
    # This is routed through the adapter's own rewrite_refs() so that
    # format-specific cross-references are rewired correctly in the same pass:
    #   - SPDX 2 `relationships` + license expressions
    #   - SPDX 3 satellite nodes (Annotation/Relationship subjects)
    #   - CDX bom-ref values
    # Identity (Step 1) is checksum/text based and is unaffected by this.
    if mapping.category == "graph" and mapping.local_ref_field:
        for inp, doc in loaded_docs:
            remap = {
                ref: make_namespaced_ref(ref, inp.input_index)
                for ref in adapter.local_refs(doc)
            }
            if remap:
                adapter.rewrite_refs(doc, remap)

    # -- Step 1: Collect entries from all inputs --
    source_order = {inp.source_id: inp.input_index for inp in inputs}
    all_entries: list[Entry] = []
    for inp, doc in loaded_docs:
        for entry in adapter.entries(doc):
            entry.source_id = inp.source_id
            entry.identity_key = adapter.identity(entry)
            if not entry.identity_key:
                name = entry.data.get("name") or entry.data.get("FileName") or entry.data.get("SPDXID") or "unknown"
                raise ValueError(
                    f"Cannot compute identity for {entry.kind.value} '{name}' from {inp.source_id}: "
                    f"missing required checksums/hashes"
                )
            all_entries.append(entry)

    if not all_entries:
        paths = ", ".join(str(inp.path) for inp in inputs)
        raise ValueError(
            f"No mergeable entries found in input report(s): {paths}. "
            f"All inputs appear empty or contain no recognizable entries."
        )

    # -- Step 2: Group by (kind, identity) --
    # Keyed by kind as well as identity so a package and a file that happen to
    # share a checksum (or a license block whose md5 collides with a hash) are
    # never merged into a single entry.
    buckets: dict[tuple[EntryKind, str], list[Entry]] = defaultdict(list)
    for entry in all_entries:
        buckets[(entry.kind, entry.identity_key)].append(entry)

    # -- Step 3: Merge each bucket --
    merged_entries: list[Entry] = []
    # Maps the local-ref ID of every deduped-away entry → the surviving
    # entry's ID, so dangling cross-references (relationships, license
    # expressions, satellites) can be redirected to the survivor in Step 4.
    dedup_alias_map: dict[str, str] = {}
    for (_kind, identity_key), bucket in buckets.items():
        if len(bucket) == 1:
            # Unique entry — pass through
            entry = bucket[0]
            provenance.record_provenance(
                path=f"/{entry.kind.value}/{identity_key}",
                source_ids=[entry.source_id],
            )
            merged_entries.append(entry)
        else:
            sorted_bucket = sorted(
                bucket,
                key=lambda e: source_order.get(e.source_id, 999),
            )
            merged = _merge_bucket(sorted_bucket, mapping, provenance)
            merged_entries.append(merged)
            if bucket[0].kind == EntryKind.LICENSE_TEXT:
                if mapping.raw.get("license_text_naming") == "last-writer":
                    _apply_last_writer_license_name(merged, sorted_bucket)
                winner_id = _license_id(merged)
                if winner_id:
                    for entry in sorted_bucket:
                        loser_id = _license_id(entry)
                        if loser_id and loser_id != winner_id:
                            dedup_alias_map[loser_id] = winner_id
            elif mapping.local_ref_field and isinstance(merged.data, dict):
                winner_id = merged.data.get(mapping.local_ref_field)
                if winner_id:
                    for entry in sorted_bucket:
                        if not isinstance(entry.data, dict):
                            continue
                        loser_id = entry.data.get(mapping.local_ref_field)
                        if loser_id and loser_id != winner_id:
                            dedup_alias_map[loser_id] = winner_id

    # -- Step 3.5: Optional adapter-specific conflict detection (e.g. DEP5 glob overlap) --
    if hasattr(adapter, "detect_conflicts"):
        for conflict in adapter.detect_conflicts(all_entries):
            provenance.record_conflict(
                path=conflict.path,
                values_by_source=conflict.values,
                resolution=conflict.resolution,
                chosen=conflict.chosen,
            )

    # -- Step 4: Re-namespacing of local refs already happened per-input in
    # Step 0c. The only remaining ref work is redirecting references that
    # pointed at deduped-away entries to their survivor — done in Step 6
    # (after assemble) via the adapter's rewrite_refs().

    # -- Step 5: Provenance already recorded in Step 3 --

    # -- Step 6: Assemble and render --
    metadata = {
        "inputs": [
            {"source_id": inp.source_id, "path": str(inp.path), "input_index": inp.input_index}
            for inp in inputs
        ],
    }
    if loaded_docs:
        _, first_doc = loaded_docs[0]
        if isinstance(first_doc, dict) and "_metadata_snapshot" in first_doc:
            metadata["primary_metadata"] = first_doc["_metadata_snapshot"]
        if isinstance(first_doc, dict) and "_primary_meta" in first_doc:
            metadata["primary_meta"] = first_doc["_primary_meta"]
    assembled_doc = adapter.assemble(merged_entries, metadata)

    # Redirect any references that pointed at deduped-away entries to the
    # surviving entry. Routed through the adapter so SPDX relationships,
    # license expressions and SPDX 3 satellites are all rewired consistently.
    if mapping.category == "graph" and dedup_alias_map:
        adapter.rewrite_refs(assembled_doc, dedup_alias_map)

    # -- Step 7: Replay edits from existing provenance (Phase 3) --
    if existing_provenance and existing_provenance.edits:
        logger.info(f"Replaying {len(existing_provenance.edits)} edit(s) from provenance")
        failed_patches = []

        for edit_entry in existing_provenance.edits:
            try:
                assembled_doc = apply_patches(assembled_doc, [edit_entry.patch])
                logger.debug(f"Applied edit: {edit_entry.patch.op} {edit_entry.patch.path}")
            except PatchError as e:
                logger.warning(
                    f"Skipping edit {edit_entry.patch.op} {edit_entry.patch.path}: {e}"
                )
                failed_patches.append((edit_entry, str(e)))

        if failed_patches:
            logger.warning(
                f"⚠ {len(failed_patches)} edit(s) failed to apply (structure may have changed):"
            )
            for edit_entry, error in failed_patches:
                logger.warning(f"  - {edit_entry.patch.path}: {error}")

        # Preserve edit history in new provenance
        provenance.edits = existing_provenance.edits

    output_bytes = adapter.render(assembled_doc)

    return MergeResult(output_bytes=output_bytes, provenance=provenance)


def _merge_bucket(
    bucket: list[Entry],
    mapping: MappingConfig,
    provenance: ProvenanceTracker,
) -> Entry:
    """Merge a bucket of entries with the same identity into one entry.

    Uses the mapping's field policies:
    - union_fields → set-union
    - conflict_fields → check for disagreement, first-writer wins
    - all other fields → first-writer wins
    """
    # Use the first entry as the base
    base = bucket[0]
    identity_key = base.identity_key
    base_path = f"/{base.kind.value}/{identity_key}"

    # Track all contributing sources
    all_sources = list(dict.fromkeys(e.source_id for e in bucket))
    provenance.record_provenance(base_path, all_sources)

    if not isinstance(base.data, dict):
        # Non-dict entries (unlikely but defensive) — just keep first
        return base

    # Merge field by field
    merged_data = dict(base.data)
    union_fields = set(mapping.union_fields)
    conflict_fields = set(mapping.conflict_fields)

    # Collect all unique field names from all entries in the bucket
    all_field_names: set[str] = set()
    for entry in bucket:
        if isinstance(entry.data, dict):
            all_field_names.update(entry.data.keys())

    for field_name in all_field_names:
        # Gather values from all entries that have this field
        values_with_sources: list[tuple[Any, str]] = []
        for entry in bucket:
            if isinstance(entry.data, dict) and field_name in entry.data:
                values_with_sources.append((entry.data[field_name], entry.source_id))

        if not values_with_sources:
            continue

        field_path = f"{base_path}/{field_name}"

        if field_name in union_fields:
            merged_value, sources = merge_union_field(values_with_sources)
            merged_data[field_name] = merged_value
            provenance.record_provenance(field_path, sources)

        elif field_name in conflict_fields:
            chosen, sources, conflict = merge_conflict_field(
                field_path, values_with_sources
            )
            merged_data[field_name] = chosen
            provenance.record_provenance(field_path, sources)
            if conflict:
                provenance.record_conflict(
                    path=conflict.path,
                    values_by_source=conflict.values,
                    resolution=conflict.resolution,
                    chosen=conflict.chosen,
                )

        else:
            # Default: first-writer wins
            chosen, sources = merge_first_writer_field(values_with_sources)
            merged_data[field_name] = chosen
            provenance.record_provenance(field_path, sources)

    return Entry(
        data=merged_data,
        kind=base.kind,
        source_id=",".join(all_sources),
        identity_key=identity_key,
    )


def _license_id(entry: Entry) -> str | None:
    """Return LicenseID from a license-text entry, if present."""
    if not isinstance(entry.data, dict):
        return None
    for key in ("LicenseID", "spdxId", "name"):
        license_id = entry.data.get(key)
        if isinstance(license_id, str) and license_id:
            return license_id
    return None


def _apply_last_writer_license_name(merged: Entry, bucket: list[Entry]) -> None:
    """Apply last-writer naming policy for deduplicated license text blocks."""
    if not isinstance(merged.data, dict):
        return
    last = bucket[-1].data
    if not isinstance(last, dict):
        return
    for key in ("LicenseID", "spdxId", "name"):
        val = last.get(key)
        if isinstance(val, str) and val:
            merged.data[key] = val
            return


