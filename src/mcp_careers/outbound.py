"""The two outside services the server calls: Cloudflare Turnstile and a Slack webhook."""

import logging
import re
from urllib.parse import urlsplit

import aiohttp

from mcp_careers.roles import Role
from mcp_careers.submission import QUESTION, Application

logger = logging.getLogger("mcp_careers.outbound")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT = aiohttp.ClientTimeout(total=10)
# Slack refuses a section whose text is over 3,000 characters. The trim notice fits in the rest.
SLACK_TEXT_LIMIT = 2_900
# Labels the applicant's answer in Slack with the question it answers.
APPLICANT_TEXT_NOTICE = f"Their answer to: {QUESTION}"


class OutboundError(Exception):
    """A call to Turnstile or Slack failed; the message is for logs only."""


async def verify_turnstile(secret: str, response: str, remote_ip: str | None) -> bool:
    """Whether Cloudflare accepts the widget's response. Fails closed on any error."""
    if not response:
        return False
    form = {"secret": secret, "response": response}
    if remote_ip and remote_ip != "unknown":
        form["remoteip"] = remote_ip
    try:
        async with (
            aiohttp.ClientSession(timeout=TIMEOUT) as http,
            http.post(SITEVERIFY_URL, data=form) as resp,
        ):
            body = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        logger.warning("turnstile siteverify failed: %s", e)
        return False
    if not body.get("success"):
        logger.info("turnstile refused: %s", body.get("error-codes"))
        return False
    return True


async def post_to_slack(webhook_url: str, payload: dict) -> None:
    try:
        async with (
            aiohttp.ClientSession(timeout=TIMEOUT) as http,
            http.post(webhook_url, json=payload) as resp,
        ):
            if resp.status != 200:
                raise OutboundError(f"slack webhook answered {resp.status}")
    except (aiohttp.ClientError, TimeoutError) as e:
        raise OutboundError(f"slack webhook failed: {e}") from e


def slack_escape(text: str) -> str:
    """Escape the three characters Slack's mrkdwn treats as control characters.

    Escaping `<` stops `<!channel>`, `<@U123>` and forged links from reaching the channel.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _quote(text: str) -> str:
    """Applicant text as a Slack quote: escaped, every line quoted, trimmed to fit.

    Escaping turns the applicant's own `>` into `&gt;`, so only the quote markers added here
    are live: the text cannot end the quote, ping anyone, or forge a link. The limit applies
    to the quoted text, since escaping and the quote markers both add characters.
    """
    body = slack_escape(text)
    quoted = "\n".join(f">{line}" if line else ">" for line in body.splitlines())
    if len(quoted) <= SLACK_TEXT_LIMIT:
        return quoted
    # Every applicant `&` is escaped, so a trailing `&` with no `;` is a cut entity.
    cut = re.sub(r"&[a-z]*$", "", quoted[:SLACK_TEXT_LIMIT])
    return cut + f"… (trimmed; {len(text):,} characters in all)"


def _label(url: str, limit: int = 48) -> str:
    """Where a link goes, as its text: `linkedin.com/in/someone`, not `open`."""
    parts = urlsplit(url)
    shown = (parts.netloc.removeprefix("www.") + parts.path).rstrip("/")
    return slack_escape(shown if len(shown) <= limit else shown[: limit - 1] + "…")


def _link(url: str) -> str:
    # Checked URLs hold no `|`, `<`, `>`, quotes or spaces (submission.py), so they cannot
    # break out of Slack's `<url|text>` form.
    return f"<{slack_escape(url)}|{_label(url)}>"


def application_message(app: Application, role: Role) -> dict:
    """The Slack message for one confirmed application."""
    name = slack_escape(app.name)
    title = slack_escape(role.title)
    email = slack_escape(app.email)
    lines = [
        f":inbox_tray: *{name}* applied for *{title}*",
        f"•  Email: <mailto:{email}|{email}>",
        f"•  Resume: {_link(app.resume_url)}",
    ]
    if app.link:
        lines.append(f"•  Built with agents: {_link(app.link)}")
    blocks: list[dict] = [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]
    if app.note:
        blocks += [
            {"type": "context", "elements": [{"type": "mrkdwn", "text": APPLICANT_TEXT_NOTICE}]},
            {"type": "section", "text": {"type": "mrkdwn", "text": _quote(app.note)}},
        ]
    return {"text": f"{name} applied for {title}", "blocks": blocks}
