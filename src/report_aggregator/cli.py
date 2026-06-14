"""CLI entry point for report-aggregator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from report_aggregator.engine.mapping import MappingError, load_mapping


# Format auto-detection by file extension
_EXT_FORMAT_MAP = {
    ".json": "cyclonedx",
    ".spdx": "spdx2tv",
}

# Adapter registry — populated as adapters are implemented
_ADAPTER_REGISTRY: dict[str, type] = {}


def _detect_format(paths: list[Path]) -> str | None:
    """Attempt to detect the report format from file extensions.

    Returns the format name if all inputs share a recognizable extension,
    or None if detection fails.
    """
    formats = set()
    for p in paths:
        fmt = _EXT_FORMAT_MAP.get(p.suffix.lower())
        if fmt:
            formats.add(fmt)

    if len(formats) == 1:
        return formats.pop()
    return None


def _register_adapters() -> None:
    """Lazily register available adapters."""
    # Will be populated as adapters are implemented in Phase 1c/1b
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


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="report-aggregator",
        description="Merge N FOSSology-generated reports into one deduplicated report.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # merge subcommand
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
        choices=["cyclonedx", "spdx2tv"],
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

    # Validate input files exist
    for p in input_paths:
        if not p.exists():
            print(f"Error: Input file not found: {p}", file=sys.stderr)
            return 1

    # Auto-detect format if not specified
    if format_name is None:
        format_name = _detect_format(input_paths)
        if format_name is None:
            print(
                "Error: Cannot auto-detect format. Use --format to specify.",
                file=sys.stderr,
            )
            return 1
        print(f"Auto-detected format: {format_name}")

    # Load mapping
    try:
        mapping = load_mapping(format_name)
    except MappingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Check adapter availability
    _register_adapters()
    if format_name not in _ADAPTER_REGISTRY:
        print(
            f"Error: Adapter for '{format_name}' is not yet implemented.\n"
            f"Available adapters: {list(_ADAPTER_REGISTRY.keys()) or ['(none)']}\n"
            f"Mapping loaded successfully from: mappings/{format_name}.toml",
            file=sys.stderr,
        )
        return 1

    # Instantiate adapter and run merge
    adapter_cls = _ADAPTER_REGISTRY[format_name]
    adapter = adapter_cls(mapping)

    # Import engine and run merge
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

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result.output_bytes)
    sidecar_path = result.provenance.write_sidecar(output_path)

    print(f"Merged {len(input_paths)} reports → {output_path}")
    print(f"Provenance sidecar → {sidecar_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
