"""OpenAI-compatible LLM client used by the dashboard's chat endpoint.

Default endpoint is DeepSeek (chosen by the project owner); any other
OpenAI-compatible service works by editing ``llm.base_url`` in
``%LOCALAPPDATA%\\CEGM\\config.json``.

Tool calling routes through a caller-supplied dispatcher so the same
class powers both the dashboard chat and any future "in-CE chat" feature.
The dispatcher receives a tool name + arguments, returns the textual
result; we wrap it back into the ``role: "tool"`` message envelope.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final

from mcp import types
from openai import AsyncOpenAI

from cegm_broker._logging import get_logger
from cegm_broker.config import LLMConfig

_log = get_logger(__name__)

# Hard cap on tool-call iterations per user message. Beyond this we stop
# and return whatever assistant text we have, to prevent runaway loops.
_MAX_TOOL_ITERATIONS: Final[int] = 8

ToolDispatcher = Callable[[str, dict[str, Any]], Awaitable[Sequence[types.ContentBlock]]]


def mcp_tools_to_openai(tools: Sequence[types.Tool]) -> list[dict[str, Any]]:
    """Translate MCP ``Tool`` definitions into OpenAI ``tools`` parameter shape."""
    out: list[dict[str, Any]] = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
        )
    return out


def _content_to_text(content: Sequence[types.ContentBlock]) -> str:
    """Best-effort string rendering of an MCP tool-result for the LLM.

    OpenAI tool messages are strings; we concatenate text blocks and
    summarize anything else (image, resource link) so the model still
    sees *something* meaningful when a tool returns non-text.
    """
    parts: list[str] = []
    for block in content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        else:
            kind = getattr(block, "type", block.__class__.__name__)
            parts.append(f"[non-text content: {kind}]")
    return "\n".join(parts) if parts else "(empty)"


class LLMClient:
    """Wraps the ``openai`` SDK pointed at a configurable base URL.

    Stateless across calls; instantiate once per request or reuse safely.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        # An empty key would crash openai's client; pass a placeholder
        # so the user gets a server-side 401 they can decode, rather than
        # a client-side ValidationError before we ever talk to the LLM.
        api_key = config.api_key.get_secret_value() or "missing-api-key"
        self._client = AsyncOpenAI(base_url=config.base_url, api_key=api_key)

    @property
    def model(self) -> str:
        return self._config.model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[types.Tool],
        dispatcher: ToolDispatcher,
        max_iter: int = _MAX_TOOL_ITERATIONS,
    ) -> dict[str, Any]:
        """Drive an agentic chat-completion loop with tool calling.

        ``messages`` is mutated in place (system + user + assistant + tool
        rows are appended as the loop progresses). Returns the final
        assistant message dict (``{"role": "assistant", "content": str}``).
        Iteration is capped at ``max_iter``; on overflow we append a
        terminal assistant message admitting the cap was hit.
        """
        oa_tools = mcp_tools_to_openai(tools) if tools else None

        for _ in range(max_iter):
            resp = await self._client.chat.completions.create(
                model=self._config.model,
                messages=messages,  # type: ignore[arg-type]
                tools=oa_tools,  # type: ignore[arg-type]
                temperature=self._config.temperature,
                max_tokens=self._config.max_output_tokens,
            )
            choice = resp.choices[0]
            assistant_msg: dict[str, Any] = choice.message.model_dump(exclude_none=True)
            messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                return {"role": "assistant", "content": assistant_msg.get("content", "")}

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError as exc:
                    args = {}
                    _log.warning(
                        "llm.tool_args_invalid",
                        extra={"name": name, "raw": raw_args, "err": repr(exc)},
                    )

                try:
                    content = await dispatcher(name, args)
                    text = _content_to_text(content)
                except Exception as exc:
                    text = f"(tool error: {exc!r})"
                    _log.warning("llm.tool_dispatch_error", extra={"name": name, "err": text})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "name": name,
                        "content": text,
                    }
                )

        truncated = {"role": "assistant", "content": "(reached max tool-iteration cap)"}
        messages.append(truncated)
        return truncated
