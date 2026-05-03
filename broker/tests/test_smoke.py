"""Smoke tests — every module imports, version is well-formed, CLI prints help."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from cegm_broker import __version__
from cegm_broker.cli import main
from cegm_broker.config import DEFAULT_LLM_BASE_URL, DEFAULT_PORT, Config


def test_version_well_formed() -> None:
    """Public version is a non-empty PEP 440-ish string."""
    assert isinstance(__version__, str)
    assert __version__.split(".")[0].isdigit()


def test_default_config_round_trip(isolated_data_dir: Path) -> None:
    """Saving and reloading a default config preserves all values."""
    cfg = Config()
    assert cfg.server.port == DEFAULT_PORT
    assert cfg.llm.base_url == DEFAULT_LLM_BASE_URL
    cfg.save()

    loaded = Config.load()
    assert loaded.model_dump() == cfg.model_dump()


def test_sanitized_config_strips_api_key(isolated_data_dir: Path) -> None:
    """The sanitized view never exposes the raw API key."""
    cfg = Config()
    cfg.llm.api_key = type(cfg.llm.api_key)("super-secret")
    cfg.save()

    s = cfg.sanitized()
    assert s["llm"]["api_key"] == "***"
    # And the secret really is on disk (we accept that; ACL is the boundary):
    raw = json.loads((isolated_data_dir / "config.json").read_text(encoding="utf-8"))
    assert raw["llm"]["api_key"] == "super-secret"


def test_cli_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """``cegm-broker --version`` prints and exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_cli_print_config_exits_zero(isolated_data_dir: Path) -> None:
    """``cegm-broker --print-config`` emits valid JSON of the sanitized config."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--print-config"])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["server"]["port"] == DEFAULT_PORT
    assert "llm" in payload
