"""Filesystem-path resolution tests."""

from __future__ import annotations

from pathlib import Path

from cegm_broker._paths import (
    activity_dir,
    config_path,
    daily_log_file,
    data_root,
    ensure_dir,
    logs_dir,
    snapshots_dir,
)


def test_data_root_honors_override(isolated_data_dir: Path) -> None:
    """``CEGM_DATA_DIR`` env var wins over ``%LOCALAPPDATA%``."""
    assert data_root() == isolated_data_dir
    assert config_path() == isolated_data_dir / "config.json"
    assert logs_dir() == isolated_data_dir / "logs"
    assert activity_dir() == isolated_data_dir / "activity"
    assert snapshots_dir() == isolated_data_dir / "snapshots"


def test_daily_log_file_is_dated(isolated_data_dir: Path) -> None:
    """The daily-rotated log filename embeds an ISO date."""
    p = daily_log_file()
    assert p.parent == logs_dir()
    assert p.name.startswith("broker-")
    assert p.suffix == ".jsonl"


def test_ensure_dir_is_idempotent(isolated_data_dir: Path) -> None:
    """Calling ``ensure_dir`` twice does not raise."""
    p = isolated_data_dir / "nested" / "tree"
    ensure_dir(p)
    ensure_dir(p)
    assert p.is_dir()
