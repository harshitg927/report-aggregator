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
