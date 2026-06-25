"""Tests for API workspace storage paths."""

from pathlib import Path

from report_aggregator.api.storage import (
    DEFAULT_WORKSPACE_DIRNAME,
    _project_root,
    workspace_root,
)


def test_project_root_contains_pyproject():
    root = _project_root()
    assert (root / "pyproject.toml").is_file()
    assert root.name == "report-aggregator"


def test_workspace_root_defaults_to_project_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("REPORT_AGGREGATOR_WORKSPACE", raising=False)
    root = workspace_root()
    assert root == _project_root() / DEFAULT_WORKSPACE_DIRNAME
    assert root.is_dir()


def test_workspace_root_env_relative_to_project(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_AGGREGATOR_WORKSPACE", "custom_ws")
    root = workspace_root()
    assert root == _project_root() / "custom_ws"


def test_workspace_root_env_absolute(monkeypatch, tmp_path):
    absolute = tmp_path / "absolute_ws"
    monkeypatch.setenv("REPORT_AGGREGATOR_WORKSPACE", str(absolute))
    assert workspace_root() == absolute
