"""High-level public API for merging FOSSology reports.

This is the stable, import-friendly entry point for embedding the merge engine
in other software (e.g. a FOSSology agent). It wraps the same pipeline the CLI
uses — format detection, mapping load, adapter selection, and
``merge_reports`` — behind a single :func:`merge` call that takes a list of
report file paths and returns an in-memory :class:`MergeOutput`.

Example::

    import report_aggregator as ra

    result = ra.merge(
        ["CYCLONEDX_JSON_a.json", "CYCLONEDX_JSON_b.json"],
        output_path="merged.cdx.json",   # optional: also write file + sidecar
    )
    print(result.format, len(result.conflicts))
    merged_bytes = result.output_bytes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from report_aggregator.engine.mapping import MappingError, load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports
from report_aggregator.formats import (
    detect_format,
    format_mismatches,
    get_adapter_registry,
)


class ReportAggregatorError(Exception):
    """Base class for all public report-aggregator errors."""


class FormatDetectionError(ReportAggregatorError):
    """Raised when the report format cannot be auto-detected from the inputs."""


class FormatMismatchError(ReportAggregatorError):
    """Raised when inputs do not all match the requested/detected format."""


class InputError(ReportAggregatorError):
    """Raised when inputs are missing, empty, or otherwise unmergeable."""


@dataclass
class MergeOutput:
    """Result of a :func:`merge` call.

    Attributes:
        output_bytes: The merged report rendered in the same format as the inputs.
        format: The resolved format name (e.g. ``"spdx2tv"``).
        provenance: The provenance sidecar as a plain dict (inputs, field
            provenance, conflicts, edits). See ``ProvenanceTracker.to_dict``.
        conflicts: Convenience view of ``provenance["conflicts"]``.
        output_path: Path the merged report was written to, if ``output_path``
            was supplied to :func:`merge`; otherwise ``None``.
        provenance_path: Path the provenance sidecar was written to, if
            ``output_path`` was supplied; otherwise ``None``.
    """

    output_bytes: bytes
    format: str
    provenance: dict[str, Any]
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    output_path: Path | None = None
    provenance_path: Path | None = None

    @property
    def output_text(self) -> str:
        """The merged report decoded as UTF-8 (best effort)."""
        return self.output_bytes.decode("utf-8", errors="replace")


def merge(
    inputs: list[str | Path],
    *,
    format: str | None = None,
    output_path: str | Path | None = None,
) -> MergeOutput:
    """Merge N same-format FOSSology reports into one deduplicated report.

    Args:
        inputs: Two or more report file paths (all the same format).
        format: Optional format override. If omitted, the format is
            auto-detected from filenames/content. If supplied, it must be one of
            the supported formats and every input must match it.
        output_path: Optional path to also write the merged report to. When set,
            a ``<stem>.provenance.json`` sidecar is written alongside it and any
            edits recorded in a pre-existing sidecar at that path are replayed.

    Returns:
        A :class:`MergeOutput` with the merged bytes, resolved format, provenance
        dict, and conflicts.

    Raises:
        InputError: If fewer than one input is given or a path does not exist.
        FormatDetectionError: If ``format`` is omitted and cannot be detected.
        FormatMismatchError: If inputs disagree with the requested format.
        MappingError: If the format has no mapping configuration.
        ReportAggregatorError: For other merge failures.
    """
    input_paths = [Path(p) for p in inputs]
    if not input_paths:
        raise InputError("No input reports provided; merge requires at least one file.")

    missing = [p for p in input_paths if not p.exists()]
    if missing:
        joined = ", ".join(str(p) for p in missing)
        raise InputError(f"Input file(s) not found: {joined}")

    # -- Resolve format --
    if format is None:
        detected = detect_format(input_paths)
        if detected is None:
            raise FormatDetectionError(
                "Cannot auto-detect report format from inputs; pass format=... explicitly. "
                f"Inputs: {', '.join(str(p) for p in input_paths)}"
            )
        format_name = detected
    else:
        mismatches = format_mismatches(input_paths, format)
        if mismatches:
            detail = "; ".join(f"{p}: detected {f}" for p, f in mismatches)
            raise FormatMismatchError(
                f"Format mismatch: expected all inputs to be '{format}', but {detail}"
            )
        format_name = format

    # -- Load mapping + adapter (MappingError propagates as-is) --
    mapping = load_mapping(format_name)

    registry = get_adapter_registry()
    adapter_cls = registry.get(format_name)
    if adapter_cls is None:
        available = list(registry.keys()) or ["(none)"]
        raise MappingError(
            f"Adapter for '{format_name}' is not available. Available adapters: {available}"
        )
    adapter = adapter_cls(mapping)

    # -- Run the merge pipeline (same call the CLI/API use) --
    input_files = [
        InputFile(path=p, input_index=i, source_id=p.stem)
        for i, p in enumerate(input_paths)
    ]
    resolved_output = Path(output_path) if output_path is not None else None

    try:
        result = merge_reports(
            adapter=adapter,
            inputs=input_files,
            mapping=mapping,
            output_path=resolved_output,
        )
    except ReportAggregatorError:
        raise
    except ValueError as exc:
        # merge_reports raises ValueError for empty/unmergeable inputs.
        raise InputError(str(exc)) from exc
    except Exception as exc:
        raise ReportAggregatorError(f"Merge failed: {exc}") from exc

    provenance_dict = result.provenance.to_dict()

    written_output: Path | None = None
    written_sidecar: Path | None = None
    if resolved_output is not None:
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_bytes(result.output_bytes)
        written_sidecar = result.provenance.write_sidecar(resolved_output)
        written_output = resolved_output

    return MergeOutput(
        output_bytes=result.output_bytes,
        format=format_name,
        provenance=provenance_dict,
        conflicts=provenance_dict.get("conflicts", []),
        output_path=written_output,
        provenance_path=written_sidecar,
    )
