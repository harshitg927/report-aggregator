"""CLI entry point for report-aggregator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report_aggregator.engine.mapping import MappingError, load_mapping


# Format auto-detection by file extension (non-ambiguous types)
_EXT_FORMAT_MAP = {
    ".spdx": "spdx2tv",
}

# Adapter registry — populated as adapters are implemented
_ADAPTER_REGISTRY: dict[str, type] = {}


def _sniff_format(path: Path) -> str | None:
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

    if suffix == ".txt":
        return None

    return _EXT_FORMAT_MAP.get(suffix)


def _detect_format(paths: list[Path]) -> str | None:
    """Attempt to detect the report format from filenames and content."""
    formats: list[str | None] = []
    for p in paths:
        fmt = _sniff_format(p)
        formats.append(fmt)

    # Check if any format is None
    if None in formats:
        return None

    # Check if all formats are the same
    unique_formats = set(formats)
    if len(unique_formats) == 1:
        return formats[0]
    
    # Format mismatch detected
    print(
        "Error: Input format mismatch detected:",
        file=sys.stderr
    )
    for p, fmt in zip(paths, formats):
        print(f"  {p}: {fmt}", file=sys.stderr)
    return None


def _register_adapters() -> None:
    """Lazily register available adapters."""
    try:
        from report_aggregator.adapters.cyclonedx import CycloneDXAdapter

        _ADAPTER_REGISTRY["cyclonedx"] = CycloneDXAdapter
    except ImportError:
        pass

    try:
        from report_aggregator.adapters.spdx2tv import SPDX2TVAdapter

        _ADAPTER_REGISTRY["spdx2tv"] = SPDX2TVAdapter
    except ImportError:
        pass

    try:
        from report_aggregator.adapters.dep5 import DEP5Adapter

        _ADAPTER_REGISTRY["dep5"] = DEP5Adapter
    except ImportError:
        pass

    try:
        from report_aggregator.adapters.readmeoss import ReadMeOSSAdapter

        _ADAPTER_REGISTRY["readmeoss"] = ReadMeOSSAdapter
    except ImportError:
        pass

    try:
        from report_aggregator.adapters.spdx3json import SPDX3JSONAdapter

        _ADAPTER_REGISTRY["spdx3json"] = SPDX3JSONAdapter
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="report-aggregator",
        description="Merge N FOSSology-generated reports into one deduplicated report.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    merge_parser = subparsers.add_parser(
        "merge",
        help="Merge multiple reports into one",
    )
    merge_parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input report files to merge",
    )
    merge_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for the merged report",
    )
    merge_parser.add_argument(
        "--format",
        choices=["cyclonedx", "spdx2tv", "dep5", "readmeoss", "spdx3json"],
        default=None,
        help="Report format (auto-detected from extension if omitted)",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "merge":
        return _handle_merge(args)

    return 0


def _handle_merge(args: argparse.Namespace) -> int:
    """Handle the 'merge' subcommand."""
    input_paths: list[Path] = args.inputs
    output_path: Path = args.output
    format_name: str | None = args.format

    for p in input_paths:
        if not p.exists():
            print(f"Error: Input file not found: {p}", file=sys.stderr)
            return 1

    if format_name is None:
        format_name = _detect_format(input_paths)
        if format_name is None:
            print(
                "Error: Cannot auto-detect format. Use --format to specify.",
                file=sys.stderr,
            )
            return 1
        print(f"Auto-detected format: {format_name}")
    else:
        # Validate all inputs match the explicitly provided format
        detected_formats = [(p, _sniff_format(p)) for p in input_paths]
        mismatches = [(p, f) for p, f in detected_formats if f and f != format_name]
        if mismatches:
            print(
                f"Error: Format mismatch. Expected all files to be '{format_name}', but found:",
                file=sys.stderr
            )
            for p, f in mismatches:
                print(f"  {p}: {f}", file=sys.stderr)
            return 1

    try:
        mapping = load_mapping(format_name)
    except MappingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _register_adapters()
    if format_name not in _ADAPTER_REGISTRY:
        print(
            f"Error: Adapter for '{format_name}' is not yet implemented.\n"
            f"Available adapters: {list(_ADAPTER_REGISTRY.keys()) or ['(none)']}\n"
            f"Mapping loaded successfully from: mappings/{format_name}.toml",
            file=sys.stderr,
        )
        return 1

    adapter_cls = _ADAPTER_REGISTRY[format_name]
    adapter = adapter_cls(mapping)

    from report_aggregator.engine.merge import InputFile, merge_reports

    inputs = [
        InputFile(
            path=p,
            input_index=i,
            source_id=p.stem,
        )
        for i, p in enumerate(input_paths)
    ]

    try:
        result = merge_reports(adapter=adapter, inputs=inputs, mapping=mapping)
    except Exception as exc:
        print(f"Error during merge: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result.output_bytes)
    sidecar_path = result.provenance.write_sidecar(output_path)

    print(f"Merged {len(input_paths)} reports → {output_path}")
    print(f"Provenance sidecar → {sidecar_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
