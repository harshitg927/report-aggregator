"""Pytest fixtures and configuration."""

from pathlib import Path
import pytest

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "fossology-reports"

@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the copied test fixtures directory."""
    return _FIXTURES_DIR

@pytest.fixture
def cdxfckeditor_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "CYCLONEDX_JSON_fckeditor-2.4.8.zip.json"

@pytest.fixture
def cdxzlib_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "CYCLONEDX_JSON_zlib132.zip.json"

@pytest.fixture
def spdx2fckeditor_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "SPDX2TV_fckeditor-2.4.8.zip.spdx"

@pytest.fixture
def spdx2zlib_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "SPDX2TV_zlib132.zip.spdx"
