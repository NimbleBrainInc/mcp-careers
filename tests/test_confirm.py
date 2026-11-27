"""The confirmation page: the only way an application reaches Slack."""

import httpx2
import pytest
from fastmcp import Client

from mcp_careers.server import mcp
from tests.conftest import good_args


async def submit(**overrides: str) -> str:
    async with Client(mcp) as client:
        result = await client.call_tool("careers_submit_application", good_args(**overrides))
    return result.structured_content["confirm_url"].removeprefix("https://careers.test")


@pytest.fixture
async def http():
    transport = httpx2.ASGITransport(app=mcp.http_app())
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client


def form(answer: str = "token-from-widget") -> dict:
    return {
        "content": f"cf-turnstile-response={answer}",
        "headers": {"content-type": "application/x-www-form-urlencoded"},
    }


async def test_the_page_shows_what_is_being_sent(http) -> None:
    path = await submit()
    page = await http.get(path)
    assert page.status_code == 200
    assert "Ada Lovelace" in page.text and "cf-turnstile" in page.text
    assert page.headers["cache-control"] == "no-store"


async def test_confirming_posts_once_and_retires_the_link(http, calls) -> None:
    path = await submit()
    done = await http.post(path, **form())
    assert done.status_code == 200 and "with the NimbleBrain team" in done.text
    assert len(calls.posts) == 1
    again = await http.post(path, **form())
    assert again.status_code == 404
    assert len(calls.posts) == 1


async def test_a_failed_turnstile_posts_nothing_and_keeps_the_link(http, calls) -> None:
    path = await submit()
    calls.turnstile_passes = False
    refused = await http.post(path, **form())
    assert refused.status_code == 400 and calls.posts == []
    calls.turnstile_passes = True
    assert (await http.post(path, **form())).status_code == 200
    assert len(calls.posts) == 1


async def test_a_missing_turnstile_answer_is_refused(http, calls) -> None:
    path = await submit()
    assert (await http.post(path, **form(""))).status_code == 400
    assert calls.posts == []


async def test_a_slack_failure_can_be_retried(http, calls, store) -> None:
    path = await submit()
    calls.slack_fails = True
    assert (await http.post(path, **form())).status_code == 502
    assert not await store.email_has_applied("ada@example.com")
    calls.slack_fails = False
    assert (await http.post(path, **form())).status_code == 200
    assert len(calls.posts) == 1


async def test_two_links_for_one_email_post_once(http, calls) -> None:
    first, second = await submit(), await submit()
    assert (await http.post(first, **form())).status_code == 200
    assert (await http.post(second, **form())).status_code == 409
    assert len(calls.posts) == 1


async def test_an_unknown_link_is_not_found(http) -> None:
    assert (await http.get("/confirm/nope")).status_code == 404
    assert (await http.post("/confirm/nope", **form())).status_code == 404


async def test_applicant_text_cannot_ping_the_channel(http, calls) -> None:
    path = await submit(name="<!channel> Ada", note="<!here> " + good_args()["note"])
    await http.post(path, **form())
    posted = str(calls.posts[0])
    assert "<!channel>" not in posted and "<!here>" not in posted
    assert "&lt;!channel&gt;" in posted
