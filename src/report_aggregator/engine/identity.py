"""Identity computation utilities for merge-key generation.

Global identity rules from architecture §4.1:
- Packages/files: SHA1 (fallback MD5, SHA256), lowercased hex
- License text blocks: md5(normalized_text)
- Checksums: always lowercased before comparison
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


# LicenseRef tokens may contain dots; SPDXRef tokens do not. Exclude SPDXRef
# matches followed by a file extension (e.g. SPDXRef-generator.py).
_EMBEDDED_REF_TOKEN = re.compile(
    r"(?:input\d+-)?(?:LicenseRef-[^\s()]+|SPDXRef-[\w-]+(?!\.\w{2,5}))"
)


def rewrite_embedded_refs(text: str, remap: dict[str, str]) -> str:
    """Replace SPDX-style ref tokens embedded in a string.

    Uses whole-token matching so a shorter ref ID cannot corrupt a longer
    one that shares the same prefix (e.g. LicenseRef-foo vs LicenseRef-foo-bar).
    """
    if not remap:
        return text

    def replace_token(match: re.Match[str]) -> str:
        return remap.get(match.group(0), match.group(0))

    return _EMBEDDED_REF_TOKEN.sub(replace_token, text)


def normalize_checksum(hex_str: str) -> str:
    """Lowercase hex digits for cross-format comparison.

    FOSSology CDX uses uppercase (CE19689F…), SPDX RDF/CLIXML use lowercase.
    """
    return hex_str.strip().lower()


def normalize_text(text: str) -> str:
    """Normalize license text before identity hashing.

    Policy from architecture §4.1:
    1. Normalize line endings to \\n
    2. Strip trailing whitespace per line
    3. Do NOT strip leading/trailing blank lines (may be legally significant)
    """
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines)


def compute_text_identity(text: str) -> str:
    """Compute MD5 identity for a license text block.

    Used for deduplicating extractedLicensingInfo, DEP5 license paragraphs,
    and ReadMeOSS license blocks.
    """
    normalized = normalize_text(text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def entry_display_name(data: dict[str, Any]) -> str:
    """Return a human-readable label for error messages."""
    for key in ("name", "FileName", "SPDXID", "spdxId", "LicenseID", "bom-ref"):
        val = data.get(key)
        if val:
            return str(val)
    return "unknown"


def compute_checksum_identity(
    hashes: list[dict[str, str]],
    preferred_alg: str = "SHA-1",
    fallback_algs: list[str] | None = None,
    *,
    context: str = "",
) -> str:
    """Resolve identity from a CDX-style hashes array.

    FOSSology CDX emits hashes as [{alg, content}, ...].
    Resolves preferred algorithm first, then fallbacks.
    """
    if fallback_algs is None:
        fallback_algs = ["MD5", "SHA-256"]

    # Skip malformed entries (missing 'alg' or 'content') instead of raising a
    # bare KeyError — a clear ValueError is raised below if nothing usable found.
    alg_map = {
        h["alg"]: h["content"]
        for h in hashes
        if isinstance(h, dict) and "alg" in h and "content" in h
    }

    for alg in [preferred_alg] + fallback_algs:
        if alg in alg_map:
            return normalize_checksum(alg_map[alg])

    prefix = f"{context}: " if context else ""
    raise ValueError(
        f"{prefix}No recognized hash algorithm found in {list(alg_map.keys())}. "
        f"Expected one of: {[preferred_alg] + fallback_algs}"
    )


def compute_spdx_checksum_identity(
    checksums: dict[str, str],
    preferred: str = "SHA1",
    fallbacks: list[str] | None = None,
    *,
    context: str = "",
) -> str:
    """Resolve identity from SPDX-style checksums dict."""
    if fallbacks is None:
        fallbacks = ["MD5", "SHA256"]

    for alg in [preferred] + fallbacks:
        if alg in checksums:
            return normalize_checksum(checksums[alg])

    prefix = f"{context}: " if context else ""
    raise ValueError(
        f"{prefix}No recognized checksum found in {list(checksums.keys())}. "
        f"Expected one of: {[preferred] + fallbacks}"
    )


def compute_spdx3_checksum_identity(
    verified_using: list[dict[str, str]],
    preferred_alg: str = "sha1",
    fallback_algs: list[str] | None = None,
    *,
    context: str = "",
) -> str:
    """Resolve identity from SPDX 3 verifiedUsing[] hash objects."""
    if fallback_algs is None:
        fallback_algs = ["md5", "sha256"]

    alg_map = {
        h["algorithm"].lower(): h["hashValue"]
        for h in verified_using
        if isinstance(h, dict) and "algorithm" in h and "hashValue" in h
    }

    for alg in [preferred_alg.lower()] + [a.lower() for a in fallback_algs]:
        if alg in alg_map:
            return normalize_checksum(alg_map[alg])

    prefix = f"{context}: " if context else ""
    raise ValueError(
        f"{prefix}No recognized hash algorithm found in verifiedUsing. "
        f"Expected one of: {[preferred_alg] + fallback_algs}"
    )


def compute_stanza_identity(license_expression: str | None, file_globs: list[str]) -> str:
    """Compute DEP5 Files stanza identity per architecture §4.1."""
    expr = (license_expression or "").strip()
    normalized_globs = sorted(g.strip() for g in file_globs if g.strip())
    key = f"{expr}\0" + "\0".join(normalized_globs)
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def strip_oselot_prefix(text: str) -> str:
    """Strip OSSelot export prefix from ReadMeOSS license text when present."""
    marker = "=== OSSelot Export ==="
    if marker in text:
        return text.split(marker, 1)[1].lstrip("\n")
    return text


def normalize_readmeoss_text(text: str) -> str:
    """Normalize ReadMeOSS license block text before identity hashing."""
    return normalize_text(strip_oselot_prefix(text))


_IRI_REF_FIELDS = frozenset({
    "subject", "from", "to", "creationInfo", "element",
    "createdBy", "createdUsing", "spdxId", "@id",
})


def _rewrite_iri_ref(value: str, remap: dict[str, str]) -> str:
    """Rewrite an IRI reference, including fragment-only matches."""
    if value in remap:
        return remap[value]
    if "#" in value:
        base, fragment = value.rsplit("#", 1)
        if fragment in remap:
            target = remap[fragment]
            return target if target.startswith(("http", "urn:")) else f"{base}#{target}"
        prefixed = f"{base}#{fragment}"
        if prefixed in remap:
            return remap[prefixed]
    return value


def rewrite_refs_in_structure(obj: Any, remap: dict[str, str]) -> Any:
    """Recursively rewrite ref fields using remap; embedded tokens elsewhere."""
    if isinstance(obj, dict):
        return {
            k: (
                _rewrite_iri_ref(v, remap)
                if isinstance(v, str) and k in _IRI_REF_FIELDS
                else rewrite_refs_in_structure(v, remap)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [rewrite_refs_in_structure(item, remap) for item in obj]
    if isinstance(obj, str):
        if obj in remap:
            return remap[obj]
        rewritten = _rewrite_iri_ref(obj, remap)
        if rewritten != obj:
            return rewritten
        embeddable = {
            k: v for k, v in remap.items()
            if "SPDXRef-" in k or "LicenseRef-" in k
        }
        if embeddable:
            return rewrite_embedded_refs(obj, embeddable)
    return obj


def make_namespaced_ref(original_ref: str, input_index: int) -> str:
    """Create a namespaced version of a local ref to avoid cross-input collisions."""
    if "#" in original_ref:
        base, fragment = original_ref.rsplit("#", 1)
        if fragment.startswith("SPDXRef-"):
            fragment = f"SPDXRef-input{input_index}-{fragment[8:]}"
        else:
            fragment = f"SPDXRef-input{input_index}-{fragment}"
        return f"{base}#{fragment}"

    spdx_match = re.match(r"^SPDXRef-(.+)$", original_ref)
    if spdx_match:
        return f"SPDXRef-input{input_index}-{spdx_match.group(1)}"

    return f"input{input_index}-{original_ref}"
