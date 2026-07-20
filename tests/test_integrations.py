"""Tests for FOSSology integration routes and client behavior."""

from __future__ import annotations

import stat
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from report_aggregator.api import storage
from report_aggregator.api.app import create_app
from report_aggregator.api import routes
from report_aggregator.integrations import config as integration_config
from report_aggregator.integrations.fossology import FossologyClient, FossologyConfig

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
        "verify_tls": True,
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


def test_config_save_read_redacts_token_and_uses_restrictive_permissions(client):
    body = _save_config(client)
    assert body["configured"] is True
    assert body["has_token"] is True
    assert "secret-token" not in str(body)

    path = integration_config.config_path()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600

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

    def fake_request(method, url, **kwargs):
        seen["headers"] = kwargs["headers"]
        request = httpx.Request(method, url)
        return httpx.Response(200, json=[], request=request)

    monkeypatch.setattr("report_aggregator.integrations.fossology.httpx.request", fake_request)
    resp = client.post("/api/integrations/fossology/test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert seen["headers"]["Authorization"] == "Bearer resolved-token"
    assert "resolved-token" not in str(client.get("/api/integrations/config").json())


def test_upload_listing_sends_auth_group_and_query_params(client, monkeypatch):
    _save_config(client)
    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update(method=method, url=url, headers=kwargs["headers"], params=kwargs["params"])
        request = httpx.Request(method, url)
        return httpx.Response(
            200,
            json=[{"id": 11, "uploadName": "pkg"}],
            headers={"X-Total-Pages": "3"},
            request=request,
        )

    monkeypatch.setattr("report_aggregator.integrations.fossology.httpx.request", fake_request)
    resp = client.get(
        "/api/integrations/fossology/uploads",
        params={"name": "pkg", "status": "open", "page": 2, "limit": 20},
    )
    assert resp.status_code == 200
    assert resp.json()["total_pages"] == "3"
    assert seen["url"] == "https://fossology.example/api/v1/uploads"
    assert seen["headers"]["Authorization"] == "Bearer secret-token"
    assert seen["headers"]["groupName"] == "fossy"
    assert seen["params"] == {
        "folderId": 7,
        "name": "pkg",
        "status": "open",
        "page": 2,
        "limit": 20,
    }


def test_retry_after_polling_is_honored(monkeypatch):
    cfg = FossologyConfig(base_url="https://fossology.example", token="t", timeout_seconds=5)
    client = FossologyClient(cfg)
    calls = []
    sleeps = []

    def fake_request(method, url, **kwargs):
        calls.append(url)
        request = httpx.Request(method, url)
        if len(calls) == 1:
            return httpx.Response(503, json={"message": "try later"}, headers={"Retry-After": "2"}, request=request)
        return httpx.Response(200, content=b"report bytes", request=request)

    monkeypatch.setattr("report_aggregator.integrations.fossology.httpx.request", fake_request)
    monkeypatch.setattr("report_aggregator.integrations.fossology.time.sleep", sleeps.append)
    assert client.wait_for_report(42) == b"report bytes"
    assert sleeps == [2.0]


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
