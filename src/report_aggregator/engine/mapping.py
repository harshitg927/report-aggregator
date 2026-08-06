# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""TOML mapping loader — reads per-format mapping files and validates required keys."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any


class MappingError(Exception):
    """Raised when a mapping file is missing, malformed, or has invalid keys."""


@dataclass(frozen=True)
class MappingConfig:
    """Parsed and validated mapping configuration for a single format.

    Attributes:
        format_name: The format identifier (e.g. "cyclonedx", "spdx2tv").
        category: "graph" or "stanza" — determines whether ref-rewiring is applied.
        entries_path: Dot-path to the entries collection in the native structure.
        identity_fields: Fields used to compute entry identity (SHA-1 etc.).
        local_ref_field: The field holding document-local IDs (bom-ref / SPDXID).
        union_fields: Fields merged via set-union across inputs.
        conflict_fields: Fields checked for disagreement (first-writer + conflict entry).
        raw: The full raw TOML dict for format-specific adapter access.
    """

    format_name: str
    category: str
    entries_path: str
    identity_fields: list[str] = field(default_factory=list)
    local_ref_field: str = ""
    union_fields: list[str] = field(default_factory=list)
    conflict_fields: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def get_mappings_dir() -> Path:
    """Return the path to the mappings directory shipped inside the package.

    Resolved via ``importlib.resources`` so it works from an installed wheel
    (including ``pip install --target`` layouts) rather than assuming a
    repo-root ``mappings/`` directory. ``report_aggregator`` installs unzipped,
    so this always resolves to a real filesystem path.
    """
    return Path(str(resources.files("report_aggregator").joinpath("mappings")))


def load_mapping(format_name: str, mappings_dir: Path | None = None) -> MappingConfig:
    """Load and validate a mapping file for the given format.

    Args:
        format_name: Format identifier matching a ``mappings/{format_name}.toml`` file.
        mappings_dir: Override the default mappings directory (useful for testing).

    Returns:
        A validated ``MappingConfig`` instance.

    Raises:
        MappingError: If the file is missing, cannot be parsed, or lacks required keys.
    """
    directory = mappings_dir or get_mappings_dir()
    toml_path = directory / f"{format_name}.toml"

    if not toml_path.exists():
        raise MappingError(
            f"Mapping file not found: {toml_path}. "
            f"Available mappings: {[p.stem for p in directory.glob('*.toml')]}"
        )

    try:
        raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise MappingError(f"Invalid TOML in {toml_path}: {exc}") from exc

    # The TOML file should have a single top-level key matching the format name
    if format_name not in raw:
        # Try the first key as a fallback
        keys = list(raw.keys())
        if len(keys) == 1:
            section = raw[keys[0]]
        else:
            raise MappingError(
                f"Mapping file {toml_path} must have a [{format_name}] section. "
                f"Found sections: {keys}"
            )
    else:
        section = raw[format_name]

    # Validate required keys
    if "category" not in section:
        raise MappingError(f"Mapping [{format_name}] missing required key 'category'")

    category = section["category"]
    if category not in ("graph", "stanza"):
        raise MappingError(
            f"Mapping [{format_name}] category must be 'graph' or 'stanza', got '{category}'"
        )

    # Build identity fields from various possible keys
    identity_fields = []
    for key in ("file_identity", "upload_identity", "package_identity"):
        if key in section:
            val = section[key]
            if isinstance(val, list):
                identity_fields.extend(val)
            else:
                identity_fields.append(val)

    return MappingConfig(
        format_name=format_name,
        category=category,
        entries_path=section.get("entries_path", ""),
        identity_fields=identity_fields,
        local_ref_field=section.get("local_ref_field", ""),
        union_fields=section.get("union_fields", []),
        conflict_fields=section.get("conflict_fields", []),
        raw=section,
    )
