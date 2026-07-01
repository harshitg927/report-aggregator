"""API routes for the report-aggregator service."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from report_aggregator.api import diffview, fieldtree, storage
from report_aggregator.api.diffpatch import build_patches
from report_aggregator.api.edit_summary import summarize_patch, value_at_path
from report_aggregator.api.storage import AggregateMeta, InputMeta
from report_aggregator.engine.mapping import MappingError, load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports
from report_aggregator.engine.patch import Patch, PatchError, apply_patch
from report_aggregator.engine.provenance import ProvenanceTracker
from report_aggregator.formats import (
    SUPPORTED_FORMATS,
    detect_format,
    format_mismatches,
    get_adapter_registry,
)

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_meta(aggregate_id: str) -> AggregateMeta:
    meta = storage.read_meta(aggregate_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Aggregate not found: {aggregate_id}")
    return meta


def _summary(meta: AggregateMeta) -> dict:
    prov = storage.load_provenance(meta.aggregate_id, meta)
    return {
        "aggregate_id": meta.aggregate_id,
        "format": meta.format,
        "created_at": meta.created_at,
        "output_filename": meta.output_filename,
        "inputs": [
            {"source_id": i.source_id, "filename": i.filename, "input_index": i.input_index}
            for i in meta.inputs
        ],
        "counts": {
            "inputs": len(meta.inputs),
            "conflicts": len(prov.get("conflicts") or []),
            "edits": len(prov.get("edits") or []),
        },
    }


def _run_merge(meta: AggregateMeta) -> None:
    """Run (or re-run) the merge for an aggregate from its stored inputs.

    Reuses the engine in-process. The engine replays any edits present in the
    existing provenance sidecar.
    """
    try:
        mapping = load_mapping(meta.format)
    except MappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    registry = get_adapter_registry()
    if meta.format not in registry:
        raise HTTPException(
            status_code=400, detail=f"Adapter for '{meta.format}' is not available"
        )
    adapter = registry[meta.format](mapping)

    in_dir = storage.inputs_dir(meta.aggregate_id)
    inputs = [
        InputFile(
            path=in_dir / im.filename,
            input_index=im.input_index,
            source_id=im.source_id,
        )
        for im in sorted(meta.inputs, key=lambda i: i.input_index)
    ]

    out_path = storage.merged_path(meta.aggregate_id, meta)
    try:
        result = merge_reports(
            adapter=adapter, inputs=inputs, mapping=mapping, output_path=out_path
        )
    except Exception as exc:  # noqa: BLE001 - surface engine errors to client
        raise HTTPException(status_code=400, detail=f"Merge failed: {exc}")

    out_path.write_bytes(result.output_bytes)
    result.provenance.write_sidecar(out_path)


# --------------------------------------------------------------------------- #
# Merge + listing
# --------------------------------------------------------------------------- #


@router.post("/merge")
async def merge(
    files: list[UploadFile] = File(...),
    format: str | None = Form(default=None),
):
    """Merge uploaded report files into a new aggregate."""
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="At least two input files are required")

    if format is not None and format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown format '{format}'. Supported: {SUPPORTED_FORMATS}",
        )

    aggregate_id = str(uuid.uuid4())
    in_dir = storage.inputs_dir(aggregate_id)
    in_dir.mkdir(parents=True, exist_ok=True)

    input_metas: list[InputMeta] = []
    saved_paths: list[Path] = []
    used_stems: set[str] = set()

    for idx, uf in enumerate(files):
        original = Path(uf.filename or f"input_{idx}").name
        dest = in_dir / original
        # Avoid clobbering identical filenames.
        if dest.exists():
            dest = in_dir / f"{Path(original).stem}_{idx}{Path(original).suffix}"
        content = await uf.read()
        dest.write_bytes(content)
        saved_paths.append(dest)

        stem = dest.stem
        if stem in used_stems:
            stem = f"{stem}_{idx}"
        used_stems.add(stem)
        input_metas.append(InputMeta(source_id=stem, filename=dest.name, input_index=idx))

    # Resolve format.
    resolved = format
    if resolved is None:
        resolved = detect_format(saved_paths)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail="Cannot auto-detect format. Provide 'format' explicitly. "
                "All inputs must be the same supported format.",
            )
    else:
        mism = format_mismatches(saved_paths, resolved)
        if mism:
            detail = "; ".join(f"{p.name}: detected {f}" for p, f in mism)
            raise HTTPException(
                status_code=400,
                detail=f"Format mismatch. Expected all files to be '{resolved}'. {detail}",
            )

    ext = storage.FORMAT_EXTENSION.get(resolved, ".out")
    meta = AggregateMeta(
        aggregate_id=aggregate_id,
        format=resolved,
        created_at=_now(),
        output_filename=f"merged{ext}",
        inputs=input_metas,
    )

    _run_merge(meta)
    storage.write_meta(meta)

    return {"aggregate_id": aggregate_id, **_summary(meta)}


@router.get("/reports")
def list_reports():
    """List all aggregates (newest first)."""
    metas = []
    for agg_id in storage.list_aggregate_ids():
        meta = storage.read_meta(agg_id)
        if meta:
            metas.append(meta)
    metas.sort(key=lambda m: m.created_at, reverse=True)
    return {"reports": [_summary(m) for m in metas]}


@router.get("/reports/{aggregate_id}")
def get_report(aggregate_id: str):
    meta = _require_meta(aggregate_id)
    return _summary(meta)


# --------------------------------------------------------------------------- #
# Read views
# --------------------------------------------------------------------------- #


@router.get("/reports/{aggregate_id}/fields")
def get_fields(aggregate_id: str):
    meta = _require_meta(aggregate_id)
    raw = storage.merged_path(aggregate_id, meta).read_bytes()
    prov = storage.load_provenance(aggregate_id, meta)
    try:
        tree = fieldtree.build_field_tree(meta.format, raw, prov)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to build field tree: {exc}")
    return tree


@router.get("/reports/{aggregate_id}/raw", response_class=PlainTextResponse)
def get_raw(aggregate_id: str):
    meta = _require_meta(aggregate_id)
    raw = storage.merged_path(aggregate_id, meta).read_bytes()
    return PlainTextResponse(raw.decode("utf-8", errors="replace"))


@router.get("/reports/{aggregate_id}/inputs/{idx}/raw", response_class=PlainTextResponse)
def get_input_raw(aggregate_id: str, idx: int):
    meta = _require_meta(aggregate_id)
    match = next((i for i in meta.inputs if i.input_index == idx), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Input {idx} not found")
    path = storage.inputs_dir(aggregate_id) / match.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Input file missing")
    return PlainTextResponse(path.read_bytes().decode("utf-8", errors="replace"))


def _resolve_source_path(meta: AggregateMeta, aggregate_id: str, source: str) -> Path:
    """Resolve a ``merged``/``input:<idx>`` source spec to an existing path."""
    try:
        path = diffview.resolve_source(meta, aggregate_id, source)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Source file missing: {source}")
    return path


@router.get("/reports/{aggregate_id}/raw/meta")
def get_raw_meta(aggregate_id: str, source: str = "merged"):
    """Return ``{size, total_lines}`` for a source without loading it."""
    meta = _require_meta(aggregate_id)
    path = _resolve_source_path(meta, aggregate_id, source)
    return {"source": source, **diffview.source_meta(aggregate_id, path)}


@router.get("/reports/{aggregate_id}/raw/lines")
def get_raw_lines(
    aggregate_id: str,
    source: str = "merged",
    start: int = 0,
    count: int = 200,
):
    """Return a window of lines from a source via the cached line index."""
    if count <= 0 or count > 5000:
        raise HTTPException(status_code=400, detail="count must be in 1..5000")
    if start < 0:
        raise HTTPException(status_code=400, detail="start must be >= 0")
    meta = _require_meta(aggregate_id)
    path = _resolve_source_path(meta, aggregate_id, source)
    offsets = diffview.get_line_index(aggregate_id, path)
    lines, total = diffview.read_lines(path, offsets, start, count)
    return {
        "source": source,
        "start": start,
        "count": len(lines),
        "total_lines": total,
        "lines": lines,
    }


@router.get("/reports/{aggregate_id}/diff/meta")
def get_diff_meta(aggregate_id: str, left: str = "merged", right: str = "merged"):
    """Compute (and cache) the diff between two sources; return summary stats."""
    meta = _require_meta(aggregate_id)
    # Validate sources up front for clear 4xx errors.
    _resolve_source_path(meta, aggregate_id, left)
    _resolve_source_path(meta, aggregate_id, right)
    model = diffview.get_diff_model(meta, aggregate_id, left, right)
    return {"left": left, "right": right, **diffview.diff_meta(model)}


@router.get("/reports/{aggregate_id}/diff/rows")
def get_diff_rows(
    aggregate_id: str,
    left: str = "merged",
    right: str = "merged",
    start: int = 0,
    count: int = 200,
):
    """Return a window of aligned diff rows for the given source pair."""
    if count <= 0 or count > 5000:
        raise HTTPException(status_code=400, detail="count must be in 1..5000")
    if start < 0:
        raise HTTPException(status_code=400, detail="start must be >= 0")
    meta = _require_meta(aggregate_id)
    left_path = _resolve_source_path(meta, aggregate_id, left)
    right_path = _resolve_source_path(meta, aggregate_id, right)
    model = diffview.get_diff_model(meta, aggregate_id, left, right)
    left_offsets = diffview.get_line_index(aggregate_id, left_path)
    right_offsets = diffview.get_line_index(aggregate_id, right_path)
    rows, total = diffview.diff_rows(
        model, left_path, left_offsets, right_path, right_offsets, start, count
    )
    return {
        "left": left,
        "right": right,
        "start": start,
        "count": len(rows),
        "total_rows": total,
        "rows": rows,
    }


@router.get("/reports/{aggregate_id}/diff/search")
def search_diff(
    aggregate_id: str,
    left: str = "merged",
    right: str = "merged",
    q: str = "",
    case_sensitive: bool = False,
    limit: int = diffview.SEARCH_DEFAULT_LIMIT,
):
    """Find lines matching ``q`` in either diff side; return row positions."""
    if not q:
        raise HTTPException(status_code=400, detail="q must not be empty")
    if limit <= 0 or limit > 5000:
        raise HTTPException(status_code=400, detail="limit must be in 1..5000")
    meta = _require_meta(aggregate_id)
    left_path = _resolve_source_path(meta, aggregate_id, left)
    right_path = _resolve_source_path(meta, aggregate_id, right)
    model = diffview.get_diff_model(meta, aggregate_id, left, right)
    left_offsets = diffview.get_line_index(aggregate_id, left_path)
    right_offsets = diffview.get_line_index(aggregate_id, right_path)
    return diffview.search_diff(
        model, left_path, left_offsets, right_path, right_offsets,
        query=q, case_sensitive=case_sensitive, limit=limit,
    )


_MEDIA_TYPES = {
    "cyclonedx": "application/json",
    "spdx3json": "application/json",
    "clixml": "application/xml",
    "spdx2tv": "text/plain",
    "dep5": "text/plain",
    "readmeoss": "text/plain",
}


@router.get("/reports/{aggregate_id}/download")
def download_merged(aggregate_id: str):
    """Download the merged report as a file attachment."""
    meta = _require_meta(aggregate_id)
    data = storage.merged_path(aggregate_id, meta).read_bytes()
    media = _MEDIA_TYPES.get(meta.format, "application/octet-stream")
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{meta.output_filename}"'
        },
    )


@router.get("/reports/{aggregate_id}/provenance/download")
def download_provenance(aggregate_id: str):
    """Download the provenance sidecar as a JSON file attachment."""
    meta = _require_meta(aggregate_id)
    path = storage.sidecar_path(aggregate_id, meta)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Provenance sidecar not found")
    name = f"{Path(meta.output_filename).stem}.provenance.json"
    return Response(
        content=path.read_bytes(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/reports/{aggregate_id}/conflicts")
def get_conflicts(aggregate_id: str):
    meta = _require_meta(aggregate_id)
    prov = storage.load_provenance(aggregate_id, meta)
    return {"conflicts": prov.get("conflicts") or []}


@router.get("/reports/{aggregate_id}/edits")
def get_edits(aggregate_id: str):
    meta = _require_meta(aggregate_id)
    prov = storage.load_provenance(aggregate_id, meta)
    return {"edits": prov.get("edits") or []}


# --------------------------------------------------------------------------- #
# Edits (apply / undo)
# --------------------------------------------------------------------------- #


class EditRequest(BaseModel):
    op: str
    path: str
    value: object | None = None
    from_: str | None = None
    who: str = "user"
    reason: str = ""

    model_config = {"populate_by_name": True}


@router.post("/reports/{aggregate_id}/edits")
def apply_edit(aggregate_id: str, body: EditRequest):
    """Apply an RFC-6902 patch to the merged report and record it."""
    meta = _require_meta(aggregate_id)

    # Accept "from" alias from JSON body.
    from_value = body.from_ or ""

    patch = Patch(op=body.op, path=body.path, value=body.value, from_=from_value)

    mapping = load_mapping(meta.format)
    registry = get_adapter_registry()
    if meta.format not in registry:
        raise HTTPException(status_code=400, detail=f"Adapter for '{meta.format}' not available")
    adapter = registry[meta.format](mapping)

    merged_file = storage.merged_path(aggregate_id, meta)
    doc = adapter.load(merged_file.read_bytes())
    old_value = value_at_path(doc, patch.path)

    try:
        doc = apply_patch(doc, patch)
    except PatchError as exc:
        raise HTTPException(status_code=422, detail=f"Patch failed: {exc}")

    # Persist new merged output + record edit in provenance.
    sidecar = storage.sidecar_path(aggregate_id, meta)
    prov_data = json.loads(sidecar.read_text(encoding="utf-8"))
    provenance = ProvenanceTracker.from_dict(prov_data)
    provenance.add_edit(
        who=body.who,
        patch=patch,
        reason=body.reason,
        summary=summarize_patch(patch, old_value=old_value),
    )

    merged_file.write_bytes(adapter.render(doc))
    provenance.write_sidecar(merged_file)

    return {"ok": True, **_summary(meta)}


class DocumentRequest(BaseModel):
    content: str
    who: str = "user"
    reason: str = "Edited via interactive editor"


@router.put("/reports/{aggregate_id}/document")
def replace_document(aggregate_id: str, body: DocumentRequest):
    """Replace the whole merged document from the interactive editor.

    The edited text is validated by the format adapter, diffed against the
    current document, and the difference is recorded as RFC-6902 patches in the
    edit layer so the change stays transparent and replays on re-merge.

    For large documents (content exceeds ``REPORT_AGGREGATOR_DIFF_VERIFY_MAX_BYTES``,
    default 25 MB) the post-apply deepcopy re-verification step inside
    ``build_patches`` is skipped to avoid excessive memory usage.  Granular
    patches and full validation are always performed regardless of size.
    """
    meta = _require_meta(aggregate_id)

    mapping = load_mapping(meta.format)
    registry = get_adapter_registry()
    if meta.format not in registry:
        raise HTTPException(status_code=400, detail=f"Adapter for '{meta.format}' not available")
    adapter = registry[meta.format](mapping)

    merged_file = storage.merged_path(aggregate_id, meta)
    old_doc = adapter.load(merged_file.read_bytes())
    old_text = merged_file.read_text(encoding="utf-8")

    # Validate the edited content by parsing it with the adapter.
    try:
        new_doc = adapter.load(body.content.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface parse/validation errors
        raise HTTPException(status_code=422, detail=f"Invalid document: {exc}")

    # For large documents skip the deepcopy re-verification step to avoid OOM.
    _verify_max = int(os.environ.get("REPORT_AGGREGATOR_DIFF_VERIFY_MAX_BYTES", 25 * 1024 * 1024))
    verify = len(body.content) <= _verify_max

    patches = build_patches(old_doc, new_doc, raw_new=body.content, verify=verify)

    # Record each patch in the edit layer, then persist the user's exact text.
    sidecar = storage.sidecar_path(aggregate_id, meta)
    prov_data = json.loads(sidecar.read_text(encoding="utf-8"))
    provenance = ProvenanceTracker.from_dict(prov_data)
    for patch in patches:
        provenance.add_edit(
            who=body.who,
            patch=patch,
            reason=body.reason,
            summary=summarize_patch(
                patch,
                old_text=old_text,
                new_text=body.content,
                old_value=value_at_path(old_doc, patch.path),
            ),
        )

    merged_file.write_bytes(body.content.encode("utf-8"))
    provenance.write_sidecar(merged_file)

    return {"ok": True, "changes": len(patches), **_summary(meta)}


@router.delete("/reports/{aggregate_id}/edits/{index}")
def undo_edit(aggregate_id: str, index: int):
    """Remove an edit (1-based index) and re-merge, replaying remaining edits."""
    meta = _require_meta(aggregate_id)
    sidecar = storage.sidecar_path(aggregate_id, meta)
    prov_data = json.loads(sidecar.read_text(encoding="utf-8"))
    provenance = ProvenanceTracker.from_dict(prov_data)

    if not provenance.edits:
        raise HTTPException(status_code=400, detail="No edits to undo")
    if index < 1 or index > len(provenance.edits):
        raise HTTPException(
            status_code=404,
            detail=f"Edit index {index} out of range (1-{len(provenance.edits)})",
        )

    provenance.edits.pop(index - 1)
    # Write the trimmed edit list back, then re-merge so the engine replays the
    # remaining edits from a clean base.
    provenance.write_sidecar(storage.merged_path(aggregate_id, meta))
    _run_merge(meta)

    return {"ok": True, **_summary(meta)}
