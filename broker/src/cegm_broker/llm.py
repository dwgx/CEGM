"""OpenAI-compatible LLM client used by the dashboard's chat endpoint.

Default endpoint is DeepSeek (chosen by the project owner). Any other
OpenAI-compatible service works by editing ``llm.base_url`` in
``%LOCALAPPDATA%\\CEGM\\config.json``.

Tool calling routes through the local MCP server (proxied + extras) so the
model gets the same tool surface the dashboard exposes externally.

Phase 1 implementation pending; this module currently exposes the stable
public types so the rest of the broker can import them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cegm_broker._logging import get_logger

if TYPE_CHECKING:
    from cegm_broker.config import LLMConfig

_log = get_logger(__name__)


class LLMClient:
    """Wraps the ``openai`` SDK pointed at a configurable base URL.

    The class shell exists in Phase 0 so imports compose; the round-trip
    (chat completion + tool dispatch + SSE streaming for the dashboard)
    lands in Phase 1.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    @property
    def model(self) -> str:
        return self._config.model
