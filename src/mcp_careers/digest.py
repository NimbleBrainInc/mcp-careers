"""Last week's funnel, posted to the careers Slack channel every Monday.

The server counts each funnel step per ISO week in Redis (`Store.count_event`). Every hour
each replica asks whether last week's digest is due; once it is (Monday 19:00 UTC, which is
09:00 in Hawaii), the first replica to claim the week posts it and the rest find it claimed.
A failed post gives the claim back, so the next hour tries again.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from mcp_careers.store import Store, week_label

logger = logging.getLogger("mcp_careers.digest")

DUE_WEEKDAY = 0  # Monday
DUE_HOUR_UTC = 19
CHECK_EVERY_SECONDS = 3600

Poster = Callable[[str, dict], Awaitable[None]]


def due_week(now: datetime) -> str | None:
    """The week whose digest is due at `now`: last week, once this week's post time passed."""
    start_of_week = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    due_at = start_of_week + timedelta(days=DUE_WEEKDAY, hours=DUE_HOUR_UTC)
    if now < due_at:
        return None
    return week_label(start_of_week - timedelta(days=1))


def digest_message(week: str, counts: dict[str, int]) -> dict:
    """The Slack payload: one line per funnel step, in order."""
    read, submitted, confirmed = counts["list_roles"], counts["submitted"], counts["confirmed"]
    return {
        "text": (
            f":bar_chart: *Careers, week {week}*\n"
            f"•  Agents read the open roles: *{read}*\n"
            f"•  Applications sent for confirmation: *{submitted}*\n"
            f"•  Confirmed and posted here: *{confirmed}*"
        )
    }


async def post_if_due(store: Store, webhook_url: str, post: Poster, now: datetime) -> bool:
    """Post last week's digest if it is due and no replica has; returns whether this one did."""
    week = due_week(now)
    if week is None or not await store.claim_digest(week):
        return False
    try:
        await post(webhook_url, digest_message(week, await store.week_counts(week)))
    except Exception:
        await store.release_digest(week)
        raise
    logger.info("event=digest_posted week=%s", week)
    return True


async def run(store_of: Callable[[], Store], webhook_url: str, post: Poster) -> None:
    """Check hourly, forever. A failed check is logged and retried next hour."""
    while True:
        await asyncio.sleep(CHECK_EVERY_SECONDS)
        try:
            await post_if_due(store_of(), webhook_url, post, datetime.now(UTC))
        # Any failure, not only Redis or Slack: one bad hour must not end the loop.
        except Exception as e:
            logger.error("weekly digest failed: %s", e)
