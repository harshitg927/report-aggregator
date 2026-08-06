# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Integration tests for the FastAPI service."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from report_aggregator.api.app import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "fossology-reports"
CDX_A = FIXTURES / "CYCLONEDX_JSON_zlib132.zip.json"
CDX_B = FIXTURES / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"
SPDX_A = FIXTURES / "SPDX2TV_zlib132.zip.spdx"
CLIXML_A = FIXTURES / "CLIXML_zlib132.zip.xml"
CLIXML_B = FIXTURES / "CLIXML_fckeditor-2.4.8.zip.xml"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_AGGREGATOR_WORKSPACE", str(tmp_path / "ws"))
    return TestClient(create_app())


def _merge_cdx(client) -> str:
    with CDX_A.open("rb") as a, CDX_B.open("rb") as b:
        resp = client.post(
            "/api/merge",
            files=[
                ("files", (CDX_A.name, a, "application/json")),
                ("files", (CDX_B.name, b, "application/json")),
            ],
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["aggregate_id"]


def _merge_clixml(client) -> str:
    with CLIXML_A.open("rb") as a, CLIXML_B.open("rb") as b:
        resp = client.post(
            "/api/merge",
            files=[
                ("files", (CLIXML_A.name, a, "application/xml")),
                ("files", (CLIXML_B.name, b, "application/xml")),
            ],
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["aggregate_id"]


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_merge_and_list(client):
    agg_id = _merge_cdx(client)

    listing = client.get("/api/reports").json()["reports"]
    assert any(r["aggregate_id"] == agg_id for r in listing)

    summary = client.get(f"/api/reports/{agg_id}").json()
    assert summary["format"] == "cyclonedx"
    assert summary["counts"]["inputs"] == 2


def test_merge_requires_two_files(client):
    with CDX_A.open("rb") as a:
        resp = client.post(
            "/api/merge",
            files=[("files", (CDX_A.name, a, "application/json"))],
        )
    assert resp.status_code == 400


def test_merge_format_mismatch(client):
    with CDX_A.open("rb") as a, SPDX_A.open("rb") as s:
        resp = client.post(
            "/api/merge",
            files=[
                ("files", (CDX_A.name, a, "application/json")),
                ("files", (SPDX_A.name, s, "text/plain")),
            ],
        )
    assert resp.status_code == 400


def test_fields_have_provenance(client):
    agg_id = _merge_cdx(client)
    tree = client.get(f"/api/reports/{agg_id}/fields").json()
    assert "nodes" in tree
    assert len(tree["nodes"]) > 0
    # At least one node should carry provenance sources (engine recorded them).
    assert any(n.get("sources") for n in tree["nodes"])
    # Source ids surfaced for the legend.
    assert len(tree["sources"]) == 2


def test_raw_and_input_raw(client):
    agg_id = _merge_cdx(client)
    raw = client.get(f"/api/reports/{agg_id}/raw")
    assert raw.status_code == 200
    assert '"bomFormat"' in raw.text

    inp = client.get(f"/api/reports/{agg_id}/inputs/0/raw")
    assert inp.status_code == 200
    assert len(inp.text) > 0

    missing = client.get(f"/api/reports/{agg_id}/inputs/99/raw")
    assert missing.status_code == 404


def test_conflicts_endpoint(client):
    agg_id = _merge_cdx(client)
    resp = client.get(f"/api/reports/{agg_id}/conflicts")
    assert resp.status_code == 200
    assert isinstance(resp.json()["conflicts"], list)


def _first_string_leaf(tree) -> dict:
    for n in tree["nodes"]:
        if (
            n["isLeaf"]
            and n["valueType"] == "str"
            and n["value"]
            and "/components/" in n["path"]
            and n["key"] in ("name", "copyright", "description", "publisher", "group")
        ):
            return n
    raise AssertionError("no safe string leaf found")


def test_edit_apply_and_undo(client):
    agg_id = _merge_cdx(client)
    tree = client.get(f"/api/reports/{agg_id}/fields").json()
    leaf = _first_string_leaf(tree)
    path = leaf["path"]
    original = leaf["value"]
    new_value = "EDITED-BY-TEST"

    resp = client.post(
        f"/api/reports/{agg_id}/edits",
        json={"op": "replace", "path": path, "value": new_value,
              "who": "tester@example.com", "reason": "unit test"},
    )
    assert resp.status_code == 200, resp.text

    edits = client.get(f"/api/reports/{agg_id}/edits").json()["edits"]
    assert len(edits) == 1
    assert edits[0]["who"] == "tester@example.com"

    # Field reflects the new value.
    tree2 = client.get(f"/api/reports/{agg_id}/fields").json()
    node = next(n for n in tree2["nodes"] if n["path"] == path)
    assert node["value"] == new_value

    # Undo restores the original.
    undo = client.delete(f"/api/reports/{agg_id}/edits/1")
    assert undo.status_code == 200, undo.text
    edits_after = client.get(f"/api/reports/{agg_id}/edits").json()["edits"]
    assert len(edits_after) == 0

    tree3 = client.get(f"/api/reports/{agg_id}/fields").json()
    node3 = next((n for n in tree3["nodes"] if n["path"] == path), None)
    assert node3 is not None
    assert node3["value"] == original


def test_invalid_patch_path(client):
    agg_id = _merge_cdx(client)
    resp = client.post(
        f"/api/reports/{agg_id}/edits",
        json={"op": "replace", "path": "/does/not/exist", "value": "x"},
    )
    assert resp.status_code == 422


def test_download_merged_and_provenance(client):
    agg_id = _merge_cdx(client)

    dl = client.get(f"/api/reports/{agg_id}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/json")
    assert "attachment" in dl.headers["content-disposition"]
    assert '"bomFormat"' in dl.text

    prov = client.get(f"/api/reports/{agg_id}/provenance/download")
    assert prov.status_code == 200
    assert "attachment" in prov.headers["content-disposition"]
    assert "aggregate_id" in prov.text


def test_document_editor_save_records_patches(client):
    agg_id = _merge_cdx(client)
    raw = client.get(f"/api/reports/{agg_id}/raw").text
    import json as _json

    doc = _json.loads(raw)
    # Edit a real field in the merged document.
    doc["components"][0]["name"] = "EDITED-VIA-EDITOR"
    new_content = _json.dumps(doc, indent=4)

    resp = client.put(
        f"/api/reports/{agg_id}/document",
        json={"content": new_content, "who": "editor@test", "reason": "bulk edit"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changes"] >= 1

    # The change is recorded in the edit history.
    edits = client.get(f"/api/reports/{agg_id}/edits").json()["edits"]
    assert len(edits) >= 1
    assert any(e["who"] == "editor@test" for e in edits)

    # The field tree reflects the new value.
    tree = client.get(f"/api/reports/{agg_id}/fields").json()
    node = next(n for n in tree["nodes"] if n["path"] == "/components/0/name")
    assert node["value"] == "EDITED-VIA-EDITOR"


def test_document_editor_rejects_invalid_content(client):
    agg_id = _merge_cdx(client)
    resp = client.put(
        f"/api/reports/{agg_id}/document",
        json={"content": "{ not valid json", "who": "x"},
    )
    assert resp.status_code == 422


def test_document_editor_save_clixml(client):
    agg_id = _merge_clixml(client)
    raw = client.get(f"/api/reports/{agg_id}/raw").text
    new_content = raw.replace(
        "<ComponentName>NA</ComponentName>",
        "<ComponentName>EDITED-VIA-EDITOR</ComponentName>",
        1,
    )

    resp = client.put(
        f"/api/reports/{agg_id}/document",
        json={"content": new_content, "who": "editor@test", "reason": "clixml edit"},
    )
    assert resp.status_code == 200, resp.text

    edits = client.get(f"/api/reports/{agg_id}/edits").json()["edits"]
    assert len(edits) >= 1
    assert edits[-1]["who"] == "editor@test"
    assert "EDITED-VIA-EDITOR" in client.get(f"/api/reports/{agg_id}/raw").text


# --------------------------------------------------------------------------- #
# Windowed raw lines + meta (large-file-safe reading)
# --------------------------------------------------------------------------- #


def test_raw_meta(client):
    agg_id = _merge_cdx(client)
    full = client.get(f"/api/reports/{agg_id}/raw").text
    meta = client.get(f"/api/reports/{agg_id}/raw/meta").json()
    assert meta["source"] == "merged"
    assert meta["size"] > 0
    # total_lines matches the index-based line count of the document.
    assert meta["total_lines"] == _expected_line_count(full)

    inp = client.get(f"/api/reports/{agg_id}/raw/meta", params={"source": "input:0"}).json()
    assert inp["total_lines"] > 0


def _expected_line_count(text: str) -> int:
    # Mirror diffview.build_line_index: one line per "\n", plus a trailing line
    # if the file does not end with a newline. Empty file -> 0 lines.
    if text == "":
        return 0
    n = text.count("\n")
    return n if text.endswith("\n") else n + 1


def test_raw_lines_windowing(client):
    agg_id = _merge_cdx(client)
    full = client.get(f"/api/reports/{agg_id}/raw").text
    expected_lines = full.split("\n")
    # Drop the trailing empty element produced by a final newline.
    if full.endswith("\n"):
        expected_lines = expected_lines[:-1]

    total = _expected_line_count(full)
    win = client.get(
        f"/api/reports/{agg_id}/raw/lines", params={"start": 0, "count": 10}
    ).json()
    assert win["total_lines"] == total
    assert win["start"] == 0
    assert win["count"] == min(10, total)
    assert win["lines"] == expected_lines[0:10]

    # A window further into the document.
    mid = client.get(
        f"/api/reports/{agg_id}/raw/lines", params={"start": 5, "count": 7}
    ).json()
    assert mid["lines"] == expected_lines[5:12]


def test_raw_lines_out_of_range(client):
    agg_id = _merge_cdx(client)
    total = client.get(f"/api/reports/{agg_id}/raw/meta").json()["total_lines"]
    win = client.get(
        f"/api/reports/{agg_id}/raw/lines",
        params={"start": total + 1000, "count": 50},
    ).json()
    assert win["lines"] == []
    assert win["count"] == 0
    assert win["total_lines"] == total


def test_raw_lines_validation_and_unknown_source(client):
    agg_id = _merge_cdx(client)
    assert client.get(
        f"/api/reports/{agg_id}/raw/lines", params={"count": 0}
    ).status_code == 400
    assert client.get(
        f"/api/reports/{agg_id}/raw/lines", params={"start": -1}
    ).status_code == 400
    assert client.get(
        f"/api/reports/{agg_id}/raw/lines", params={"source": "input:99"}
    ).status_code == 404
    assert client.get(
        f"/api/reports/{agg_id}/raw/lines", params={"source": "bogus"}
    ).status_code == 400


def test_raw_lines_index_invalidates_after_edit(client):
    agg_id = _merge_cdx(client)
    before = client.get(f"/api/reports/{agg_id}/raw/meta").json()["total_lines"]

    # Rewrite the merged document with more lines via the editor endpoint.
    import json as _json

    raw = client.get(f"/api/reports/{agg_id}/raw").text
    doc = _json.loads(raw)
    # Append components so the indented document gains lines.
    extra = {"type": "library", "name": "EXTRA-COMPONENT"}
    doc["components"].extend([dict(extra) for _ in range(20)])
    new_content = _json.dumps(doc, indent=4)
    resp = client.put(
        f"/api/reports/{agg_id}/document",
        json={"content": new_content, "who": "x"},
    )
    assert resp.status_code == 200, resp.text

    after = client.get(f"/api/reports/{agg_id}/raw/meta").json()["total_lines"]
    assert after == _expected_line_count(new_content)
    assert after != before


# --------------------------------------------------------------------------- #
# Diff model: meta + caching + invalidation
# --------------------------------------------------------------------------- #


def test_diff_meta_identical_sources(client):
    agg_id = _merge_cdx(client)
    meta = client.get(
        f"/api/reports/{agg_id}/diff/meta",
        params={"left": "merged", "right": "merged"},
    ).json()
    assert meta["left"] == "merged" and meta["right"] == "merged"
    # Diffing a file with itself: every row is equal, no changes.
    assert meta["counts"]["replace"] == 0
    assert meta["counts"]["insert"] == 0
    assert meta["counts"]["delete"] == 0
    assert meta["total_rows"] == meta["left_lines"] == meta["right_lines"]


def test_diff_meta_between_input_and_merged(client):
    agg_id = _merge_cdx(client)
    meta = client.get(
        f"/api/reports/{agg_id}/diff/meta",
        params={"left": "input:0", "right": "merged"},
    ).json()
    # The merged output differs from a single input -> some changes exist.
    changed = (
        meta["counts"]["replace"]
        + meta["counts"]["insert"]
        + meta["counts"]["delete"]
    )
    assert changed > 0
    assert meta["total_rows"] >= max(meta["left_lines"], meta["right_lines"])


def test_diff_meta_unknown_source(client):
    agg_id = _merge_cdx(client)
    assert client.get(
        f"/api/reports/{agg_id}/diff/meta", params={"left": "input:99"}
    ).status_code == 404
    assert client.get(
        f"/api/reports/{agg_id}/diff/meta", params={"left": "bogus"}
    ).status_code == 400


def test_diff_model_cached_and_invalidated(client):
    from report_aggregator.api import diffview, storage

    agg_id = _merge_cdx(client)
    meta_obj = storage.read_meta(agg_id)

    # First call computes + writes a cache file.
    client.get(
        f"/api/reports/{agg_id}/diff/meta",
        params={"left": "input:0", "right": "merged"},
    )
    left_path = diffview.resolve_source(meta_obj, agg_id, "input:0")
    right_path = diffview.resolve_source(meta_obj, agg_id, "merged")
    cache_path = diffview._diff_cache_path(agg_id, left_path, right_path)
    assert cache_path.exists()
    first_sig = cache_path.stat().st_mtime_ns

    # Second call is served from cache (same file, not rewritten).
    client.get(
        f"/api/reports/{agg_id}/diff/meta",
        params={"left": "input:0", "right": "merged"},
    )
    assert cache_path.stat().st_mtime_ns == first_sig

    # Rewriting the merged output changes its signature -> a new cache key.
    import json as _json

    raw = client.get(f"/api/reports/{agg_id}/raw").text
    doc = _json.loads(raw)
    doc["components"].append({"type": "library", "name": "NEW"})
    new_content = _json.dumps(doc, indent=4)
    client.put(f"/api/reports/{agg_id}/document", json={"content": new_content, "who": "x"})

    new_right = diffview.resolve_source(storage.read_meta(agg_id), agg_id, "merged")
    new_cache = diffview._diff_cache_path(agg_id, left_path, new_right)
    assert new_cache != cache_path  # key changed because the source changed
    client.get(
        f"/api/reports/{agg_id}/diff/meta",
        params={"left": "input:0", "right": "merged"},
    )
    assert new_cache.exists()


def test_field_tree_cached_and_invalidated(client):
    from report_aggregator.api import fieldtree_cache, storage

    agg_id = _merge_cdx(client)
    meta_obj = storage.read_meta(agg_id)
    merged = storage.merged_path(agg_id, meta_obj)
    sidecar = storage.sidecar_path(agg_id, meta_obj)

    # Merge pre-warms the cache; first fields read should not rewrite it.
    cache_path = fieldtree_cache.cache_path(agg_id, merged, sidecar)
    assert cache_path.exists()
    first_mtime = cache_path.stat().st_mtime_ns

    client.get(f"/api/reports/{agg_id}/fields")
    assert cache_path.stat().st_mtime_ns == first_mtime

    # Second read is still served from the same cache file.
    client.get(f"/api/reports/{agg_id}/fields")
    assert cache_path.stat().st_mtime_ns == first_mtime

    # Editing rewrites merged output + sidecar -> new cache key.
    tree = client.get(f"/api/reports/{agg_id}/fields").json()
    leaf = _first_string_leaf(tree)
    client.post(
        f"/api/reports/{agg_id}/edits",
        json={
            "op": "replace",
            "path": leaf["path"],
            "value": "CACHE-INVALIDATION-TEST",
            "who": "cache-test",
            "reason": "cache invalidation",
        },
    )

    meta_obj = storage.read_meta(agg_id)
    merged = storage.merged_path(agg_id, meta_obj)
    sidecar = storage.sidecar_path(agg_id, meta_obj)
    new_cache = fieldtree_cache.cache_path(agg_id, merged, sidecar)
    assert new_cache != cache_path
    assert new_cache.exists()

    tree2 = client.get(f"/api/reports/{agg_id}/fields").json()
    node = next(n for n in tree2["nodes"] if n["path"] == leaf["path"])
    assert node["value"] == "CACHE-INVALIDATION-TEST"


def test_compute_diff_opcodes_small(tmp_path):
    """Directly validate opcode assembly for a known small diff."""
    from report_aggregator.api import diffview

    left = tmp_path / "a.txt"
    right = tmp_path / "b.txt"
    left.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    right.write_text("a\nB\nc\nd\nd2\ne\n", encoding="utf-8")  # b->B, insert d2

    model = diffview.compute_diff(left, right, a_lines=5, b_lines=6)
    opcodes = [tuple(o) for o in model["opcodes"]]

    # Expected aligned structure:
    #   equal a (0:1 / 0:1)
    #   replace b->B (1:2 / 1:2)
    #   equal c,d (2:4 / 2:4)
    #   insert d2 (4:4 / 4:5)
    #   equal e (4:5 / 5:6)
    assert opcodes == [
        ("equal", 0, 1, 0, 1),
        ("replace", 1, 2, 1, 2),
        ("equal", 2, 4, 2, 4),
        ("insert", 4, 4, 4, 5),
        ("equal", 4, 5, 5, 6),
    ]
    assert model["left_lines"] == 5
    assert model["right_lines"] == 6
    # total_rows = sum of per-opcode spans = 1+1+2+1+1 = 6
    assert model["total_rows"] == 6
    assert model["counts"]["replace"] == 1
    assert model["counts"]["insert"] == 1
    assert model["counts"]["delete"] == 0


def test_compute_diff_identical(tmp_path):
    from report_aggregator.api import diffview

    p = tmp_path / "a.txt"
    q = tmp_path / "b.txt"
    p.write_text("x\ny\nz\n", encoding="utf-8")
    q.write_text("x\ny\nz\n", encoding="utf-8")
    model = diffview.compute_diff(p, q, a_lines=3, b_lines=3)
    assert model["opcodes"] == [["equal", 0, 3, 0, 3]]
    assert model["total_rows"] == 3
    assert model["counts"]["replace"] == 0


# --------------------------------------------------------------------------- #
# Windowed diff rows
# --------------------------------------------------------------------------- #


def _merge_two_files(client, p, q, media):
    with open(p, "rb") as a, open(q, "rb") as b:
        resp = client.post(
            "/api/merge",
            files=[
                ("files", (p.name, a, media)),
                ("files", (q.name, b, media)),
            ],
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["aggregate_id"]


def test_diff_rows_small_known(client, tmp_path):
    # Build two known sources directly and diff via the service for exactness.
    from report_aggregator.api import diffview, storage

    agg_id = _merge_cdx(client)
    meta_obj = storage.read_meta(agg_id)
    # Overwrite the merged file and an input with controlled content.
    left_path = storage.inputs_dir(agg_id) / meta_obj.inputs[0].filename
    right_path = storage.merged_path(agg_id, meta_obj)
    left_path.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    right_path.write_text("a\nB\nc\nd\nd2\ne\n", encoding="utf-8")

    win = client.get(
        f"/api/reports/{agg_id}/diff/rows",
        params={"left": "input:0", "right": "merged", "start": 0, "count": 100},
    ).json()
    assert win["total_rows"] == 6
    rows = win["rows"]
    assert len(rows) == 6
    assert rows[0] == {"type": "equal", "left_no": 1, "right_no": 1, "left": "a", "right": "a"}
    assert rows[1] == {"type": "replace", "left_no": 2, "right_no": 2, "left": "b", "right": "B"}
    assert rows[2]["type"] == "equal" and rows[2]["left"] == "c"
    assert rows[3]["type"] == "equal" and rows[3]["left"] == "d"
    # Inserted row: left absent, right present.
    assert rows[4] == {"type": "insert", "left_no": None, "right_no": 5, "left": None, "right": "d2"}
    assert rows[5]["type"] == "equal" and rows[5]["left"] == "e"


def test_diff_rows_windowing_across_boundaries(client):
    from report_aggregator.api import diffview, storage

    agg_id = _merge_cdx(client)
    meta_obj = storage.read_meta(agg_id)
    left_path = storage.inputs_dir(agg_id) / meta_obj.inputs[0].filename
    right_path = storage.merged_path(agg_id, meta_obj)
    # 50 identical lines, then a change, then more identical lines.
    base = [f"line{i}" for i in range(50)]
    left_path.write_text("\n".join(base + ["X"] + base) + "\n", encoding="utf-8")
    right_path.write_text("\n".join(base + ["Y"] + base) + "\n", encoding="utf-8")

    meta = client.get(
        f"/api/reports/{agg_id}/diff/meta",
        params={"left": "input:0", "right": "merged"},
    ).json()
    total = meta["total_rows"]

    # Fetch in two windows and concatenate; must equal a single full fetch.
    full = client.get(
        f"/api/reports/{agg_id}/diff/rows",
        params={"left": "input:0", "right": "merged", "start": 0, "count": total},
    ).json()["rows"]
    w1 = client.get(
        f"/api/reports/{agg_id}/diff/rows",
        params={"left": "input:0", "right": "merged", "start": 0, "count": 49},
    ).json()["rows"]
    w2 = client.get(
        f"/api/reports/{agg_id}/diff/rows",
        params={"left": "input:0", "right": "merged", "start": 49, "count": total},
    ).json()["rows"]
    assert w1 + w2 == full
    # The changed line is a replace at row 50.
    assert full[50]["type"] == "replace"
    assert full[50]["left"] == "X" and full[50]["right"] == "Y"


def test_diff_rows_validation(client):
    agg_id = _merge_cdx(client)
    assert client.get(
        f"/api/reports/{agg_id}/diff/rows", params={"count": 0}
    ).status_code == 400
    assert client.get(
        f"/api/reports/{agg_id}/diff/rows", params={"start": -5}
    ).status_code == 400
    assert client.get(
        f"/api/reports/{agg_id}/diff/rows", params={"left": "bogus"}
    ).status_code == 400


# --------------------------------------------------------------------------- #
# Diff search (backend-assisted find)
# --------------------------------------------------------------------------- #


def _setup_known_diff(client):
    """Create an aggregate with controlled content; return agg_id."""
    from report_aggregator.api import storage

    agg_id = _merge_cdx(client)
    meta_obj = storage.read_meta(agg_id)
    left_path = storage.inputs_dir(agg_id) / meta_obj.inputs[0].filename
    right_path = storage.merged_path(agg_id, meta_obj)
    left_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    right_path.write_text("alpha\nBETA\ngamma\ndelta\n", encoding="utf-8")
    return agg_id


def test_diff_search_finds_matches(client):
    agg_id = _setup_known_diff(client)
    res = client.get(
        f"/api/reports/{agg_id}/diff/search",
        params={"left": "input:0", "right": "merged", "q": "alpha"},
    ).json()
    assert res["total"] >= 1
    # "alpha" appears on both sides of the equal row → at least one match.
    assert any(m["side"] in ("left", "right") for m in res["matches"])
    rows_returned = {m["row"] for m in res["matches"]}
    assert 0 in rows_returned  # row 0 is the equal "alpha" line


def test_diff_search_case_insensitive(client):
    agg_id = _setup_known_diff(client)
    res_ci = client.get(
        f"/api/reports/{agg_id}/diff/search",
        params={"left": "input:0", "right": "merged", "q": "beta", "case_sensitive": "false"},
    ).json()
    # Both "beta" (left) and "BETA" (right) should match case-insensitively.
    sides = {m["side"] for m in res_ci["matches"]}
    assert "left" in sides and "right" in sides


def test_diff_search_case_sensitive(client):
    agg_id = _setup_known_diff(client)
    res = client.get(
        f"/api/reports/{agg_id}/diff/search",
        params={"left": "input:0", "right": "merged", "q": "BETA", "case_sensitive": "true"},
    ).json()
    # Only the right side has "BETA" in uppercase.
    assert all(m["side"] == "right" for m in res["matches"])


def test_diff_search_no_matches(client):
    agg_id = _setup_known_diff(client)
    res = client.get(
        f"/api/reports/{agg_id}/diff/search",
        params={"left": "input:0", "right": "merged", "q": "NOTPRESENT_XYZ"},
    ).json()
    assert res["total"] == 0
    assert res["matches"] == []


def test_diff_search_limit_and_truncated(client):
    from report_aggregator.api import storage

    agg_id = _merge_cdx(client)
    meta_obj = storage.read_meta(agg_id)
    left_path = storage.inputs_dir(agg_id) / meta_obj.inputs[0].filename
    right_path = storage.merged_path(agg_id, meta_obj)
    # 100 lines all containing the search term.
    content = "\n".join(f"match_line_{i}" for i in range(100)) + "\n"
    left_path.write_text(content, encoding="utf-8")
    right_path.write_text(content, encoding="utf-8")

    res = client.get(
        f"/api/reports/{agg_id}/diff/search",
        params={"left": "input:0", "right": "merged", "q": "match_line", "limit": 10},
    ).json()
    assert res["total"] == 10
    assert res["truncated"] is True


def test_diff_search_validation(client):
    agg_id = _merge_cdx(client)
    assert client.get(
        f"/api/reports/{agg_id}/diff/search", params={"q": ""}
    ).status_code == 400
    assert client.get(
        f"/api/reports/{agg_id}/diff/search", params={"q": "x", "limit": 0}
    ).status_code == 400
    assert client.get(
        f"/api/reports/{agg_id}/diff/search", params={"q": "x", "left": "bogus"}
    ).status_code == 400


# --------------------------------------------------------------------------- #
# Large-document save: memory-safe verify=False path
# --------------------------------------------------------------------------- #


def test_large_document_save_records_granular_patches(client, monkeypatch):
    """When content exceeds REPORT_AGGREGATOR_DIFF_VERIFY_MAX_BYTES the save still
    records granular patches (verify=False skips only the deepcopy re-check)."""
    # Force the threshold to 1 byte so *any* save triggers the large-file path.
    monkeypatch.setenv("REPORT_AGGREGATOR_DIFF_VERIFY_MAX_BYTES", "1")

    agg_id = _merge_cdx(client)
    import json as _json

    raw = client.get(f"/api/reports/{agg_id}/raw").text
    doc = _json.loads(raw)
    doc["components"][0]["name"] = "LARGE-DOC-EDIT"
    new_content = _json.dumps(doc, indent=4)

    resp = client.put(
        f"/api/reports/{agg_id}/document",
        json={"content": new_content, "who": "large-test"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Granular patches were recorded (not just a single root replace due to OOM).
    assert body["changes"] >= 1

    edits = client.get(f"/api/reports/{agg_id}/edits").json()["edits"]
    assert any(e["who"] == "large-test" for e in edits)
    # At least one edit should reference a field path (granular, not root "/").
    assert any(
        e.get("patch", {}).get("path", "/") != "/"
        for e in edits
        if e.get("who") == "large-test"
    )

    # Field tree reflects the edit.
    tree = client.get(f"/api/reports/{agg_id}/fields").json()
    node = next(n for n in tree["nodes"] if n["path"] == "/components/0/name")
    assert node["value"] == "LARGE-DOC-EDIT"


def test_large_document_save_still_validates(client, monkeypatch):
    """Validation (adapter.load) always runs even on the large-file path."""
    monkeypatch.setenv("REPORT_AGGREGATOR_DIFF_VERIFY_MAX_BYTES", "1")
    agg_id = _merge_cdx(client)
    resp = client.put(
        f"/api/reports/{agg_id}/document",
        json={"content": "{ not valid json at all !!!", "who": "x"},
    )
    assert resp.status_code == 422


def test_small_document_save_uses_verified_path(client, monkeypatch):
    """Below the threshold the original verify=True path runs unchanged."""
    # Very large threshold: all CDX fixtures are well below 100 MB.
    monkeypatch.setenv("REPORT_AGGREGATOR_DIFF_VERIFY_MAX_BYTES", str(100 * 1024 * 1024))
    agg_id = _merge_cdx(client)
    import json as _json

    raw = client.get(f"/api/reports/{agg_id}/raw").text
    doc = _json.loads(raw)
    doc["components"][0]["name"] = "VERIFIED-EDIT"
    new_content = _json.dumps(doc, indent=4)

    resp = client.put(
        f"/api/reports/{agg_id}/document",
        json={"content": new_content, "who": "small-test"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["changes"] >= 1
