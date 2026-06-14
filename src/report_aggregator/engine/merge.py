"""Core merge engine — the heart of the report aggregator.

Implements the format-agnostic merge loop from architecture §5:
  Step 1: Collect entries from all inputs
  Step 2: Group by identity key
  Step 3: Merge each bucket (union/conflict/first-writer)
  Step 4: Re-namespace local refs (graph formats only)
  Step 5: Record provenance
  Step 6: Assemble and render the output document
"""

from __future__ import annotations

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
from report_aggregator.engine.identity import make_namespaced_ref, rewrite_embedded_refs
from report_aggregator.engine.mapping import MappingConfig
from report_aggregator.engine.provenance import ProvenanceTracker


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


def merge_reports(
    adapter: FormatAdapter,
    inputs: list[InputFile],
    mapping: MappingConfig,
) -> MergeResult:
    """Run the full merge pipeline on N input reports.

    Args:
        adapter: Format-specific adapter implementing FormatAdapter.
        inputs: List of input files to merge.
        mapping: Parsed mapping configuration for the format.

    Returns:
        MergeResult with rendered output bytes and provenance tracker.
    """
    provenance = ProvenanceTracker(format_name=mapping.format_name)

    # -- Step 0: Load all inputs --
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

    # -- Step 1: Collect entries from all inputs --
    all_entries: list[Entry] = []
    for inp, doc in loaded_docs:
        for entry in adapter.entries(doc):
            entry.source_id = inp.source_id
            entry.identity_key = adapter.identity(entry)
            all_entries.append(entry)

    # -- Step 2: Group by identity --
    buckets: dict[str, list[Entry]] = defaultdict(list)
    for entry in all_entries:
        buckets[entry.identity_key].append(entry)

    # -- Step 3: Merge each bucket --
    merged_entries: list[Entry] = []
    license_alias_map: dict[str, str] = {}
    for identity_key, bucket in buckets.items():
        if len(bucket) == 1:
            # Unique entry — pass through
            entry = bucket[0]
            provenance.record_provenance(
                path=f"/{entry.kind.value}/{identity_key}",
                source_ids=[entry.source_id],
            )
            merged_entries.append(entry)
        else:
            # Duplicate — merge fields
            merged = _merge_bucket(bucket, mapping, provenance)
            merged_entries.append(merged)
            if bucket[0].kind == EntryKind.LICENSE_TEXT:
                winner_id = _license_id(bucket[0])
                if winner_id:
                    for entry in bucket[1:]:
                        loser_id = _license_id(entry)
                        if loser_id:
                            license_alias_map[loser_id] = winner_id

    # -- Step 4: Re-namespace local refs (graph formats only) --
    if mapping.category == "graph" and mapping.local_ref_field:
        # Redirect deduped-away license IDs to the surviving entry before namespacing
        if license_alias_map:
            for entry in merged_entries:
                if isinstance(entry.data, dict):
                    _rewrite_entry_refs(
                        entry.data, mapping.local_ref_field, license_alias_map
                    )

        remap: dict[str, str] = {}
        for inp, doc in loaded_docs:
            refs = adapter.local_refs(doc)
            for ref in refs:
                new_ref = make_namespaced_ref(ref, inp.input_index)
                remap[ref] = new_ref

        # Rewrite refs in merged entries — both the top-level ref field
        # and any embedded references (e.g. LicenseRef-* in LicenseConcluded).
        # We do NOT call adapter.rewrite_refs(doc, remap) on loaded_docs because
        # some adapters yield entries that share dict references with the doc,
        # which would cause double-prefixing.
        for entry in merged_entries:
            if isinstance(entry.data, dict):
                _rewrite_entry_refs(entry.data, mapping.local_ref_field, remap)

    # -- Step 5: Provenance already recorded in Step 3 --

    # -- Step 6: Assemble and render --
    metadata = {
        "inputs": [
            {"source_id": inp.source_id, "path": str(inp.path), "input_index": inp.input_index}
            for inp in inputs
        ],
    }
    assembled_doc = adapter.assemble(merged_entries, metadata)
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
    license_id = entry.data.get("LicenseID")
    return license_id if isinstance(license_id, str) else None


def _is_embeddable_ref(ref: str) -> bool:
    """Return True if this ref could appear embedded inside other strings.

    Only SPDX-style refs (SPDXRef-*, LicenseRef-*) can appear inside
    license expressions and other string fields. CDX bom-refs are simple
    integers/short tokens and should NOT be treated as embeddable.
    """
    return ref.startswith("SPDXRef-") or ref.startswith("LicenseRef-")


def _rewrite_entry_refs(
    data: dict[str, Any],
    local_ref_field: str,
    remap: dict[str, str],
) -> None:
    """Rewrite all refs in an entry's data dict using the remap table.

    Handles:
    - The top-level ref field (e.g. ``bom-ref``, ``SPDXID``) — exact match
    - Embedded refs in string values (e.g. ``LicenseRef-*`` in license expressions)
    - Refs inside lists of strings (e.g. ``LicenseInfoInFile``)

    Only refs that look like SPDX identifiers are replaced inside strings;
    short CDX bom-refs (e.g. ``"2"``) are only replaced as exact matches on
    the local_ref_field to avoid corrupting filenames and other data.
    """
    # Build a filtered remap for embedded refs — only SPDX-style refs
    embeddable_remap = {k: v for k, v in remap.items() if _is_embeddable_ref(k)}

    for key, value in data.items():
        if key == local_ref_field and isinstance(value, str):
            # Top-level ref field: exact match replacement
            if value in remap:
                data[key] = remap[value]
        elif isinstance(value, str):
            data[key] = _rewrite_string_refs(value, embeddable_remap)
        elif isinstance(value, list):
            data[key] = [
                _rewrite_string_refs(item, embeddable_remap)
                if isinstance(item, str)
                else item
                for item in value
            ]


def _rewrite_string_refs(text: str, remap: dict[str, str]) -> str:
    """Replace any known SPDX-style refs inside a string value."""
    return rewrite_embedded_refs(text, remap)


