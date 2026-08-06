# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Large-file-safe raw/diff support for the API service.

This module powers the VS Code-style raw/diff view in the UI. Reports can be
50-115 MB, far beyond what a browser-side diff engine (e.g. Monaco, whose diff
``maxFileSize`` defaults to 50 MB) can handle. Instead of shipping whole files
to the client we:

* build and cache a per-file **byte-offset line index** so any line range can
  be read with a single ``seek`` (no full-file load),
* (in later steps) compute a line-level **diff** once and cache it, then serve
  aligned rows in windows.

All cache artifacts live under ``<aggregate>/diffcache/`` and are keyed by each
source file's ``(size, mtime)`` so they invalidate automatically when the
merged output is rewritten by an edit.
"""

from __future__ import annotations

import array
import bisect
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from report_aggregator.api import storage
from report_aggregator.api.storage import AggregateMeta

# Native unsigned 64-bit offsets. Cache files are machine-local, so native byte
# order is fine.
_OFFSET_TYPECODE = "Q"


# --------------------------------------------------------------------------- #
# Cache locations
# --------------------------------------------------------------------------- #


def cache_dir(aggregate_id: str) -> Path:
    """Return (and create) the diff/line-index cache directory."""
    d = storage.aggregate_dir(aggregate_id) / "diffcache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_signature(path: Path) -> str:
    """A cheap content fingerprint: size + modification time (ns)."""
    st = path.stat()
    return f"{st.st_size}-{st.st_mtime_ns}"


def _signature_hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _line_index_path(aggregate_id: str, path: Path) -> Path:
    h = _signature_hash("lines", str(path), _file_signature(path))
    return cache_dir(aggregate_id) / f"lines-{h}.idx"


# --------------------------------------------------------------------------- #
# Source resolution
# --------------------------------------------------------------------------- #


def resolve_source(meta: AggregateMeta, aggregate_id: str, source: str) -> Path:
    """Map a source spec to a file path.

    ``source`` is either ``"merged"`` or ``"input:<index>"``.
    Raises ``KeyError`` for an unknown input and ``ValueError`` for a malformed
    spec.
    """
    if source == "merged":
        return storage.merged_path(aggregate_id, meta)
    if source.startswith("input:"):
        try:
            idx = int(source.split(":", 1)[1])
        except ValueError as exc:  # noqa: TRY003
            raise ValueError(f"Invalid input index in source '{source}'") from exc
        match = next((i for i in meta.inputs if i.input_index == idx), None)
        if match is None:
            raise KeyError(f"Input {idx} not found")
        return storage.inputs_dir(aggregate_id) / match.filename
    raise ValueError(f"Unknown source spec: {source!r}")


# --------------------------------------------------------------------------- #
# Line-offset index
# --------------------------------------------------------------------------- #


def build_line_index(path: Path) -> array.array:
    """Build an array of byte offsets marking the start of each line.

    The returned array has ``N + 1`` entries for ``N`` lines: the start offset
    of every line plus a trailing EOF offset, so line ``i`` spans
    ``offsets[i]:offsets[i + 1]`` (newline included).
    """
    offsets = array.array(_OFFSET_TYPECODE, [0])
    offset = 0
    with path.open("rb") as fh:
        for line in fh:
            offset += len(line)
            offsets.append(offset)
    return offsets


def get_line_index(aggregate_id: str, path: Path) -> array.array:
    """Return a cached line index, building and persisting it on first use."""
    idx_path = _line_index_path(aggregate_id, path)
    if idx_path.exists():
        offsets = array.array(_OFFSET_TYPECODE)
        offsets.frombytes(idx_path.read_bytes())
        return offsets
    offsets = build_line_index(path)
    idx_path.write_bytes(offsets.tobytes())
    return offsets


def line_count(offsets: array.array) -> int:
    """Number of lines represented by an offset index."""
    return max(0, len(offsets) - 1)


def _strip_eol(seg: bytes) -> bytes:
    if seg.endswith(b"\n"):
        seg = seg[:-1]
        if seg.endswith(b"\r"):
            seg = seg[:-1]
    return seg


def read_lines(
    path: Path, offsets: array.array, start: int, count: int
) -> tuple[list[str], int]:
    """Read ``count`` lines starting at 0-based ``start``.

    Performs a single ``seek``/``read`` covering only the requested range and
    returns ``(lines, total_lines)``. Trailing newlines (``\\n``/``\\r\\n``) are
    stripped from each returned line.
    """
    total = line_count(offsets)
    start = max(0, start)
    end = min(total, start + max(0, count))
    if start >= end:
        return [], total

    base = offsets[start]
    nbytes = offsets[end] - base
    with path.open("rb") as fh:
        fh.seek(base)
        blob = fh.read(nbytes)

    lines: list[str] = []
    for i in range(start, end):
        seg = blob[offsets[i] - base : offsets[i + 1] - base]
        lines.append(_strip_eol(seg).decode("utf-8", errors="replace"))
    return lines, total


def source_meta(aggregate_id: str, path: Path) -> dict:
    """Return ``{size, total_lines}`` for a source file (cheap; uses the index)."""
    offsets = get_line_index(aggregate_id, path)
    return {"size": path.stat().st_size, "total_lines": line_count(offsets)}


# --------------------------------------------------------------------------- #
# Line-level diff (computed once, cached on disk)
# --------------------------------------------------------------------------- #

DIFF_MODEL_VERSION = 1

# In-process cache of parsed diff models, keyed by (cache_path, mtime_ns) so a
# windowed-rows request does not re-read/parse the JSON on every call.
_MODEL_CACHE: dict[tuple[str, int], dict] = {}


def _hash_line(seg: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(seg, digest_size=8).digest(), "big")


def _line_tokens(path: Path) -> list[int]:
    """Hash each EOL-stripped line to a compact token for diffing.

    Hashing keeps memory bounded for very large files and matches the text the
    UI displays (newlines stripped), so equality lines up with the rendered
    rows.
    """
    tokens: list[int] = []
    with path.open("rb") as fh:
        for line in fh:
            tokens.append(_hash_line(_strip_eol(line)))
    return tokens


def _opcode_row_span(tag: str, i1: int, i2: int, j1: int, j2: int) -> int:
    """Number of aligned (side-by-side) rows an opcode occupies."""
    if tag == "insert":
        return j2 - j1
    if tag in ("equal", "delete"):
        return i2 - i1
    # replace: lines pair up; the longer side dictates the row count.
    return max(i2 - i1, j2 - j1)


def _diff_cache_path(aggregate_id: str, left_path: Path, right_path: Path) -> Path:
    h = _signature_hash(
        "diff",
        str(left_path),
        _file_signature(left_path),
        str(right_path),
        _file_signature(right_path),
    )
    return cache_dir(aggregate_id) / f"diff-{h}.json"


# --- diff backends --------------------------------------------------------- #

# GNU diff scales to 100+ MB in well under a second; difflib is a portability
# fallback only (it is quadratic on repetitive lines and unusable at scale).
_DIFF_BIN = shutil.which("diff")

_TAG_FROM_LETTER = {"a": "insert", "d": "delete", "c": "replace"}


class DiffError(RuntimeError):
    """Raised when the external diff backend fails."""


def _gnu_diff_records(left_path: Path, right_path: Path) -> list[tuple]:
    """Run GNU diff and return compact change records (no line content).

    Group formats emit one line per change group as
    ``<tag> <oldFirst> <oldLast> <newFirst> <newLast>`` (1-based, inclusive;
    an empty range has ``last == first - 1``). Unchanged groups are suppressed,
    so output is proportional to the number of changes — never the file size.
    """
    fmt = "{} %df %dl %dF %dL\n"
    cmd = [
        _DIFF_BIN,
        "-a",  # treat input as text (avoid "Binary files differ")
        "--unchanged-group-format=",
        "--old-group-format=" + fmt.format("d"),
        "--new-group-format=" + fmt.format("a"),
        "--changed-group-format=" + fmt.format("c"),
        str(left_path),
        str(right_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    # 0 = identical, 1 = differences, >=2 = error.
    if proc.returncode >= 2:
        raise DiffError(proc.stderr.strip() or "diff failed")

    records: list[tuple] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        tag, of, ol, nf, nl = line.split()
        records.append((tag, int(of), int(ol), int(nf), int(nl)))
    return records


def _records_to_opcodes(
    records: list[tuple], a_lines: int, b_lines: int
) -> list[list]:
    """Turn GNU diff change records into a full opcode list (equal gaps filled)."""
    opcodes: list[list] = []
    ai = bj = 0
    for tag, of, ol, nf, nl in records:
        # 0-based, half-open spans (empty span when last < first).
        i1, i2 = (of - 1, ol) if ol >= of else (of - 1, of - 1)
        j1, j2 = (nf - 1, nl) if nl >= nf else (nf - 1, nf - 1)
        # Equal run between the previous change and this one.
        if i1 > ai:
            gap = i1 - ai
            opcodes.append(["equal", ai, i1, bj, bj + gap])
            bj += gap
            ai = i1
        opcodes.append([_TAG_FROM_LETTER[tag], i1, i2, j1, j2])
        ai, bj = i2, j2
    # Trailing equal run to EOF.
    if ai < a_lines:
        opcodes.append(["equal", ai, a_lines, bj, bj + (a_lines - ai)])
    return opcodes


def _difflib_opcodes(left_path: Path, right_path: Path) -> list[list]:
    """Fallback diff using stdlib difflib (small files / no GNU diff)."""
    a = _line_tokens(left_path)
    b = _line_tokens(right_path)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=True)
    return [[tag, i1, i2, j1, j2] for tag, i1, i2, j1, j2 in matcher.get_opcodes()]


def compute_diff(
    left_path: Path, right_path: Path, a_lines: int, b_lines: int
) -> dict:
    """Compute a line-level diff model between two files.

    Uses GNU ``diff`` when available (scales to 100+ MB), otherwise falls back
    to ``difflib``. Returns a JSON-serializable model with opcodes + stats.
    """
    if _DIFF_BIN:
        records = _gnu_diff_records(left_path, right_path)
        opcodes = _records_to_opcodes(records, a_lines, b_lines)
    else:
        opcodes = _difflib_opcodes(left_path, right_path)

    total_rows = 0
    counts = {"equal": 0, "replace": 0, "insert": 0, "delete": 0}
    for tag, i1, i2, j1, j2 in opcodes:
        rows = _opcode_row_span(tag, i1, i2, j1, j2)
        counts[tag] = counts.get(tag, 0) + rows
        total_rows += rows

    return {
        "version": DIFF_MODEL_VERSION,
        "total_rows": total_rows,
        "counts": counts,
        "left_lines": a_lines,
        "right_lines": b_lines,
        "opcodes": opcodes,
    }


def get_diff_model(
    meta: AggregateMeta, aggregate_id: str, left: str, right: str
) -> dict:
    """Return a cached diff model, computing and persisting it on first use."""
    left_path = resolve_source(meta, aggregate_id, left)
    right_path = resolve_source(meta, aggregate_id, right)
    cache_path = _diff_cache_path(aggregate_id, left_path, right_path)

    if cache_path.exists():
        key = (str(cache_path), cache_path.stat().st_mtime_ns)
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        model = json.loads(cache_path.read_text(encoding="utf-8"))
        if model.get("version") == DIFF_MODEL_VERSION:
            _MODEL_CACHE[key] = model
            return model
        # Version mismatch: fall through and recompute.

    # Building the line indexes both warms the per-file cache (reused by the
    # rows endpoint) and gives the exact line counts for opcode assembly.
    a_lines = line_count(get_line_index(aggregate_id, left_path))
    b_lines = line_count(get_line_index(aggregate_id, right_path))
    model = compute_diff(left_path, right_path, a_lines, b_lines)
    cache_path.write_text(json.dumps(model), encoding="utf-8")
    _MODEL_CACHE[(str(cache_path), cache_path.stat().st_mtime_ns)] = model
    return model


def diff_meta(model: dict) -> dict:
    """Project a diff model to its lightweight metadata (no opcodes)."""
    return {
        "total_rows": model["total_rows"],
        "counts": model["counts"],
        "left_lines": model["left_lines"],
        "right_lines": model["right_lines"],
    }


def _cumulative_rows(opcodes: list) -> list[int]:
    """Prefix sums of per-opcode row spans (length ``len(opcodes) + 1``)."""
    cum = [0]
    for tag, i1, i2, j1, j2 in opcodes:
        cum.append(cum[-1] + _opcode_row_span(tag, i1, i2, j1, j2))
    return cum


def diff_rows(
    model: dict,
    left_path: Path,
    left_offsets: array.array,
    right_path: Path,
    right_offsets: array.array,
    start: int,
    count: int,
) -> tuple[list[dict], int]:
    """Assemble aligned diff rows for the window ``[start, start + count)``.

    Each row is ``{type, left_no, right_no, left, right}`` where ``*_no`` are
    1-based line numbers (``None`` when that side is absent) and ``left``/
    ``right`` are the line texts. Line content is read from the source files in
    a single contiguous range per side, using the cached line index.
    """
    opcodes = model["opcodes"]
    total = model["total_rows"]
    start = max(0, start)
    end = min(total, start + max(0, count))
    if start >= end:
        return [], total

    cum = _cumulative_rows(opcodes)
    k = bisect.bisect_right(cum, start) - 1

    # First pass: determine the (type, left_line, right_line) of each row.
    meta_rows: list[tuple[str, int | None, int | None]] = []
    g = start
    while g < end and k < len(opcodes):
        tag, i1, i2, j1, j2 = opcodes[k]
        base = cum[k]
        span = cum[k + 1] - base
        lo = g - base
        hi = min(span, end - base)
        for r in range(lo, hi):
            if tag == "equal":
                meta_rows.append(("equal", i1 + r, j1 + r))
            elif tag == "delete":
                meta_rows.append(("delete", i1 + r, None))
            elif tag == "insert":
                meta_rows.append(("insert", None, j1 + r))
            else:  # replace
                di, dj = i2 - i1, j2 - j1
                meta_rows.append(
                    ("replace", i1 + r if r < di else None, j1 + r if r < dj else None)
                )
        g = base + hi
        k += 1

    # Second pass: read each side's needed lines in one contiguous span.
    def _read_side(path: Path, offsets: array.array, nums: list[int]) -> dict:
        if not nums:
            return {}
        lo_n, hi_n = min(nums), max(nums) + 1
        lines, _ = read_lines(path, offsets, lo_n, hi_n - lo_n)
        return {lo_n + i: lines[i] for i in range(len(lines))}

    left_text = _read_side(
        left_path, left_offsets, [m[1] for m in meta_rows if m[1] is not None]
    )
    right_text = _read_side(
        right_path, right_offsets, [m[2] for m in meta_rows if m[2] is not None]
    )

    rows = [
        {
            "type": tag,
            "left_no": (ln + 1) if ln is not None else None,
            "right_no": (rn + 1) if rn is not None else None,
            "left": left_text.get(ln) if ln is not None else None,
            "right": right_text.get(rn) if rn is not None else None,
        }
        for tag, ln, rn in meta_rows
    ]
    return rows, total


# --------------------------------------------------------------------------- #
# Diff search (backend-assisted, VS Code-style next/prev)
# --------------------------------------------------------------------------- #

SEARCH_DEFAULT_LIMIT = 500


def search_diff(
    model: dict,
    left_path: Path,
    left_offsets: array.array,
    right_path: Path,
    right_offsets: array.array,
    query: str,
    case_sensitive: bool = False,
    limit: int = SEARCH_DEFAULT_LIMIT,
) -> dict:
    """Find lines containing ``query`` in either diff side.

    Streams both source files line-by-line (no full load), maps each matching
    line to its diff row number via the cumulative row table, and returns a
    capped match list with ``{row, side, line_no}`` entries.

    ``row`` is 0-based (directly usable by the virtualizer's ``scrollToIndex``),
    ``line_no`` is 1-based, ``side`` is ``"left"`` or ``"right"``.
    """
    needle = query if case_sensitive else query.lower()
    opcodes = model["opcodes"]
    cum = _cumulative_rows(opcodes)

    # Build per-side sorted opcode boundary arrays for O(log n) line→row lookup.
    left_starts = array.array("q", [op[1] for op in opcodes])  # i1 per opcode
    right_starts = array.array("q", [op[3] for op in opcodes])  # j1 per opcode

    def _fast_line_to_row(side: str, line0: int) -> int | None:
        if side == "left":
            ki = bisect.bisect_right(left_starts, line0) - 1
            if ki < 0 or ki >= len(opcodes):
                return None
            tag, i1, i2, j1, j2 = opcodes[ki]
            if tag not in ("equal", "delete", "replace") or not (i1 <= line0 < i2):
                return None
            return cum[ki] + (line0 - i1)
        else:
            ki = bisect.bisect_right(right_starts, line0) - 1
            if ki < 0 or ki >= len(opcodes):
                return None
            tag, i1, i2, j1, j2 = opcodes[ki]
            if tag not in ("equal", "insert", "replace") or not (j1 <= line0 < j2):
                return None
            offset = line0 - j1
            if tag == "replace":
                di = i2 - i1
                return cum[ki] + min(offset, di - 1) if offset < (i2 - i1) else cum[ki] + offset
            return cum[ki] + offset

    matches: list[dict] = []
    truncated = False

    for side, path, offsets in (
        ("left", left_path, left_offsets),
        ("right", right_path, right_offsets),
    ):
        n = line_count(offsets)
        chunk = 4096
        line0 = 0
        while line0 < n:
            chunk_lines, _ = read_lines(path, offsets, line0, chunk)
            for i, text in enumerate(chunk_lines):
                haystack = text if case_sensitive else text.lower()
                if needle in haystack:
                    row = _fast_line_to_row(side, line0 + i)
                    if row is not None:
                        matches.append({"row": row, "side": side, "line_no": line0 + i + 1})
                        if len(matches) >= limit:
                            truncated = True
                            break
            if truncated:
                break
            line0 += chunk
        if truncated:
            break

    # Sort by row so next/prev work in document order.
    matches.sort(key=lambda m: (m["row"], m["side"]))
    return {"total": len(matches), "truncated": truncated, "matches": matches}


