# SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Small in-process job registry with persisted status files."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from report_aggregator.api import storage


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jobs_dir() -> Path:
    path = storage.workspace_root() / "integration_jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def _write(state: dict) -> None:
    path = job_path(state["job_id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_job(job_id: str) -> dict | None:
    path = job_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class JobHandle:
    job_id: str

    def update(self, **changes) -> None:
        state = read_job(self.job_id)
        if state is None:
            return
        state.update(changes)
        state["updated_at"] = _now()
        _write(state)


def start_job(total: int, worker: Callable[[JobHandle], str]) -> dict:
    job_id = str(uuid.uuid4())
    state = {
        "job_id": job_id,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "total": total,
        "completed": 0,
        "error": None,
        "aggregate_id": None,
    }
    _write(state)
    handle = JobHandle(job_id)

    def run() -> None:
        handle.update(status="running")
        try:
            aggregate_id = worker(handle)
        except Exception as exc:  # noqa: BLE001 - persisted for API clients
            handle.update(status="failed", error=str(exc))
            return
        handle.update(status="succeeded", completed=total, aggregate_id=aggregate_id)

    threading.Thread(target=run, name=f"fossology-merge-{job_id}", daemon=True).start()
    return state
