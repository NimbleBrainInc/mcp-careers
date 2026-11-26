"""A golden record of what a host sees, on each protocol era.

The record holds the server's identity and instructions, every tool with its schemas and
annotations, the resources with their MIME types, the Server Card, and a digest of every
skill file. A difference fails the test and writes `<era>.actual.json` beside the record.
To accept an intended change, regenerate and review the diff in the PR:

    UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py
"""

import hashlib
import json
import os
from pathlib import Path

import httpx2
import pytest
from fastmcp import Client
from nimblebrain_server_sdk import SERVER_CARD_MEDIA_TYPE
from nimblebrain_server_sdk.testing import Mode

from mcp_careers.server import mcp

GOLDEN = Path(__file__).parent / "golden"


def _wire(model) -> dict:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


async def record(mode: Mode) -> dict:
    async with Client(mcp, mode=mode) as client:
        tools = sorted((_wire(t) for t in await client.list_tools()), key=lambda t: t["name"])
        resources = []
        for r in sorted(await client.list_resources(), key=lambda r: str(r.uri)):
            [content] = await client.read_resource(r.uri)
            text = getattr(content, "text", "")
            resources.append(
                {
                    "uri": str(r.uri),
                    "mimeType": r.mimeType,
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
            )
        templates = [_wire(t) for t in await client.list_resource_templates()]
        prompts = [_wire(p) for p in await client.list_prompts()]

    transport = httpx2.ASGITransport(app=mcp.http_app())
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        card = (
            await http.get("/mcp/server-card", headers={"accept": SERVER_CARD_MEDIA_TYPE})
        ).json()
    # The version moves on every release; test_server_card holds it to pyproject.
    card.pop("version", None)
    return {
        "instructions": mcp.instructions,
        "server_card": card,
        "tools": tools,
        "resources": resources,
        "resource_templates": templates,
        "prompts": prompts,
    }


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_the_surface_matches_the_golden_record(mode: Mode) -> None:
    path = GOLDEN / f"{mode}.json"
    actual = json.dumps(await record(mode), indent=2, sort_keys=True) + "\n"
    if os.getenv("UPDATE_GOLDEN") == "1":
        path.write_text(actual)
    expected = path.read_text() if path.exists() else ""
    if actual != expected:
        (GOLDEN / f"{mode}.actual.json").write_text(actual)
        pytest.fail(
            f"The surface differs from {path.name}; see {mode}.actual.json. If the change is "
            "intended: UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py"
        )
