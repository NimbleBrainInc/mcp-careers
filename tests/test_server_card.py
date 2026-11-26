"""The Server Card a host reads before it connects, and the files that restate it.

pyproject.toml holds the version; the card and serverInfo derive it from the installed
package; server.json restates the card. The release refuses a tag that disagrees with
server.json, so these must agree on every commit.
"""

import json
import tomllib
from pathlib import Path

import httpx2
from nimblebrain_server_sdk import SERVER_CARD_MEDIA_TYPE

from mcp_careers.server import mcp

ROOT = Path(__file__).parent.parent


async def served_card() -> dict:
    transport = httpx2.ASGITransport(app=mcp.http_app())
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        response = await http.get("/mcp/server-card", headers={"accept": SERVER_CARD_MEDIA_TYPE})
    assert response.status_code == 200
    return response.json()


async def test_the_card_reports_the_pyproject_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert (await served_card())["version"] == pyproject["project"]["version"]


async def test_server_json_agrees_with_the_card() -> None:
    card = await served_card()
    server_json = json.loads((ROOT / "server.json").read_text())
    for field in ("name", "version", "title", "description", "websiteUrl"):
        assert server_json[field] == card[field], field
