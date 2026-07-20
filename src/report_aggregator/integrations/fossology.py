"""FOSSology REST client used by the API integration routes."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from report_aggregator.integrations.config import FossologyConfig, IntegrationConfigError


class FossologyApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass
class ScheduledReport:
    job_id: int
    download_url: str | None = None


def _api_base_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        raise IntegrationConfigError("FOSSology base URL is not configured")
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        raise IntegrationConfigError("FOSSology base URL must include scheme and host")
    if cleaned.endswith("/api/v1"):
        return cleaned
    if cleaned.endswith("/api"):
        return f"{cleaned}/v1"
    return f"{cleaned}/api/v1"


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(body, dict):
        for key in ("message", "detail", "error"):
            if body.get(key):
                return str(body[key])
        if body.get("code") and body.get("type"):
            return f"{body['type']} ({body['code']})"
    return str(body)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


class FossologyClient:
    def __init__(self, config: FossologyConfig):
        self.config = config
        self.base_url = _api_base_url(config.base_url)
        self.token = config.resolve_token()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.config.group_name:
            headers["groupName"] = self.config.group_name
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(
                method,
                url,
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_tls,
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise FossologyApiError(f"FOSSology request failed: {exc}") from exc
        if response.status_code >= 400:
            raise FossologyApiError(
                _detail(response),
                status_code=response.status_code,
                retry_after=_retry_after(response),
            )
        return response

    def test_connection(self) -> dict:
        params = {"limit": 1}
        if self.config.folder_id is not None:
            params["folderId"] = self.config.folder_id
        response = self._request("GET", "/uploads", headers=self._headers(), params=params)
        return {"ok": True, "status_code": response.status_code}

    def list_folders(self) -> list[dict]:
        response = self._request("GET", "/folders", headers=self._headers())
        data = response.json()
        return data if isinstance(data, list) else []

    def list_uploads(self, params: dict) -> dict:
        foss_params = dict(params)
        extra_headers: dict[str, str] = {}
        if foss_params.get("page") is not None:
            extra_headers["page"] = str(foss_params.pop("page"))
        if foss_params.get("limit") is not None:
            extra_headers["limit"] = str(foss_params.pop("limit"))
        response = self._request(
            "GET",
            "/uploads",
            headers=self._headers(extra_headers),
            params=foss_params,
        )
        return {
            "uploads": response.json(),
            "total_pages": response.headers.get("X-Total-Pages"),
        }

    def get_upload(self, upload_id: int) -> dict:
        response = self._request("GET", f"/uploads/{upload_id}", headers=self._headers())
        data = response.json()
        return data if isinstance(data, dict) else {}

    def schedule_report(self, upload_id: int, report_format: str) -> ScheduledReport:
        response = self._request(
            "GET",
            "/report",
            headers=self._headers({"uploadId": str(upload_id), "reportFormat": report_format}),
        )
        body = response.json()
        message = str(body.get("message") or body.get("detail") or "")
        match = re.search(r"/report/(\d+)\b", message)
        if not match:
            match = re.search(r"\b(\d+)\b", message)
        if not match:
            raise FossologyApiError("FOSSology did not return a report job id")
        return ScheduledReport(job_id=int(match.group(1)), download_url=message or None)

    def download_report(self, report_job_id: int) -> bytes:
        response = self._request("GET", f"/report/{report_job_id}", headers=self._headers())
        return response.content

    def wait_for_report(self, report_job_id: int) -> bytes:
        deadline = time.monotonic() + self.config.timeout_seconds
        while True:
            try:
                return self.download_report(report_job_id)
            except FossologyApiError as exc:
                if exc.status_code != 503:
                    raise
                now = time.monotonic()
                if now >= deadline:
                    raise FossologyApiError(
                        f"Timed out waiting for FOSSology report job {report_job_id}",
                        status_code=exc.status_code,
                    ) from exc
                time.sleep(min(exc.retry_after or 1.0, max(deadline - now, 0.0)))
