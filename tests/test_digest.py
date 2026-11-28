"""The weekly funnel digest: counting, when it is due, and posting it exactly once."""

from datetime import UTC, datetime

import fakeredis
import pytest

from mcp_careers import digest
from mcp_careers.store import Store, week_label

# Week 2026-W48 runs Monday 23 November to Sunday 29 November.
IN_W48 = datetime(2026, 11, 25, 12, tzinfo=UTC)
MONDAY_W49_BEFORE = datetime(2026, 11, 30, 18, 59, tzinfo=UTC)
MONDAY_W49_DUE = datetime(2026, 11, 30, 19, 0, tzinfo=UTC)


@pytest.fixture
def store() -> Store:
    return Store(fakeredis.FakeAsyncRedis(), pending_ttl=3600, dedupe_days=60)


class Poster:
    def __init__(self, fails: bool = False) -> None:
        self.fails = fails
        self.posts: list[dict] = []

    async def __call__(self, url: str, payload: dict) -> None:
        if self.fails:
            raise RuntimeError("slack down")
        self.posts.append(payload)


def test_week_label_is_the_iso_week() -> None:
    assert week_label(IN_W48) == "2026-W48"
    assert week_label(datetime(2027, 1, 1, tzinfo=UTC)) == "2026-W53"


def test_last_week_is_due_from_monday_19_utc() -> None:
    assert digest.due_week(MONDAY_W49_BEFORE) is None
    assert digest.due_week(MONDAY_W49_DUE) == "2026-W48"
    assert digest.due_week(datetime(2026, 12, 3, tzinfo=UTC)) == "2026-W48"


async def test_counts_are_kept_per_week(store: Store) -> None:
    for event in ("list_roles", "list_roles", "list_roles", "submitted", "submitted", "confirmed"):
        await store.count_event(event, IN_W48)
    await store.count_event("list_roles", MONDAY_W49_DUE)
    assert await store.week_counts("2026-W48") == {"list_roles": 3, "submitted": 2, "confirmed": 1}
    assert await store.week_counts("2026-W49") == {"list_roles": 1, "submitted": 0, "confirmed": 0}


async def test_posts_last_weeks_counts_once(store: Store) -> None:
    await store.count_event("list_roles", IN_W48)
    await store.count_event("confirmed", IN_W48)
    post = Poster()
    assert await digest.post_if_due(store, "https://hook", post, MONDAY_W49_DUE)
    # A second replica, or the next hour, finds the week claimed.
    assert not await digest.post_if_due(store, "https://hook", post, MONDAY_W49_DUE)
    assert len(post.posts) == 1
    text = post.posts[0]["text"]
    assert "week 2026-W48" in text
    assert "Agents read the open roles: *1*" in text
    assert "Applications sent for confirmation: *0*" in text
    assert "Confirmed and posted here: *1*" in text


async def test_nothing_posts_before_it_is_due(store: Store) -> None:
    post = Poster()
    assert not await digest.post_if_due(store, "https://hook", post, MONDAY_W49_BEFORE)
    assert post.posts == []


async def test_a_failed_post_gives_the_week_back(store: Store) -> None:
    with pytest.raises(RuntimeError):
        await digest.post_if_due(store, "https://hook", Poster(fails=True), MONDAY_W49_DUE)
    retry = Poster()
    assert await digest.post_if_due(store, "https://hook", retry, MONDAY_W49_DUE)
    assert len(retry.posts) == 1
