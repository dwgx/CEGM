"""Entry point for ``python -m cegm_broker`` and the ``cegm-broker`` script.

Kept deliberately minimal — argument parsing and process orchestration live
in :mod:`cegm_broker.cli`. This module only delegates so that the import
surface for entry points stays tiny.
"""

from __future__ import annotations

import sys

from cegm_broker.cli import main


def _entry() -> None:
    """Run the CLI, mapping its return code to a process exit."""
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover
    _entry()
