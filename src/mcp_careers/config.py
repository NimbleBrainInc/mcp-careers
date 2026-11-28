"""Settings, read from the environment once at import."""

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    # The deployment's careers config (about, question, roles; see examples/careers.yaml):
    # the YAML itself, or a path to it. The YAML wins when both are set.
    careers_config: str | None = os.getenv("CAREERS_CONFIG") or None
    careers_config_file: str | None = os.getenv("CAREERS_CONFIG_FILE") or None
    # The origin the confirmation link is built on, with no trailing slash.
    public_url: str = os.getenv("CAREERS_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    slack_webhook_url: str | None = os.getenv("SLACK_WEBHOOK_URL") or None
    turnstile_site_key: str | None = os.getenv("TURNSTILE_SITE_KEY") or None
    turnstile_secret_key: str | None = os.getenv("TURNSTILE_SECRET_KEY") or None

    # A submission waits this long for the person to confirm it.
    pending_ttl_seconds: int = _int("CAREERS_PENDING_TTL_SECONDS", 3600)
    # One posted submission per email address in this window.
    dedupe_days: int = _int("CAREERS_DEDUPE_DAYS", 60)
    # Posted submissions per UTC day, across everyone.
    daily_cap: int = _int("CAREERS_DAILY_CAP", 10)
    # Submit calls per client IP per hour.
    submit_limit_per_hour: int = _int("CAREERS_SUBMIT_LIMIT_PER_HOUR", 10)
    # The client IP is read this many entries from the right of X-Forwarded-For: the entry
    # our outermost trusted proxy observed. The leftmost entries are client-supplied.
    trusted_proxy_hops: int = _int("CAREERS_TRUSTED_PROXY_HOPS", 1)
    # Post last week's funnel counts to the Slack webhook every Monday. "0" turns it off.
    weekly_digest: bool = os.getenv("CAREERS_WEEKLY_DIGEST", "1") != "0"

    def ready(self) -> bool:
        """Whether a submission can be confirmed and posted."""
        return bool(
            self.slack_webhook_url and self.turnstile_site_key and self.turnstile_secret_key
        )


settings = Settings()
