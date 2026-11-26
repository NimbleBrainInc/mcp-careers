"""The two tools and the skill, over the wire, on both protocol eras."""

from dataclasses import replace

import pytest
from fastmcp import Client
from nimblebrain_server_sdk.testing import Mode, served_skills

from mcp_careers import config
from mcp_careers.server import mcp
from tests.conftest import good_args

MODES = ["auto", "legacy"]


async def call(mode: Mode, tool: str, args: dict):
    async with Client(mcp, mode=mode) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


@pytest.mark.parametrize("mode", MODES)
async def test_the_skill_and_its_brief_are_served(mode: Mode) -> None:
    assert set(await served_skills(mcp, mode)) == {"skill://apply-to-nimblebrain/SKILL.md"}
    async with Client(mcp, mode=mode) as client:
        brief = await client.read_resource("skill://apply-to-nimblebrain/challenge.md")
    assert "Build a skill" in brief[0].text


@pytest.mark.parametrize("mode", MODES)
async def test_every_tool_is_annotated(mode: Mode) -> None:
    async with Client(mcp, mode=mode) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert set(tools) == {"careers_get_challenge", "careers_submit_application"}
    assert tools["careers_get_challenge"].annotations.read_only_hint is True
    submit = tools["careers_submit_application"].annotations
    assert submit.read_only_hint is False and submit.destructive_hint is False


@pytest.mark.parametrize("mode", MODES)
async def test_get_challenge_lists_the_open_roles(mode: Mode) -> None:
    result = await call(mode, "careers_get_challenge", {})
    data = result.structured_content
    assert [r["id"] for r in data["roles"]] == ["test-agent-engineer"]
    assert "build a skill" in data["challenge"].lower()
    assert data["submission"]["tool"] == "careers_submit_application"


async def test_the_test_role_never_shows_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, env="production"))
    result = await call("auto", "careers_get_challenge", {})
    assert result.structured_content["roles"] == []


@pytest.mark.parametrize("mode", MODES)
async def test_an_unknown_role_is_bad_input(mode: Mode) -> None:
    result = await call(mode, "careers_get_challenge", {"role": "ceo"})
    assert result.is_error
    assert result.structured_content["error"]["code"] == "bad_input"


@pytest.mark.parametrize("mode", MODES)
async def test_a_good_submission_returns_a_confirm_link_and_posts_nothing(
    mode: Mode, calls
) -> None:
    result = await call(mode, "careers_submit_application", good_args())
    assert not result.is_error
    data = result.structured_content
    assert data["status"] == "awaiting_confirmation"
    assert data["confirm_url"].startswith("https://careers.test/confirm/")
    assert calls.posts == []


@pytest.mark.parametrize("mode", MODES)
async def test_every_problem_is_listed_at_once(mode: Mode) -> None:
    result = await call(
        mode,
        "careers_submit_application",
        good_args(email="nope", resume_url="http://x.test/cv", note="too short"),
    )
    assert result.is_error
    error = result.structured_content["error"]
    assert error["code"] == "bad_input"
    for field in ("`email`", "`resume_url`", "`note`"):
        assert field in error["message"]


async def test_an_email_that_already_applied_is_a_conflict(store) -> None:
    await store.reserve("ada@example.com", daily_cap=10)
    result = await call("auto", "careers_submit_application", good_args(email="ADA@example.com"))
    assert result.structured_content["error"]["code"] == "conflict"


async def test_a_full_day_is_rate_limited(store) -> None:
    for i in range(10):
        await store.reserve(f"p{i}@example.com", daily_cap=10)
    result = await call("auto", "careers_submit_application", good_args())
    error = result.structured_content["error"]
    assert error["code"] == "rate_limited" and error["retryable"] is True


async def test_too_many_calls_from_one_ip_are_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, submit_limit_per_hour=2))
    for _ in range(2):
        assert not (await call("auto", "careers_submit_application", good_args())).is_error
    result = await call("auto", "careers_submit_application", good_args())
    assert result.structured_content["error"]["code"] == "rate_limited"


async def test_not_configured_is_internal_and_points_to_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, slack_webhook_url=None))
    result = await call("auto", "careers_submit_application", good_args())
    error = result.structured_content["error"]
    assert error["code"] == "internal"
    assert "careers@nimblebrain.ai" in error["message"]
