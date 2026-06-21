"""Per-aggregate workspace storage for the API service.

Each merge creates a workspace directory keyed by ``aggregate_id`` containing:

    <workspace>/<aggregate_id>/
        inputs/          original uploaded input files
        merged.<ext>     the merged report
        merged.provenance.json   provenance sidecar (engine-written)
        meta.json        API-level metadata (format, filenames, timestamps)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Output file extension per format.
FORMAT_EXTENSION = {
    "cyclonedx": ".json",
    "spdx2tv": ".spdx",
    "dep5": ".txt",
    "readmeoss": ".txt",
    "spdx3json": ".json",
    "clixml": ".xml",
}


def workspace_root() -> Path:
    """Return the root directory holding all aggregate workspaces."""
    env = os.environ.get("REPORT_AGGREGATOR_WORKSPACE")
    if env:
        root = Path(env)
    else:
        root = Path.cwd() / ".api_workspaces"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class InputMeta:
    source_id: str
    filename: str
    input_index: int


@dataclass
class AggregateMeta:
    aggregate_id: str
    format: str
    created_at: str
    output_filename: str
    inputs: list[InputMeta] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "aggregate_id": self.aggregate_id,
            "format": self.format,
            "created_at": self.created_at,
            "output_filename": self.output_filename,
            "inputs": [asdict(i) for i in self.inputs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AggregateMeta":
        return cls(
            aggregate_id=data["aggregate_id"],
            format=data["format"],
            created_at=data["created_at"],
            output_filename=data["output_filename"],
            inputs=[InputMeta(**i) for i in data.get("inputs", [])],
        )


def aggregate_dir(aggregate_id: str) -> Path:
    return workspace_root() / aggregate_id


def inputs_dir(aggregate_id: str) -> Path:
    return aggregate_dir(aggregate_id) / "inputs"


def merged_path(aggregate_id: str, meta: AggregateMeta) -> Path:
    return aggregate_dir(aggregate_id) / meta.output_filename


def sidecar_path(aggregate_id: str, meta: AggregateMeta) -> Path:
    merged = merged_path(aggregate_id, meta)
    return merged.parent / f"{merged.stem}.provenance.json"


def meta_path(aggregate_id: str) -> Path:
    return aggregate_dir(aggregate_id) / "meta.json"


def write_meta(meta: AggregateMeta) -> None:
    meta_path(meta.aggregate_id).write_text(
        json.dumps(meta.to_dict(), indent=2), encoding="utf-8"
    )


def read_meta(aggregate_id: str) -> AggregateMeta | None:
    path = meta_path(aggregate_id)
    if not path.exists():
        return None
    return AggregateMeta.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_aggregate_ids() -> list[str]:
    root = workspace_root()
    ids = []
    for child in root.iterdir():
        if child.is_dir() and (child / "meta.json").exists():
            ids.append(child.name)
    return ids


def load_provenance(aggregate_id: str, meta: AggregateMeta) -> dict:
    """Load the provenance sidecar as a raw dict."""
    path = sidecar_path(aggregate_id, meta)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
