"""Shared pytest fixtures."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _close_log_handlers_after_test() -> Iterator[None]:
    """Tear down any logging FileHandlers a test installed.

    Without this, ``configure_logging()`` leaves the daily-log FileHandler
    open across tests; pytest's resource-warning filter then fails the
    next test that touches a different temp dir.
    """
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()
        root.removeHandler(h)


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


@pytest.fixture
def disabled_proxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the MCP proxy at a non-existent entry script.

    Tests that spin up the full Starlette app (lifespan included) need
    the proxy to fail-fast rather than try to launch miscusi-peek's
    Python child — that would hang when CE isn't running.
    """
    fake = tmp_path / "no-such-entry.py"
    monkeypatch.setenv("CEGM_PROXY_ENTRY", os.fspath(fake))
