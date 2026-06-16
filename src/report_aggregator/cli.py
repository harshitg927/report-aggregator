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

    # Merge subcommand
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

    # Edit subcommand
    edit_parser = subparsers.add_parser(
        "edit",
        help="Apply an edit patch to a merged report",
    )
    edit_parser.add_argument(
        "merged_file",
        type=Path,
        help="Path to merged report file",
    )
    edit_parser.add_argument(
        "--patch",
        required=True,
        help="RFC-6902 JSON patch operation (JSON string)",
    )
    edit_parser.add_argument(
        "--who",
        default="user",
        help="User identifier (email or username)",
    )
    edit_parser.add_argument(
        "--reason",
        default="",
        help="Reason for the edit",
    )

    # List-edits subcommand
    list_edits_parser = subparsers.add_parser(
        "list-edits",
        help="Show edit history for a merged report",
    )
    list_edits_parser.add_argument(
        "merged_file",
        type=Path,
        help="Path to merged report file",
    )

    # Undo subcommand
    undo_parser = subparsers.add_parser(
        "undo",
        help="Remove an edit and re-merge",
    )
    undo_parser.add_argument(
        "merged_file",
        type=Path,
        help="Path to merged report file",
    )
    undo_parser.add_argument(
        "--index",
        type=int,
        help="Index of edit to remove (1-based, omit to remove last)",
    )

    # Replay subcommand
    replay_parser = subparsers.add_parser(
        "replay",
        help="Manually replay edits without re-merging",
    )
    replay_parser.add_argument(
        "merged_file",
        type=Path,
        help="Path to merged report file",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "merge":
        return _handle_merge(args)
    elif args.command == "edit":
        return _handle_edit(args)
    elif args.command == "list-edits":
        return _handle_list_edits(args)
    elif args.command == "undo":
        return _handle_undo(args)
    elif args.command == "replay":
        return _handle_replay(args)

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
        result = merge_reports(
            adapter=adapter,
            inputs=inputs,
            mapping=mapping,
            output_path=output_path,
        )
    except Exception as exc:
        print(f"Error during merge: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result.output_bytes)
    sidecar_path = result.provenance.write_sidecar(output_path)

    print(f"Merged {len(input_paths)} reports → {output_path}")
    print(f"Provenance sidecar → {sidecar_path}")
    return 0


def _handle_edit(args: argparse.Namespace) -> int:
    """Handle the 'edit' subcommand."""
    import json

    from report_aggregator.engine.patch import Patch, PatchError, apply_patch
    from report_aggregator.engine.provenance import ProvenanceTracker

    merged_file: Path = args.merged_file
    patch_json: str = args.patch
    who: str = args.who
    reason: str = args.reason

    if not merged_file.exists():
        print(f"Error: File not found: {merged_file}", file=sys.stderr)
        return 1

    # Load provenance sidecar
    sidecar_path = merged_file.parent / f"{merged_file.stem}.provenance.json"
    if not sidecar_path.exists():
        print(f"Error: Provenance sidecar not found: {sidecar_path}", file=sys.stderr)
        return 1

    try:
        provenance_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        provenance = ProvenanceTracker.from_dict(provenance_data)
    except Exception as e:
        print(f"Error loading provenance: {e}", file=sys.stderr)
        return 1

    # Parse patch
    try:
        patch_data = json.loads(patch_json)
        patch = Patch(
            op=patch_data["op"],
            path=patch_data["path"],
            value=patch_data.get("value"),
            from_=patch_data.get("from", ""),
        )
    except Exception as e:
        print(f"Error parsing patch: {e}", file=sys.stderr)
        return 1

    # Determine format and load adapter
    format_name = provenance.format_name
    try:
        mapping = load_mapping(format_name)
    except MappingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _register_adapters()
    if format_name not in _ADAPTER_REGISTRY:
        print(f"Error: Adapter for '{format_name}' not available", file=sys.stderr)
        return 1

    adapter_cls = _ADAPTER_REGISTRY[format_name]
    adapter = adapter_cls(mapping)

    # Load merged file
    try:
        raw = merged_file.read_bytes()
        doc = adapter.load(raw)
    except Exception as e:
        print(f"Error loading merged file: {e}", file=sys.stderr)
        return 1

    # Apply patch
    try:
        old_value = None
        if patch.op in ("replace", "remove"):
            # Try to capture old value for display
            try:
                from report_aggregator.engine.patch import get_value_at_path, parse_json_pointer
                tokens = parse_json_pointer(patch.path)
                old_value = get_value_at_path(doc, tokens)
            except:
                pass

        doc = apply_patch(doc, patch)

        print("✓ Edit applied successfully")
        print(f"  Operation: {patch.op}")
        print(f"  Path: {patch.path}")
        if old_value is not None:
            print(f"  Old value: {old_value}")
        if patch.value is not None:
            print(f"  New value: {patch.value}")

    except PatchError as e:
        print(f"Error applying patch: {e}", file=sys.stderr)
        return 1

    # Add edit to provenance
    provenance.add_edit(who=who, patch=patch, reason=reason)

    # Write updated files
    try:
        output_bytes = adapter.render(doc)
        merged_file.write_bytes(output_bytes)
        provenance.write_sidecar(merged_file)
        print(f"\nUpdated files:")
        print(f"  {merged_file}")
        print(f"  {sidecar_path}")
    except Exception as e:
        print(f"Error writing files: {e}", file=sys.stderr)
        return 1

    return 0


def _handle_list_edits(args: argparse.Namespace) -> int:
    """Handle the 'list-edits' subcommand."""
    import json

    from report_aggregator.engine.provenance import ProvenanceTracker

    merged_file: Path = args.merged_file
    sidecar_path = merged_file.parent / f"{merged_file.stem}.provenance.json"

    if not sidecar_path.exists():
        print(f"No provenance sidecar found: {sidecar_path}", file=sys.stderr)
        return 1

    try:
        provenance_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        provenance = ProvenanceTracker.from_dict(provenance_data)
    except Exception as e:
        print(f"Error loading provenance: {e}", file=sys.stderr)
        return 1

    edits = provenance.get_edits()

    if not edits:
        print(f"No edits found in {merged_file}")
        return 0

    print(f"Edit History for {merged_file} ({len(edits)} edit(s))\n")

    for i, edit_entry in enumerate(edits, 1):
        print(f"{i}. [{edit_entry.when}] {edit_entry.who}")
        print(f"   Operation: {edit_entry.patch.op}")
        print(f"   Path: {edit_entry.patch.path}")
        if edit_entry.patch.value is not None:
            print(f"   Value: {edit_entry.patch.value}")
        if edit_entry.patch.from_:
            print(f"   From: {edit_entry.patch.from_}")
        if edit_entry.reason:
            print(f"   Reason: {edit_entry.reason}")
        print()

    return 0


def _handle_undo(args: argparse.Namespace) -> int:
    """Handle the 'undo' subcommand."""
    import json

    from report_aggregator.engine.provenance import ProvenanceTracker

    merged_file: Path = args.merged_file
    index: int | None = args.index

    if not merged_file.exists():
        print(f"Error: File not found: {merged_file}", file=sys.stderr)
        return 1

    sidecar_path = merged_file.parent / f"{merged_file.stem}.provenance.json"
    if not sidecar_path.exists():
        print(f"Error: Provenance sidecar not found: {sidecar_path}", file=sys.stderr)
        return 1

    try:
        provenance_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        provenance = ProvenanceTracker.from_dict(provenance_data)
    except Exception as e:
        print(f"Error loading provenance: {e}", file=sys.stderr)
        return 1

    if not provenance.edits:
        print("No edits to undo")
        return 0

    # Remove specified edit
    if index is not None:
        if index < 1 or index > len(provenance.edits):
            print(f"Error: Edit index {index} out of range (1-{len(provenance.edits)})", file=sys.stderr)
            return 1
        removed = provenance.edits.pop(index - 1)
        print(f"Removed edit {index}: {removed.patch.op} {removed.patch.path}")
    else:
        removed = provenance.edits.pop()
        print(f"Removed last edit: {removed.patch.op} {removed.patch.path}")

    # To properly undo, we need to re-merge from scratch
    # For now, just update the provenance and suggest re-running merge
    print("\n⚠ To apply the undo, re-run the original merge command.")
    print("The merge will replay the remaining edits automatically.")

    # Write updated provenance
    provenance.write_sidecar(merged_file)
    print(f"Updated provenance: {sidecar_path}")

    return 0


def _handle_replay(args: argparse.Namespace) -> int:
    """Handle the 'replay' subcommand."""
    import json

    from report_aggregator.engine.patch import PatchError, apply_patches
    from report_aggregator.engine.provenance import ProvenanceTracker

    merged_file: Path = args.merged_file

    if not merged_file.exists():
        print(f"Error: File not found: {merged_file}", file=sys.stderr)
        return 1

    sidecar_path = merged_file.parent / f"{merged_file.stem}.provenance.json"
    if not sidecar_path.exists():
        print(f"Error: Provenance sidecar not found: {sidecar_path}", file=sys.stderr)
        return 1

    try:
        provenance_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        provenance = ProvenanceTracker.from_dict(provenance_data)
    except Exception as e:
        print(f"Error loading provenance: {e}", file=sys.stderr)
        return 1

    if not provenance.edits:
        print("No edits to replay")
        return 0

    # Determine format and load adapter
    format_name = provenance.format_name
    try:
        mapping = load_mapping(format_name)
    except MappingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _register_adapters()
    if format_name not in _ADAPTER_REGISTRY:
        print(f"Error: Adapter for '{format_name}' not available", file=sys.stderr)
        return 1

    adapter_cls = _ADAPTER_REGISTRY[format_name]
    adapter = adapter_cls(mapping)

    # Load merged file
    try:
        raw = merged_file.read_bytes()
        doc = adapter.load(raw)
    except Exception as e:
        print(f"Error loading merged file: {e}", file=sys.stderr)
        return 1

    # Replay all edits
    print(f"Replaying {len(provenance.edits)} edit(s)...")
    failed = 0
    for i, edit_entry in enumerate(provenance.edits, 1):
        try:
            doc = apply_patches(doc, [edit_entry.patch])
            print(f"  {i}. ✓ {edit_entry.patch.op} {edit_entry.patch.path}")
        except PatchError as e:
            print(f"  {i}. ✗ {edit_entry.patch.op} {edit_entry.patch.path}: {e}")
            failed += 1

    # Write updated file
    try:
        output_bytes = adapter.render(doc)
        merged_file.write_bytes(output_bytes)
        print(f"\nUpdated: {merged_file}")
        if failed:
            print(f"⚠ {failed} edit(s) failed to apply")
    except Exception as e:
        print(f"Error writing file: {e}", file=sys.stderr)
        return 1

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
        result = merge_reports(
            adapter=adapter,
            inputs=inputs,
            mapping=mapping,
            output_path=output_path,
        )
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
