"""Persistent integration configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from report_aggregator.api import storage

CONFIG_FILENAME = "integrations.json"
DEFAULT_TIMEOUT_SECONDS = 30.0


class IntegrationConfigError(ValueError):
    """Raised when an integration is not configured correctly."""


@dataclass
class FossologyConfig:
    base_url: str = ""
    token: str | None = None
    group_name: str | None = None
    folder_id: int | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def configured(self) -> bool:
        return bool(self.base_url.strip() and self.token)

    def resolve_token(self) -> str:
        token = (self.token or "").strip()
        if not token:
            raise IntegrationConfigError("FOSSology token is not configured")
        if token.startswith("env:"):
            env_name = token[4:].strip()
            if not env_name:
                raise IntegrationConfigError("FOSSology token environment variable is empty")
            value = os.environ.get(env_name)
            if not value:
                raise IntegrationConfigError(
                    f"FOSSology token environment variable '{env_name}' is not set"
                )
            return value
        return token

    def redacted(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "base_url": self.base_url,
            "group_name": self.group_name or "",
            "folder_id": self.folder_id,
            "timeout_seconds": self.timeout_seconds,
            "has_token": bool(self.token),
            "token_is_env_ref": bool((self.token or "").startswith("env:")),
        }


def config_path() -> Path:
    return storage.workspace_root() / CONFIG_FILENAME


def _read_all() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_all(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, indent=2).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def load_fossology_config() -> FossologyConfig:
    all_data = _read_all()
    raw = (all_data.get("fossology") or {}) if isinstance(all_data, dict) else {}
    # Legacy verify_tls keys in integrations.json are ignored intentionally.
    return FossologyConfig(
        base_url=str(raw.get("base_url") or ""),
        token=raw.get("token") or None,
        group_name=raw.get("group_name") or None,
        folder_id=raw.get("folder_id"),
        timeout_seconds=float(raw.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
    )


def save_fossology_config(payload: dict[str, Any]) -> FossologyConfig:
    data = _read_all()
    current = data.get("fossology") or {}

    next_config = {
        "base_url": str(payload.get("base_url", current.get("base_url") or "")).strip(),
        "group_name": (
            str(payload.get("group_name", current.get("group_name") or "")).strip() or None
        ),
        "folder_id": payload.get("folder_id", current.get("folder_id")),
        "timeout_seconds": float(
            payload.get("timeout_seconds", current.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
        ),
    }

    if "token" in payload:
        token = str(payload.get("token") or "").strip()
        next_config["token"] = token or None
    else:
        next_config["token"] = current.get("token")

    if next_config["folder_id"] in ("", None):
        next_config["folder_id"] = None
    elif next_config["folder_id"] is not None:
        next_config["folder_id"] = int(next_config["folder_id"])

    if next_config["timeout_seconds"] <= 0:
        raise IntegrationConfigError("timeout_seconds must be greater than zero")

    data["fossology"] = next_config
    _write_all(data)
    return load_fossology_config()
