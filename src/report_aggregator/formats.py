"""Shared format detection and adapter registry.

Factored out of ``cli.py`` so both the CLI and the API service use the same
detection rules and adapter loading logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

SUPPORTED_FORMATS = [
    "cyclonedx",
    "spdx2tv",
    "dep5",
    "readmeoss",
    "spdx3json",
    "clixml",
]

# Format auto-detection by file extension (non-ambiguous types).
_EXT_FORMAT_MAP = {
    ".spdx": "spdx2tv",
}


def sniff_format(path: Path) -> str | None:
    """Detect format from filename pattern or file content."""
    name = path.name
    if name.startswith("DEP5_"):
        return "dep5"
    if name.startswith("ReadMe_OSS_"):
        return "readmeoss"
    if name.startswith("SPDX3JSON_"):
        return "spdx3json"
    if name.startswith("CYCLONEDX_JSON_"):
        return "cyclonedx"
    if name.startswith("CLIXML_"):
        return "clixml"

    try:
        head = path.read_bytes()[:4096].decode("utf-8", errors="replace")
    except OSError:
        return _EXT_FORMAT_MAP.get(path.suffix.lower())

    if head.startswith("Format: https://www.debian.org/doc/packaging-manuals/copyright-format/"):
        return "dep5"
    if head.lstrip().startswith("=" * 20):
        return "readmeoss"

    suffix = path.suffix.lower()
    if suffix == ".json":
        stripped = head.lstrip()
        if stripped.startswith("["):
            return "spdx3json"
        if '"bomFormat"' in head or '"specVersion"' in head:
            return "cyclonedx"

    if suffix == ".xml":
        if "<ComponentLicenseInformation" in head:
            return "clixml"

    if suffix == ".txt":
        return None

    return _EXT_FORMAT_MAP.get(suffix)


class FormatDetectionError(Exception):
    """Raised when a set of inputs cannot be resolved to a single format."""


def detect_format(paths: list[Path], *, stream=sys.stderr) -> str | None:
    """Attempt to detect the report format from filenames and content.

    Returns the format name if all inputs agree on a single non-None format,
    otherwise None. Diagnostic messages are written to ``stream``.
    """
    formats: list[str | None] = [sniff_format(p) for p in paths]

    if None in formats:
        return None

    unique_formats = set(formats)
    if len(unique_formats) == 1:
        return formats[0]

    print("Error: Input format mismatch detected:", file=stream)
    for p, fmt in zip(paths, formats):
        print(f"  {p}: {fmt}", file=stream)
    return None


def format_mismatches(paths: list[Path], expected: str) -> list[tuple[Path, str]]:
    """Return (path, detected) pairs whose detected format conflicts with ``expected``."""
    detected = [(p, sniff_format(p)) for p in paths]
    return [(p, f) for p, f in detected if f and f != expected]


def get_adapter_registry() -> dict[str, type]:
    """Lazily import and return the available format adapters."""
    registry: dict[str, type] = {}

    try:
        from report_aggregator.adapters.cyclonedx import CycloneDXAdapter

        registry["cyclonedx"] = CycloneDXAdapter
    except ImportError:
        pass
    try:
        from report_aggregator.adapters.spdx2tv import SPDX2TVAdapter

        registry["spdx2tv"] = SPDX2TVAdapter
    except ImportError:
        pass
    try:
        from report_aggregator.adapters.dep5 import DEP5Adapter

        registry["dep5"] = DEP5Adapter
    except ImportError:
        pass
    try:
        from report_aggregator.adapters.readmeoss import ReadMeOSSAdapter

        registry["readmeoss"] = ReadMeOSSAdapter
    except ImportError:
        pass
    try:
        from report_aggregator.adapters.spdx3json import SPDX3JSONAdapter

        registry["spdx3json"] = SPDX3JSONAdapter
    except ImportError:
        pass
    try:
        from report_aggregator.adapters.clixml import CLIXMLAdapter

        registry["clixml"] = CLIXMLAdapter
    except ImportError:
        pass

    return registry
