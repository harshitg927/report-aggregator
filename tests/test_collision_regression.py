"""Regression tests for cross-instance local-ID collisions.

These cover the documented "re-namespace across independent reports" scenario
(architecture §2.4, §11) that the same-instance golden fixtures never exercise:
two reports from *different* FOSSology instances reuse the same local IDs
(``bom-ref:"1"``, ``SPDXRef-upload1``, ``SPDXRef-item1`` …) for *different*
content. ID uniquification and relationship rewiring must still hold.
"""

import json
import re
from collections import Counter
from pathlib import Path

from report_aggregator.adapters.cyclonedx import CycloneDXAdapter
from report_aggregator.adapters.spdx2tv import SPDX2TVAdapter
from report_aggregator.engine.mapping import load_mapping
from report_aggregator.engine.merge import InputFile, merge_reports


def _cdx(upload_sha1: str, file_sha1: str, file_name: str) -> bytes:
    return json.dumps({
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {"component": {
            "type": "library", "name": "pkg", "bom-ref": "1",
            "hashes": [{"alg": "SHA-1", "content": upload_sha1}],
        }},
        "components": [{
            "type": "file", "name": file_name, "bom-ref": "1-1",
            "hashes": [{"alg": "SHA-1", "content": file_sha1}],
            "licenses": [{"license": {"id": "MIT"}}],
        }],
    }).encode()


def test_cyclonedx_cross_instance_bom_ref_uniqueness(tmp_path: Path):
    """Two independent reports sharing bom-refs but with different content
    must produce strictly unique bom-refs (no last-writer collapse)."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_bytes(_cdx("aaa1", "f00d", "src/a.c"))
    b.write_bytes(_cdx("bbb2", "beef", "src/b.c"))

    mapping = load_mapping("cyclonedx")
    adapter = CycloneDXAdapter(mapping)
    result = merge_reports(
        adapter,
        [InputFile(path=a, input_index=0, source_id="A"),
         InputFile(path=b, input_index=1, source_id="B")],
        mapping,
    )
    out = json.loads(result.output_bytes)

    # 2 distinct uploads + 2 distinct files, none deduped (different content).
    assert len(out["components"]) == 4
    bom_refs = [c["bom-ref"] for c in out["components"] if "bom-ref" in c]
    assert len(bom_refs) == len(set(bom_refs)), f"duplicate bom-refs: {bom_refs}"


def _spdx(upload_id: str, item_id: str, pkg_sha1: str, file_sha1: str, fname: str) -> bytes:
    return f"""SPDXVersion: SPDX-2.3
DataLicense: CC0-1.0
SPDXID: SPDXRef-DOCUMENT
DocumentName: doc
DocumentNamespace: http://x/{upload_id}

##Package
PackageName: pkg
SPDXID: SPDXRef-upload{upload_id}
PackageChecksum: SHA1: {pkg_sha1}
PackageDownloadLocation: NOASSERTION
Relationship: SPDXRef-upload{upload_id} CONTAINS SPDXRef-item{item_id}

##File
FileName: {fname}
SPDXID: SPDXRef-item{item_id}
FileChecksum: SHA1: {file_sha1}
LicenseConcluded: MIT
""".encode()


def _spdx_ids_and_rels(text: str):
    ids = re.findall(r"^SPDXID: (\S+)", text, re.M)
    rels = re.findall(r"^Relationship: (\S+) (\S+) (\S+)", text, re.M)
    return ids, rels


def _dangling(ids, rels):
    idset = set(ids) | {"SPDXRef-DOCUMENT"}
    return [r for r in rels if r[0] not in idset or r[2] not in idset]


def test_spdx2tv_cross_instance_no_collision_no_dangling(tmp_path: Path):
    """Two independent reports reusing SPDXRef-upload1 / SPDXRef-item1 for
    different content → unique SPDXIDs and every relationship resolves."""
    a = tmp_path / "a.spdx"
    b = tmp_path / "b.spdx"
    a.write_bytes(_spdx("1", "1", "p111", "f111", "a.c"))
    b.write_bytes(_spdx("1", "1", "p222", "f222", "b.c"))

    mapping = load_mapping("spdx2tv")
    adapter = SPDX2TVAdapter(mapping)
    result = merge_reports(
        adapter,
        [InputFile(path=a, input_index=0, source_id="A"),
         InputFile(path=b, input_index=1, source_id="B")],
        mapping,
    )
    text = result.output_bytes.decode()
    ids, rels = _spdx_ids_and_rels(text)

    # No duplicate SPDXIDs.
    dups = [i for i, n in Counter(ids).items() if n > 1]
    assert not dups, f"duplicate SPDXIDs: {dups}"
    # Two distinct packages and two distinct files survive.
    assert text.count("##Package") == 2
    assert text.count("##File") == 2
    # Relationships reference declared IDs only.
    assert not _dangling(ids, rels), f"dangling relationships: {_dangling(ids, rels)}"


def test_spdx2tv_duplicate_file_dedup_redirects_relationship(tmp_path: Path):
    """Two different uploads share a file by SHA1; the deduped file's survivor
    must be referenced by both packages' CONTAINS relationships (alias redirect)."""
    a = tmp_path / "a.spdx"
    b = tmp_path / "b.spdx"
    # Different package hashes (distinct uploads) but the same file content (aaaa).
    a.write_bytes(_spdx("100", "10", "PKGA", "aaaa", "shared.c"))
    b.write_bytes(_spdx("200", "20", "PKGB", "aaaa", "shared.c"))

    mapping = load_mapping("spdx2tv")
    adapter = SPDX2TVAdapter(mapping)
    result = merge_reports(
        adapter,
        [InputFile(path=a, input_index=0, source_id="A"),
         InputFile(path=b, input_index=1, source_id="B")],
        mapping,
    )
    text = result.output_bytes.decode()
    ids, rels = _spdx_ids_and_rels(text)

    # 2 packages, 1 deduped file.
    assert text.count("##Package") == 2
    assert text.count("##File") == 1
    assert not _dangling(ids, rels), f"dangling relationships: {_dangling(ids, rels)}"
    # Both CONTAINS relationships point at the single surviving file id.
    contains_targets = {r[2] for r in rels if r[1] == "CONTAINS"}
    assert len(contains_targets) == 1
    assert contains_targets.issubset(set(ids))
