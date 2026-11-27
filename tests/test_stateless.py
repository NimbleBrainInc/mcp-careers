"""Any replica serves any request: no MCP session ties a client to one pod."""

import json
from contextlib import AsyncExitStack

import httpx2

from mcp_careers.server import build_app

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


async def _pod(stack: AsyncExitStack) -> httpx2.AsyncClient:
    """One replica: its own app instance, started, sharing nothing in memory with another."""
    app = build_app()
    await stack.enter_async_context(app.router.lifespan_context(app))
    return await stack.enter_async_context(
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1")
    )


async def test_a_follow_up_on_another_pod_is_served() -> None:
    async with AsyncExitStack() as stack:
        first, second = await _pod(stack), await _pod(stack)
        opened = await first.post("/mcp", headers=HEADERS, json=INITIALIZE)
        assert opened.status_code == 200
        followup = {**HEADERS, "mcp-protocol-version": "2025-11-25"}
        # A client echoes a session id if one was issued; a stateless server issues none,
        # and must serve the follow-up either way.
        if session := opened.headers.get("mcp-session-id"):
            followup["mcp-session-id"] = session
        listed = await second.post(
            "/mcp",
            headers=followup,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
    assert listed.status_code == 200, listed.text
    names = {t["name"] for t in json.loads(listed.text)["result"]["tools"]}
    assert names == {"careers_list_roles", "careers_submit_application"}
