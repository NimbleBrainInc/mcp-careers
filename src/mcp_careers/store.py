"""Everything the server keeps, in Redis, and all of it expiring.

careers:pending:<token>      a submission waiting to be confirmed   (pending TTL)
careers:email:<sha256>       an email that has posted               (dedupe window)
careers:day:<YYYY-MM-DD>     posted submissions that UTC day        (2 days)
careers:ip:<ip>:<hour>       submit calls from one IP that hour     (2 hours)
"""

import hashlib
import json
import secrets
from datetime import UTC, datetime

from redis.asyncio import Redis

from mcp_careers.submission import Submission

PREFIX = "careers"


def _email_key(email: str) -> str:
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    return f"{PREFIX}:email:{digest}"


def _day_key(now: datetime) -> str:
    return f"{PREFIX}:day:{now:%Y-%m-%d}"


class Store:
    def __init__(self, redis: Redis, *, pending_ttl: int, dedupe_days: int) -> None:
        self.redis = redis
        self.pending_ttl = pending_ttl
        self.dedupe_seconds = dedupe_days * 86_400

    # -- the submit tool's checks --------------------------------------------------

    async def count_submit_call(self, ip: str, now: datetime | None = None) -> int:
        """Count one submit call from `ip` this hour; returns the count including it."""
        now = now or datetime.now(UTC)
        key = f"{PREFIX}:ip:{ip}:{now:%Y%m%d%H}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 7_200)
        return int(count)

    async def email_has_applied(self, email: str) -> bool:
        return bool(await self.redis.exists(_email_key(email)))

    async def posted_today(self, now: datetime | None = None) -> int:
        value = await self.redis.get(_day_key(now or datetime.now(UTC)))
        return int(value or 0)

    # -- pending submissions ---------------------------------------------------------

    async def hold(self, sub: Submission) -> str:
        """Keep a submission until it is confirmed or expires; returns its token."""
        token = secrets.token_urlsafe(32)
        await self.redis.set(
            f"{PREFIX}:pending:{token}", json.dumps(sub.to_dict()), ex=self.pending_ttl
        )
        return token

    async def peek(self, token: str) -> Submission | None:
        raw = await self.redis.get(f"{PREFIX}:pending:{token}")
        return Submission(**json.loads(raw)) if raw else None

    async def claim(self, token: str) -> tuple[Submission, int] | None:
        """Take a pending submission so no second confirm can post it.

        Returns it with the seconds it had left, so `release` can put it back.
        """
        key = f"{PREFIX}:pending:{token}"
        ttl = await self.redis.ttl(key)
        raw = await self.redis.getdel(key)
        if not raw:
            return None
        return Submission(**json.loads(raw)), max(int(ttl), 60)

    async def release(self, token: str, sub: Submission, ttl: int) -> None:
        """Put a claimed submission back, so the person can try the same link again."""
        await self.redis.set(f"{PREFIX}:pending:{token}", json.dumps(sub.to_dict()), ex=ttl)

    # -- posting -------------------------------------------------------------------

    async def reserve(self, email: str, daily_cap: int, now: datetime | None = None) -> str | None:
        """Mark the email as applied and take a place in today's cap.

        Returns None on success, or `"duplicate"` or `"full"`; nothing is held on refusal.
        """
        email_key = _email_key(email)
        if not await self.redis.set(email_key, "1", nx=True, ex=self.dedupe_seconds):
            return "duplicate"
        day_key = _day_key(now or datetime.now(UTC))
        count = await self.redis.incr(day_key)
        if count == 1:
            await self.redis.expire(day_key, 172_800)
        if count > daily_cap:
            await self.redis.decr(day_key)
            await self.redis.delete(email_key)
            return "full"
        return None

    async def unreserve(self, email: str, now: datetime | None = None) -> None:
        """Undo `reserve` when the post itself failed."""
        await self.redis.decr(_day_key(now or datetime.now(UTC)))
        await self.redis.delete(_email_key(email))
