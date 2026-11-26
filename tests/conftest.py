"""Shared fixtures: an in-memory Redis, ready settings, and recorded outbound calls."""

from dataclasses import replace

import fakeredis
import pytest

from mcp_careers import config, outbound, server
from mcp_careers.store import Store

NOTE = (
    "My agent kept writing a description that said what the skill was about but never when "
    "to use it, so it never loaded on the requests it was built for. I caught it by asking a "
    "fresh session three real questions and watching it ignore the skill each time. I "
    "rewrote the description around the trigger phrases people actually use. With another "
    "day I would add a failure table for when the upstream system is down."
)
SKILL = (
    "---\n"
    "name: weekly-close\n"
    "description: How to run the weekly books close. Use when someone asks to close the week.\n"
    "---\n\n"
    "# Weekly close\n\n1. Pull the ledger.\n2. Reconcile.\n"
)


def good_args(**overrides: str) -> dict[str, str]:
    args = {
        "role": "test-agent-engineer",
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "resume_url": "https://example.com/ada.pdf",
        "skill": SKILL,
        "note": NOTE,
    }
    args.update(overrides)
    return args


class Outbound:
    """Records what would have gone to Turnstile and Slack."""

    def __init__(self) -> None:
        self.turnstile_passes = True
        self.slack_fails = False
        self.posts: list[dict] = []

    async def verify_turnstile(self, secret: str, response: str, remote_ip: str | None) -> bool:
        return self.turnstile_passes and bool(response)

    async def post_to_slack(self, webhook_url: str, payload: dict) -> None:
        if self.slack_fails:
            raise outbound.OutboundError("slack down")
        self.posts.append(payload)


@pytest.fixture(autouse=True)
def ready_settings(monkeypatch: pytest.MonkeyPatch):
    settings = replace(
        config.settings,
        env="development",
        public_url="https://careers.test",
        slack_webhook_url="https://hooks.slack.test/x",
        turnstile_site_key="site-key",
        turnstile_secret_key="secret-key",
        daily_cap=10,
        submit_limit_per_hour=10,
    )
    monkeypatch.setattr(config, "settings", settings)
    return settings


@pytest.fixture(autouse=True)
def store():
    s = Store(fakeredis.FakeAsyncRedis(decode_responses=True), pending_ttl=3600, dedupe_days=60)
    server.set_store(s)
    yield s
    server.set_store(None)


@pytest.fixture(autouse=True)
def calls(monkeypatch: pytest.MonkeyPatch) -> Outbound:
    rec = Outbound()
    monkeypatch.setattr(outbound, "verify_turnstile", rec.verify_turnstile)
    monkeypatch.setattr(outbound, "post_to_slack", rec.post_to_slack)
    return rec
