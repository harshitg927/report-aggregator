"""FOSSology client backed by fossology-python."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlparse

from fossology import Fossology
from fossology.enums import ClearingStatus, ReportFormat
from fossology.exceptions import AuthenticationError, AuthorizationError
from fossology.exceptions import FossologyApiError as LibFossologyApiError
from fossology.obj import Folder, Upload

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


def _server_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        raise IntegrationConfigError("FOSSology base URL is not configured")
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        raise IntegrationConfigError("FOSSology base URL must include scheme and host")
    if cleaned.endswith("/api/v1"):
        cleaned = cleaned[: -len("/api/v1")].rstrip("/")
    elif cleaned.endswith("/api"):
        cleaned = cleaned[: -len("/api")].rstrip("/")
    return cleaned


def _to_report_format(report_format: str) -> ReportFormat | SimpleNamespace:
    try:
        return ReportFormat(report_format)
    except ValueError:
        # fossology-python ReportFormat omits some server formats (e.g. cyclonedx).
        return SimpleNamespace(value=report_format)


def _to_clearing_status(value: str | None) -> ClearingStatus | None:
    if not value:
        return None
    raw = value.strip()
    try:
        return ClearingStatus(raw)
    except ValueError:
        pass
    normalized = raw.replace("_", "").replace("-", "").lower()
    for status in ClearingStatus:
        if status.name.replace("_", "").lower() == normalized:
            return status
        if status.value.replace("_", "").replace("-", "").lower() == normalized:
            return status
    raise FossologyApiError(f"Unsupported FOSSology upload status: {value}", status_code=400)


def _folder_arg(folder_id: int | None) -> Folder | None:
    if folder_id is None:
        return None
    return Folder(id=int(folder_id), name="", description="", parent=None)


def _serialize_folder(folder: Folder) -> dict:
    return {
        "id": folder.id,
        "name": folder.name,
        "description": folder.description,
        "parent": folder.parent,
    }


def _serialize_upload(upload: Upload) -> dict:
    data = {
        "id": upload.id,
        "uploadName": upload.uploadname,
        "description": upload.description,
        "folderId": upload.folderid,
        "folderName": upload.foldername,
        "uploadDate": upload.uploaddate,
        "assignee": upload.assignee,
        "assigneeDate": upload.assigneeDate,
        "closingDate": upload.closeDate,
    }
    if upload.hash is not None:
        data["hash"] = {
            "sha1": getattr(upload.hash, "sha1", None),
            "md5": getattr(upload.hash, "md5", None),
            "sha256": getattr(upload.hash, "sha256", None),
            "size": getattr(upload.hash, "size", None),
        }
    return data


def _map_lib_error(exc: BaseException) -> FossologyApiError:
    if isinstance(exc, FossologyApiError):
        return exc
    if isinstance(exc, AuthorizationError):
        return FossologyApiError(str(exc), status_code=403)
    if isinstance(exc, AuthenticationError):
        return FossologyApiError(str(exc), status_code=401)
    if isinstance(exc, LibFossologyApiError):
        return FossologyApiError(str(exc), status_code=502)
    return FossologyApiError(f"FOSSology request failed: {exc}")


class FossologyClient:
    def __init__(self, config: FossologyConfig):
        self.config = config
        self.server_url = _server_url(config.base_url)
        self.token = config.resolve_token()
        self._foss: Fossology | None = None

    def _api(self) -> Fossology:
        if self._foss is None:
            try:
                foss = Fossology(self.server_url, self.token, version="v1")
                foss.session.verify = True
                self._foss = foss
            except Exception as exc:
                raise _map_lib_error(exc) from exc
        return self._foss

    def _group(self) -> str | None:
        return self.config.group_name or None

    def test_connection(self) -> dict:
        foss = self._api()
        try:
            foss.list_uploads(
                folder=_folder_arg(self.config.folder_id),
                group=self._group(),
                page_size=1,
                page=1,
            )
        except Exception as exc:
            raise _map_lib_error(exc) from exc
        return {"ok": True, "status_code": 200}

    def list_folders(self) -> list[dict]:
        try:
            folders = self._api().list_folders()
        except Exception as exc:
            raise _map_lib_error(exc) from exc
        return [_serialize_folder(folder) for folder in folders]

    def list_uploads(self, params: dict) -> dict:
        foss_params = dict(params)
        folder_id = foss_params.pop("folderId", None)
        if folder_id is None:
            folder_id = self.config.folder_id
        recursive = True
        if "recursive" in foss_params:
            recursive = str(foss_params.pop("recursive")).lower() not in {"false", "0", "no"}
        name = foss_params.pop("name", None)
        status = _to_clearing_status(foss_params.pop("status", None))
        page = int(foss_params.pop("page", 1) or 1)
        page_size = int(foss_params.pop("limit", 100) or 100)
        try:
            uploads, total_pages = self._api().list_uploads(
                folder=_folder_arg(int(folder_id) if folder_id is not None else None),
                group=self._group(),
                recursive=recursive,
                name=name,
                status=status,
                page_size=page_size,
                page=page,
            )
        except Exception as exc:
            raise _map_lib_error(exc) from exc
        return {
            "uploads": [_serialize_upload(upload) for upload in uploads],
            "total_pages": str(total_pages) if total_pages is not None else None,
        }

    def get_upload(self, upload_id: int) -> dict:
        try:
            upload = self._api().detail_upload(int(upload_id), group=self._group())
        except Exception as exc:
            raise _map_lib_error(exc) from exc
        return _serialize_upload(upload)

    def schedule_report(self, upload_id: int, report_format: str) -> ScheduledReport:
        try:
            upload = self._api().detail_upload(int(upload_id), group=self._group())
            job_id = self._api().generate_report(
                upload,
                report_format=_to_report_format(report_format),
                group=self._group(),
            )
        except Exception as exc:
            raise _map_lib_error(exc) from exc
        return ScheduledReport(job_id=int(job_id))

    def download_report(self, report_job_id: int) -> bytes:
        try:
            content, _name = self._api().download_report(
                int(report_job_id),
                group=self._group(),
                wait_time=0,
            )
        except Exception as exc:
            raise _map_lib_error(exc) from exc
        return content

    def wait_for_report(self, report_job_id: int) -> bytes:
        wait_time = max(int(self.config.timeout_seconds), 1)
        try:
            content, _name = self._api().download_report(
                int(report_job_id),
                group=self._group(),
                wait_time=wait_time,
            )
        except Exception as exc:
            raise _map_lib_error(exc) from exc
        return content
