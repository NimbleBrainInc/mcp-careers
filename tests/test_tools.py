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
async def test_the_skill_is_served(mode: Mode) -> None:
    assert set(await served_skills(mcp, mode)) == {"skill://apply-to-nimblebrain/SKILL.md"}


@pytest.mark.parametrize("mode", MODES)
async def test_every_tool_says_what_it_can_change(mode: Mode) -> None:
    async with Client(mcp, mode=mode) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert set(tools) == {"careers_list_roles", "careers_submit_application"}
    for tool in tools.values():
        assert tool.title, tool.name
        assert tool.output_schema, tool.name
        assert tool.annotations.open_world_hint is False, tool.name
    roles = tools["careers_list_roles"].annotations
    assert roles.read_only_hint is True and roles.idempotent_hint is True
    submit = tools["careers_submit_application"].annotations
    assert submit.read_only_hint is False and submit.destructive_hint is False
    assert submit.idempotent_hint is False


@pytest.mark.parametrize("mode", MODES)
async def test_every_parameter_is_described(mode: Mode) -> None:
    async with Client(mcp, mode=mode) as client:
        for tool in await client.list_tools():
            for name, prop in tool.input_schema.get("properties", {}).items():
                assert prop.get("description"), f"{tool.name}.{name}"


@pytest.mark.parametrize("mode", MODES)
async def test_list_roles_names_the_open_roles(mode: Mode) -> None:
    data = (await call(mode, "careers_list_roles", {})).structured_content
    assert [r["id"] for r in data["roles"]] == ["test-agent-engineer"]
    assert "careers_submit_application" in data["how_to_apply"]


async def test_the_test_role_never_shows_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "settings", replace(config.settings, env="production"))
    result = await call("auto", "careers_list_roles", {})
    assert result.structured_content["roles"] == []


@pytest.mark.parametrize("mode", MODES)
async def test_a_good_application_returns_a_confirm_link_and_posts_nothing(
    mode: Mode, calls
) -> None:
    result = await call(mode, "careers_submit_application", good_args())
    assert not result.is_error
    data = result.structured_content
    assert data["status"] == "awaiting_confirmation"
    assert data["confirm_url"].startswith("https://careers.test/confirm/")
    assert calls.posts == []


async def test_link_and_note_are_optional() -> None:
    args = good_args()
    del args["link"], args["note"]
    assert not (await call("auto", "careers_submit_application", args)).is_error


@pytest.mark.parametrize("mode", MODES)
async def test_every_problem_is_listed_at_once(mode: Mode) -> None:
    result = await call(
        mode,
        "careers_submit_application",
        good_args(email="nope", resume_url="http://x.test/cv", note="word " * 301),
    )
    assert result.is_error
    error = result.structured_content["error"]
    assert error["code"] == "bad_input"
    for field in ("`email`", "`resume_url`", "`note`"):
        assert field in error["message"]


async def test_an_unknown_role_is_bad_input() -> None:
    result = await call("auto", "careers_submit_application", good_args(role="ceo"))
    assert result.structured_content["error"]["code"] == "bad_input"


async def test_an_email_that_already_applied_is_a_conflict(store) -> None:
    await store.reserve("ada@example.com", daily_cap=10)
    result = await call("auto", "careers_submit_application", good_args(email="ADA@example.com"))
    assert result.structured_content["error"]["code"] == "conflict"


async def test_a_full_day_is_rate_limited(store) -> None:
    for i in range(10):
        await store.reserve(f"p{i}@example.com", daily_cap=10)
    error = (await call("auto", "careers_submit_application", good_args())).structured_content[
        "error"
    ]
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
    error = (await call("auto", "careers_submit_application", good_args())).structured_content[
        "error"
    ]
    assert error["code"] == "internal"
    assert "careers@nimblebrain.ai" in error["message"]


async def test_every_error_message_starts_with_its_code(store) -> None:
    """The skill keys its error table by code, and some clients show only the text."""
    await store.reserve("taken@example.com", daily_cap=10)
    cases = [good_args(email="nope"), good_args(email="taken@example.com")]
    for args in cases:
        error = (await call("auto", "careers_submit_application", args)).structured_content["error"]
        assert error["message"].startswith(f"{error['code']}: "), error
