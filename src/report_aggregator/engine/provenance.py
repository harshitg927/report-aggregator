# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Provenance sidecar — tracks which input contributed each field and records conflicts."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .patch import Patch


@dataclass
class InputInfo:
    """Metadata about one input report fed into the merge."""

    id: str
    path: str
    input_index: int
    fossology_upload_hash_sha1: str = ""


@dataclass
class ConflictEntry:
    """A recorded disagreement between inputs for a specific field."""

    path: str
    values: dict[str, Any]  # source_id → value
    resolution: str  # e.g. "first-writer"
    chosen: Any


@dataclass
class EditEntry:
    """User edit recorded in provenance sidecar."""

    who: str  # user@example.com or username
    when: str  # ISO 8601 timestamp
    patch: Patch  # The RFC-6902 operation
    reason: str = ""  # Optional: why the edit was made
    summary: str = ""  # Short human-readable change for UI/CLI display


@dataclass
class ProvenanceTracker:
    """Accumulates provenance information during a merge operation.

    Produces the ``.provenance.json`` sidecar alongside the merged report.
    Schema matches architecture §6.1.
    """

    format_name: str
    aggregate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    inputs: list[InputInfo] = field(default_factory=list)
    field_provenance: dict[str, list[str]] = field(default_factory=dict)
    conflicts: list[ConflictEntry] = field(default_factory=list)
    edits: list[EditEntry] = field(default_factory=list)  # Phase 3: edit history

    # -- Recording methods --

    def add_input(
        self,
        source_id: str,
        path: str,
        input_index: int,
        upload_hash_sha1: str = "",
    ) -> None:
        """Register an input report."""
        self.inputs.append(
            InputInfo(
                id=source_id,
                path=path,
                input_index=input_index,
                fossology_upload_hash_sha1=upload_hash_sha1,
            )
        )

    def record_provenance(self, path: str, source_ids: list[str]) -> None:
        """Record which input(s) contributed a value at the given path.

        Args:
            path: JSON Pointer path into the merged native structure.
            source_ids: List of input source IDs that contributed this value.
        """
        self.field_provenance[path] = source_ids

    def record_conflict(
        self,
        path: str,
        values_by_source: dict[str, Any],
        resolution: str,
        chosen: Any,
    ) -> None:
        """Record a field-level disagreement between inputs.

        Args:
            path: JSON Pointer path to the conflicting field.
            values_by_source: Mapping of source_id → value for each disagreeing input.
            resolution: Policy name (e.g. "first-writer").
            chosen: The value that was selected for the merged output.
        """
        self.conflicts.append(
            ConflictEntry(
                path=path,
                values=values_by_source,
                resolution=resolution,
                chosen=chosen,
            )
        )

    def add_edit(
        self,
        who: str,
        patch: Patch,
        reason: str = "",
        summary: str = "",
    ) -> None:
        """Add a user edit to the provenance history.

        Args:
            who: User identifier (email or username)
            patch: The RFC-6902 patch operation
            reason: Optional explanation for the edit
            summary: Optional short description of what changed (for display)
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.edits.append(
            EditEntry(
                who=who,
                when=timestamp,
                patch=patch,
                reason=reason,
                summary=summary,
            )
        )

    def get_edits(self) -> list[EditEntry]:
        """Get all edits from the provenance history.

        Returns:
            List of edit entries
        """
        return self.edits

    # -- Serialization --

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict matching the §6.1 sidecar schema."""
        return {
            "aggregate_id": self.aggregate_id,
            "format": self.format_name,
            "created_at": self.created_at,
            "inputs": [
                {
                    "id": inp.id,
                    "path": inp.path,
                    "input_index": inp.input_index,
                    "fossology_upload_hash_sha1": inp.fossology_upload_hash_sha1,
                }
                for inp in self.inputs
            ],
            "field_provenance": self.field_provenance,
            "conflicts": [
                {
                    "path": c.path,
                    "values": c.values,
                    "resolution": c.resolution,
                    "chosen": c.chosen,
                }
                for c in self.conflicts
            ],
            "edits": [
                {
                    "who": e.who,
                    "when": e.when,
                    "patch": {
                        "op": e.patch.op,
                        "path": e.patch.path,
                        "value": e.patch.value,
                        "from": e.patch.from_,
                    },
                    "reason": e.reason,
                    "summary": e.summary,
                }
                for e in self.edits
            ],
        }

    def write_sidecar(self, output_path: Path) -> Path:
        """Write the provenance sidecar JSON next to the merged output.

        Args:
            output_path: Path to the merged report file.

        Returns:
            Path to the written sidecar file.
        """
        sidecar_path = output_path.parent / f"{output_path.stem}.provenance.json"
        sidecar_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return sidecar_path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceTracker:
        """Deserialize from a sidecar dict."""
        tracker = cls(
            format_name=data["format"],
            aggregate_id=data["aggregate_id"],
            created_at=data["created_at"],
        )
        for inp in data.get("inputs", []):
            tracker.add_input(
                source_id=inp["id"],
                path=inp["path"],
                input_index=inp["input_index"],
                upload_hash_sha1=inp.get("fossology_upload_hash_sha1", ""),
            )
        tracker.field_provenance = data.get("field_provenance", {})
        for c in data.get("conflicts", []):
            tracker.record_conflict(
                path=c["path"],
                values_by_source=c["values"],
                resolution=c["resolution"],
                chosen=c["chosen"],
            )
        # Deserialize edits
        for e in data.get("edits", []):
            patch_data = e["patch"]
            patch = Patch(
                op=patch_data["op"],
                path=patch_data["path"],
                value=patch_data.get("value"),
                from_=patch_data.get("from", ""),
            )
            tracker.edits.append(
                EditEntry(
                    who=e["who"],
                    when=e["when"],
                    patch=patch,
                    reason=e.get("reason", ""),
                    summary=e.get("summary", ""),
                )
            )
        return tracker
