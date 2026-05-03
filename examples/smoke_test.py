"""Tiny smoke-test client for a running CEGM broker.

Run this without any external client to verify the broker stack is alive:

    python examples/smoke_test.py

Hits /api/health, lists MCP tools via the proxy, and prints a summary.
"""

from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = "http://127.0.0.1:27077"


def get_json(url: str) -> dict[str, object]:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=5) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def post_jsonrpc(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def main(base: str = DEFAULT_BASE) -> int:
    try:
        health = get_json(f"{base}/api/health")
    except URLError as exc:
        print(f"broker unreachable at {base}: {exc.reason}", file=sys.stderr)
        return 1

    print(f"broker  : v{health.get('version')} on port {health.get('port')}")
    proxy = health.get("proxy", {})
    print(f"proxy   : available={proxy.get('available')}  tools={proxy.get('tool_count')}")
    if proxy.get("error"):
        print(f"          (last error: {proxy['error']})")

    rpc = post_jsonrpc(
        f"{base}/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    tools = rpc.get("result", {}).get("tools", [])
    print(f"tools   : {len(tools)} exposed via /mcp")
    for t in tools[:5]:
        print(f"          - {t.get('name')}")
    if len(tools) > 5:
        print(f"          … +{len(tools) - 5} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE))
