"""Generate RFC-6902 patches from the difference between two documents.

Used by the interactive editor: the client sends a full edited document, and we
record the change as granular patches in the provenance edit layer so it stays
transparent and replays on re-merge — exactly like an inline edit.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from report_aggregator.engine.patch import Patch, apply_patches


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def diff_to_patches(old: Any, new: Any, path: str = "") -> list[Patch]:
    """Return RFC-6902 patches that transform ``old`` into ``new``.

    Emits only ``replace``/``add``/``remove`` operations. List changes are
    diffed index-wise with trailing add/remove, which apply cleanly because
    removes are emitted from the highest index downward.
    """
    # Type change or scalar mismatch -> replace wholesale.
    if type(old) is not type(new) or _is_scalar(new) or _is_scalar(old):
        if old != new:
            return [Patch(op="replace", path=path or "/", value=copy.deepcopy(new))]
        return []

    patches: list[Patch] = []

    if isinstance(old, dict):
        for key in old:
            child = f"{path}/{_escape(str(key))}"
            if key not in new:
                patches.append(Patch(op="remove", path=child))
            else:
                patches.extend(diff_to_patches(old[key], new[key], child))
        for key in new:
            if key not in old:
                child = f"{path}/{_escape(str(key))}"
                patches.append(Patch(op="add", path=child, value=copy.deepcopy(new[key])))
        return patches

    if isinstance(old, list):
        common = min(len(old), len(new))
        for i in range(common):
            patches.extend(diff_to_patches(old[i], new[i], f"{path}/{i}"))
        # Removals from the tail, highest index first.
        if len(old) > len(new):
            for i in range(len(old) - 1, len(new) - 1, -1):
                patches.append(Patch(op="remove", path=f"{path}/{i}"))
        # Additions appended in order.
        elif len(new) > len(old):
            for i in range(len(old), len(new)):
                patches.append(Patch(op="add", path=f"{path}/{i}", value=copy.deepcopy(new[i])))
        return patches

    # Fallback for unexpected types.
    if old != new:
        return [Patch(op="replace", path=path or "/", value=copy.deepcopy(new))]
    return []


def _patch_json_serializable(patch: Patch) -> bool:
    """Return True if patch fields can be stored in provenance JSON."""
    try:
        json.dumps(
            {
                "op": patch.op,
                "path": patch.path,
                "value": patch.value,
                "from": patch.from_,
            }
        )
        return True
    except TypeError:
        return False


def _patches_json_serializable(patches: list[Patch]) -> bool:
    return all(_patch_json_serializable(p) for p in patches)


def _content_replace_patch(raw_new: str) -> list[Patch]:
    """Record a full-document replacement as raw text (JSON-serializable)."""
    return [Patch(op="replace", path="/", value=raw_new)]


def build_patches(old: Any, new: Any, raw_new: str | None = None, verify: bool = True) -> list[Patch]:
    """Diff old->new and verify the patches reproduce ``new``.

    Falls back to a single root replace if the granular diff does not
    reconstruct ``new`` exactly (guarantees the recorded edit is consistent).

    When ``raw_new`` is provided and native structures are not JSON-serializable
    (e.g. CLIXML ``Element`` trees), the fallback stores the edited text so the
    provenance sidecar can be written and edits replay on re-merge.

    Args:
        verify: When True (default) the computed patches are re-applied against
            a deep-copy of ``old`` and compared to ``new`` to guarantee
            correctness.  Pass ``verify=False`` for very large documents where
            the deepcopy would consume excessive memory — the granular patches
            are still computed and recorded; only the post-apply confirmation
            step is skipped.
    """
    patches = diff_to_patches(old, new)
    if not patches:
        return []

    if not _patches_json_serializable(patches):
        if raw_new is not None:
            return _content_replace_patch(raw_new)
        patches = [Patch(op="replace", path="/", value=copy.deepcopy(new))]

    if not verify:
        return patches

    try:
        check = apply_patches(copy.deepcopy(old), copy.deepcopy(patches))
        if check == new:
            return patches
    except Exception:
        pass

    if raw_new is not None:
        return _content_replace_patch(raw_new)
    return [Patch(op="replace", path="/", value=copy.deepcopy(new))]
