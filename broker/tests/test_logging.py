"""Structured-logging tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from cegm_broker._logging import configure_logging, get_logger


def test_configure_emits_jsonl_to_file(isolated_data_dir: Path) -> None:
    """A single ``log.info`` produces a parseable JSONL line on disk."""
    configure_logging("debug")
    log = get_logger("test.cegm")
    log.info("broker.tool_called", extra={"tool": "memory_read", "addr": "0x1234"})

    # Flush all handlers so the log line lands in the file synchronously.
    logging.shutdown()

    log_files = list((isolated_data_dir / "logs").glob("broker-*.jsonl"))
    assert log_files, "no daily log file created"
    raw = log_files[0].read_text(encoding="utf-8").splitlines()
    assert raw, "log file is empty"

    last = json.loads(raw[-1])
    assert last["event"] == "broker.tool_called"
    assert last["level"] == "info"
    assert last["logger"] == "test.cegm"
    assert last["tool"] == "memory_read"
    assert last["addr"] == "0x1234"
    assert last["ts"].endswith("Z")
