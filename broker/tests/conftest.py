"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``CEGM_DATA_DIR`` to a per-test temp dir.

    Any code path that writes config / logs / snapshots resolves under here,
    so tests don't pollute the user's real ``%LOCALAPPDATA%\\CEGM`` tree.
    ``monkeypatch`` automatically restores the env var when the test ends,
    so no explicit teardown is needed.
    """
    monkeypatch.setenv("CEGM_DATA_DIR", os.fspath(tmp_path))
    return tmp_path
