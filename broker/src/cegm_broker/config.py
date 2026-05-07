"""Runtime configuration model and on-disk persistence.

The broker has a single source of truth at ``%LOCALAPPDATA%\\CEGM\\config.json``.
Defaults are inlined here; the file is written lazily on first save and the
schema is validated by Pydantic on every load. The dashboard mutates config
through the ``/api/config`` endpoint, which round-trips through this module.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from cegm_broker._paths import config_path, ensure_dir

DEFAULT_PORT: int = 27077
DEFAULT_LLM_BASE_URL: str = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL: str = "deepseek-chat"


class LLMConfig(BaseModel):
    """LLM endpoint configuration — OpenAI-compatible.

    Default targets DeepSeek (chosen by the project owner). Any
    OpenAI-compatible endpoint works (Ollama, OpenRouter, vLLM, LM Studio, …)
    — set ``base_url`` and ``model`` accordingly. ``api_key`` is stored as a
    :class:`SecretStr` to keep it out of accidental ``repr`` output.
    """

    model_config = ConfigDict(extra="forbid")

    base_url: str = DEFAULT_LLM_BASE_URL
    api_key: SecretStr = SecretStr("")
    model: str = DEFAULT_LLM_MODEL
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=1, le=131072)


class SafetyConfig(BaseModel):
    """Safety / observability defaults.

    ``preview_writes_default`` toggles routing every proxied ``memory_write``
    through :func:`cegm.preview_write` instead of applying immediately. Off
    by default in v0.1 to match user expectations of "AI just does it"; users
    who want a tighter loop tick it on.
    """

    model_config = ConfigDict(extra="forbid")

    preview_writes_default: bool = False
    confirm_lua_exec: bool = True
    snapshot_on_first_write: bool = True


class UIConfig(BaseModel):
    """In-CE UX toggles read by ``plugin/cegm.lua`` at autorun time.

    These are server-side because the dashboard is the single source of
    truth for user preferences — the Lua plugin reads
    ``%LOCALAPPDATA%\\CEGM\\config.json`` on each CE start.
    """

    model_config = ConfigDict(extra="forbid")

    show_status_form: bool = False
    """If True, a small floating "CEGM 0.1.0a1" status form opens on CE
    startup with the broker URL and an "Open Dashboard" button. Off by
    default — the C plugin's main-menu entry "Open CEGM Dashboard" plus
    the broker auto-spawn give the same UX without a stray window. Flip
    on in the dashboard's Settings drawer if you prefer the popup."""


class ServerConfig(BaseModel):
    """Listen-port and bind-host configuration.

    The bind host is intentionally not user-configurable from the dashboard
    — broadening past ``127.0.0.1`` would change the security model. To
    expose the broker remotely a user must edit ``config.json`` directly.
    """

    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)


class Config(BaseModel):
    """Top-level config persisted to disk."""

    model_config = ConfigDict(extra="forbid")

    server: ServerConfig = Field(default_factory=ServerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @classmethod
    def load(cls) -> Self:
        """Load config from disk, returning defaults if the file is missing
        or corrupted."""
        path = config_path()
        if not path.exists():
            return cls()
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logging.getLogger("cegm_broker.config").warning(
                "config.load_failed",
                extra={"path": str(path), "err": repr(exc)},
            )
            return cls()
        return cls.model_validate(raw)

    def save(self) -> None:
        """Persist config to disk atomically (write-then-rename).

        Pydantic's default JSON serialization masks ``SecretStr`` to ``"**********"``,
        which would lose the user's LLM key on every save. We dump in
        ``python`` mode and explicitly unwrap the secret before writing.
        The on-disk file therefore holds the key in plaintext; the Windows
        ACL on ``%LOCALAPPDATA%`` is the security boundary.
        """
        path = config_path()
        ensure_dir(path.parent)
        tmp = path.with_suffix(".json.tmp")
        payload: dict[str, Any] = self.model_dump(mode="python")
        # Unwrap ``SecretStr`` instances so ``json.dumps`` produces real values.
        if isinstance(payload.get("llm"), dict):
            payload["llm"]["api_key"] = self.llm.api_key.get_secret_value()
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
            fh.write("\n")
        tmp.replace(path)

    def sanitized(self) -> dict[str, Any]:
        """Return a config representation safe to expose via ``/api/config``.

        Strips the LLM API key. Useful for the dashboard's settings drawer
        and for the ``cegm://config`` MCP resource.
        """
        data: dict[str, Any] = self.model_dump(mode="json")
        if "llm" in data and isinstance(data["llm"], dict):
            data["llm"]["api_key"] = "***" if self.llm.api_key.get_secret_value() else ""
        return data
