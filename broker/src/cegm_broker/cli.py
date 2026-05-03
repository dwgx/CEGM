"""Command-line entry point.

Kept argparse-only (no ``click``/``typer`` dep) so the CLI surface is
trivial to reason about and the broker has no extra wheel pull.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from cegm_broker import __version__
from cegm_broker._logging import configure_logging, get_logger
from cegm_broker.config import Config
from cegm_broker.server import run

_log = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cegm-broker",
        description="CheatEngineGM broker — MCP HTTP server, dashboard, LLM client.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cegm-broker {__version__}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP port to bind on 127.0.0.1 (default: from config.json or 27077).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host (default: 127.0.0.1). Changing this widens the security boundary.",
    )
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=None,
        help="Exit when this PID disappears. Set by the CE Lua autorun shim.",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Dump the resolved configuration as JSON and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = _build_parser().parse_args(argv)
    configure_logging(args.log_level)

    config = Config.load()
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port

    if args.print_config:
        print(json.dumps(config.sanitized(), indent=2, ensure_ascii=False))
        return 0

    _log.info(
        "broker.starting",
        extra={
            "version": __version__,
            "host": config.server.host,
            "port": config.server.port,
            "parent_pid": args.parent_pid,
        },
    )

    run(host=config.server.host, port=config.server.port, parent_pid=args.parent_pid)
    return 0
