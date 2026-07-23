"""Tests for FOSSology integration routes and client behavior."""

from __future__ import annotations

import stat
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from report_aggregator.api import storage
from report_aggregator.api.app import create_app
from report_aggregator.api import routes
from report_aggregator.integrations import config as integration_config
from report_aggregator.integrations.fossology import FossologyClient, FossologyConfig
from fossology.obj import Folder, Upload

FIXTURES = Path(__file__).parent / "fixtures" / "fossology-reports"
CDX_A = FIXTURES / "CYCLONEDX_JSON_zlib132.zip.json"
CDX_B = FIXTURES / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_AGGREGATOR_WORKSPACE", str(tmp_path / "ws"))
    return TestClient(create_app())


def _save_config(client, **overrides):
    payload = {
        "base_url": "https://fossology.example",
        "token": "secret-token",
        "group_name": "fossy",
        "folder_id": 7,
        "timeout_seconds": 10,
    }
    payload.update(overrides)
    resp = client.put("/api/integrations/config", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["fossology"]


def _wait_job(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        body = client.get(f"/api/integrations/jobs/{job_id}").json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def _fake_upload(**overrides):
    data = {
        "folderid": 7,
        "foldername": "Software Repository",
        "id": 11,
        "description": "",
        "uploadname": "pkg",
        "uploaddate": "2024-01-01",
        "hash": {"sha1": "abc", "md5": "def", "sha256": "ghi", "size": 1},
    }
    data.update(overrides)
    return Upload(**data)


class FakeFossology:
    def __init__(self, url, token, version="v1"):
        self.host = url
        self.token = token
        self.version = version
        self.session = SimpleNamespace(verify=True, headers={"Authorization": f"Bearer {token}"})
        self.calls = []

    def list_uploads(self, **kwargs):
        self.calls.append(("list_uploads", kwargs))
        return [_fake_upload()], 3

    def list_folders(self):
        self.calls.append(("list_folders", {}))
        return [
            Folder(id=1, name="Software Repository", description="", parent=None),
            Folder(id=3, name="Third Party", description="", parent=1),
        ]

    def detail_upload(self, upload_id, group=None, wait_time=0):
        self.calls.append(("detail_upload", {"upload_id": upload_id, "group": group}))
        return _fake_upload(id=upload_id, uploadname=f"upload-{upload_id}")

    def generate_report(self, upload, report_format=None, group=None):
        self.calls.append(
            (
                "generate_report",
                {
                    "upload_id": upload.id,
                    "report_format": getattr(report_format, "value", report_format),
                    "group": group,
                },
            )
        )
        return 1000 + upload.id

    def download_report(self, report_id, group=None, wait_time=0):
        self.calls.append(
            ("download_report", {"report_id": report_id, "group": group, "wait_time": wait_time})
        )
        return b"report bytes", "report.txt"


def test_config_save_read_redacts_token_and_uses_restrictive_permissions(client):
    body = _save_config(client)
    assert body["configured"] is True
    assert body["has_token"] is True
    assert "secret-token" not in str(body)
    assert "verify_tls" not in body

    path = integration_config.config_path()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    saved = path.read_text(encoding="utf-8")
    assert "verify_tls" not in saved

    body = client.put(
        "/api/integrations/config",
        json={"base_url": "https://fossology.changed", "timeout_seconds": 5},
    ).json()["fossology"]
    assert body["base_url"] == "https://fossology.changed"
    assert body["has_token"] is True

    body = client.put("/api/integrations/config", json={"token": ""}).json()["fossology"]
    assert body["has_token"] is False


def test_env_token_resolves_only_server_side(client, monkeypatch):
    _save_config(client, token="env:FOSSOLOGY_TOKEN")
    monkeypatch.setenv("FOSSOLOGY_TOKEN", "resolved-token")
    seen = {}

    def fake_fossology(url, token, version="v1"):
        seen["url"] = url
        seen["token"] = token
        seen["version"] = version
        return FakeFossology(url, token, version=version)

    monkeypatch.setattr("report_aggregator.integrations.fossology.Fossology", fake_fossology)
    resp = client.post("/api/integrations/fossology/test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert seen["token"] == "resolved-token"
    assert seen["url"] == "https://fossology.example"
    assert "resolved-token" not in str(client.get("/api/integrations/config").json())


def test_upload_listing_passes_filters_to_library(client, monkeypatch):
    _save_config(client)
    fake = FakeFossology("https://fossology.example", "secret-token")

    def fake_fossology(url, token, version="v1"):
        return fake

    monkeypatch.setattr("report_aggregator.integrations.fossology.Fossology", fake_fossology)
    resp = client.get(
        "/api/integrations/fossology/uploads",
        params={"name": "pkg", "status": "open", "page": 2, "limit": 20},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_pages"] == "3"
    assert body["uploads"][0]["uploadName"] == "pkg"

    method, kwargs = fake.calls[-1]
    assert method == "list_uploads"
    assert kwargs["group"] == "fossy"
    assert kwargs["name"] == "pkg"
    assert kwargs["page"] == 2
    assert kwargs["page_size"] == 20
    assert kwargs["folder"].id == 7
    assert kwargs["status"].value == "Open"


def test_list_folders_returns_folder_array(client, monkeypatch):
    _save_config(client)
    fake = FakeFossology("https://fossology.example", "secret-token")

    monkeypatch.setattr(
        "report_aggregator.integrations.fossology.Fossology",
        lambda url, token, version="v1": fake,
    )
    resp = client.get("/api/integrations/fossology/folders")
    assert resp.status_code == 200
    body = resp.json()
    assert body["folders"][0]["name"] == "Software Repository"
    assert body["folders"][1]["parent"] == 1
    assert fake.calls[0][0] == "list_folders"


def test_wait_for_report_uses_library_download_with_timeout(monkeypatch):
    cfg = FossologyConfig(base_url="https://fossology.example", token="t", timeout_seconds=5)
    fake = FakeFossology("https://fossology.example", "t")
    monkeypatch.setattr(
        "report_aggregator.integrations.fossology.Fossology",
        lambda url, token, version="v1": fake,
    )
    client = FossologyClient(cfg)
    assert client.wait_for_report(42) == b"report bytes"
    method, kwargs = fake.calls[-1]
    assert method == "download_report"
    assert kwargs == {"report_id": 42, "group": None, "wait_time": 5}
    assert client._api().session.verify is True


def test_tls_verify_always_enabled(monkeypatch):
    cfg = FossologyConfig(base_url="https://fossology.example", token="t")
    fake = FakeFossology("https://fossology.example", "t")
    fake.session.verify = False
    monkeypatch.setattr(
        "report_aggregator.integrations.fossology.Fossology",
        lambda url, token, version="v1": fake,
    )
    client = FossologyClient(cfg)
    client._api()
    assert fake.session.verify is True


def test_server_url_strips_api_suffix(monkeypatch):
    cfg = FossologyConfig(base_url="https://fossology.example/repo/api/v1", token="t")
    seen = {}

    def fake_fossology(url, token, version="v1"):
        seen["url"] = url
        return FakeFossology(url, token, version=version)

    monkeypatch.setattr("report_aggregator.integrations.fossology.Fossology", fake_fossology)
    FossologyClient(cfg)._api()
    assert seen["url"] == "https://fossology.example/repo"


def test_merge_from_uploads_creates_normal_aggregate(client, monkeypatch):
    _save_config(client)

    class FakeScheduled:
        def __init__(self, job_id):
            self.job_id = job_id

    class FakeClient:
        def __init__(self, cfg):
            self.config = cfg

        def get_upload(self, upload_id):
            return {"id": upload_id, "uploadName": f"upload-{upload_id}"}

        def schedule_report(self, upload_id, report_format):
            return FakeScheduled(1000 + upload_id)

        def wait_for_report(self, report_job_id):
            return (CDX_A if report_job_id == 1001 else CDX_B).read_bytes()

    monkeypatch.setattr(routes, "FossologyClient", FakeClient)
    resp = client.post(
        "/api/integrations/fossology/merge-from-uploads",
        json={"upload_ids": [1, 2], "report_format": "cyclonedx"},
    )
    assert resp.status_code == 200, resp.text
    job = _wait_job(client, resp.json()["job_id"])
    assert job["status"] == "succeeded"
    aggregate_id = job["aggregate_id"]

    report = client.get(f"/api/reports/{aggregate_id}").json()
    assert report["format"] == "cyclonedx"
    assert report["counts"]["inputs"] == 2
    assert report["inputs"][0]["origin"]["system"] == "fossology"
    assert report["inputs"][0]["origin"]["report_job_id"] == 1001


def test_failed_fossology_job_does_not_create_successful_aggregate(client, monkeypatch):
    _save_config(client)

    class FakeScheduled:
        job_id = 99

    class FakeClient:
        def __init__(self, cfg):
            self.config = cfg

        def get_upload(self, upload_id):
            return {"id": upload_id, "uploadName": f"upload-{upload_id}"}

        def schedule_report(self, upload_id, report_format):
            return FakeScheduled()

        def wait_for_report(self, report_job_id):
            return b"not a cyclonedx report"

    monkeypatch.setattr(routes, "FossologyClient", FakeClient)
    resp = client.post(
        "/api/integrations/fossology/merge-from-uploads",
        json={"upload_ids": [1, 2], "report_format": "cyclonedx"},
    )
    job = _wait_job(client, resp.json()["job_id"])
    assert job["status"] == "failed"
    assert job["aggregate_id"] is None
    assert storage.list_aggregate_ids() == []
