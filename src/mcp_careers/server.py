"""The NimbleBrain careers MCP server.

An applicant's agent reads the challenge and submits an application; the person then opens
a confirmation link and passes a Turnstile check, and only then does the application reach
the team's Slack channel. Nothing is stored beyond expiring keys in Redis.
"""

import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from nimblebrain_server_sdk import (
    ADDS,
    READS,
    add_error_contract,
    add_server_card,
    add_skills,
)
from nimblebrain_server_sdk.errors import ErrorCode, ServiceError
from pydantic import Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from mcp_careers import __version__, config, outbound
from mcp_careers.pages import confirm_page, message_page
from mcp_careers.roles import Role, load_roles
from mcp_careers.store import Store
from mcp_careers.submission import Submission, normalized, problems

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_careers")

SKILLS_DIR = Path(__file__).parent / "skills"
SKILL_DIR = SKILLS_DIR / "apply-to-nimblebrain"
CHALLENGE = (SKILL_DIR / "challenge.md").read_text()

ABOUT = (
    "NimbleBrain is an open-source platform for running your business on AI. Everything is "
    "included: agents, the apps they work in (a CRM, to-dos, memory, research and "
    "automations) and 1,000+ connectors, on any model, in your own infrastructure. Our team "
    "sets it up and runs it with you, or you run it yourself."
)
FALLBACK = "Email careers@nimblebrain.ai with a resume and a link to your work."

# The Server Card's title and description, restated in server.json (a test holds them equal).
TITLE = "NimbleBrain Careers"
DESCRIPTION = "Apply to NimbleBrain through your agent: read the challenge and send your work."

mcp = FastMCP(
    "ai.nimblebrain/careers",
    version=__version__,
    website_url="https://nimblebrain.ai/careers",
    instructions=(
        "Helps a person apply for a job at NimbleBrain. Read the "
        "skill://apply-to-nimblebrain/SKILL.md resource before calling a tool."
    ),
)
add_error_contract(mcp)
add_skills(mcp, [SKILL_DIR])
add_server_card(mcp, title=TITLE, description=DESCRIPTION)


# ============================================================================
# State
# ============================================================================

_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        s = config.settings
        _store = Store(
            Redis.from_url(s.redis_url, decode_responses=True),
            pending_ttl=s.pending_ttl_seconds,
            dedupe_days=s.dedupe_days,
        )
    return _store


def set_store(store: Store | None) -> None:
    """Replace the store (tests use an in-memory Redis)."""
    global _store
    _store = store


@lru_cache(maxsize=4)
def _roles_for(env: str) -> dict[str, Role]:
    return load_roles(env)


def open_roles() -> dict[str, Role]:
    return _roles_for(config.settings.env)


def client_ip(request: Request | None) -> str:
    """The client IP, read `trusted_proxy_hops` entries from the right of X-Forwarded-For.

    The leftmost entries are client-supplied, so a forged header cannot mint a fresh
    rate-limit identity.
    """
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        hops = config.settings.trusted_proxy_hops
        if hops >= 1 and len(parts) >= hops:
            return parts[-hops]
    return (request.client.host if request.client else None) or "unknown"


def _current_request() -> Request | None:
    try:
        return get_http_request()
    except RuntimeError:
        return None


def _store_failure(e: RedisError) -> ServiceError:
    return ServiceError(
        ErrorCode.INTERNAL,
        f"Applications can't be taken right now. Try again in a few minutes, or {FALLBACK}",
        retryable=True,
        detail=f"redis: {e}",
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Liveness only: it never touches Redis or an outside service."""
    return JSONResponse({"status": "healthy", "service": "mcp-careers"})


# ============================================================================
# Tools
# ============================================================================


@mcp.tool(annotations=READS)
async def careers_get_challenge(
    role: Annotated[
        str | None,
        Field(
            description=(
                "A role `id` from a previous call, to confirm it is open. Omit it to get "
                "every open role."
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Get NimbleBrain's open roles, the hiring challenge, and what an application needs.

    Call this first whenever someone wants to apply to NimbleBrain or asks what NimbleBrain
    is hiring for, before helping them with the challenge or calling
    careers_submit_application. The result holds who NimbleBrain is, each open role (id,
    title, location, pay range, summary), the challenge brief in Markdown, and the fields and
    limits a submission must meet. An unknown `role` is refused with the list of open role ids.
    """
    roles = open_roles()
    if role is not None and role not in roles:
        listed = ", ".join(roles) or "none right now"
        raise ServiceError(
            ErrorCode.BAD_INPUT, f"`role` is not an open role. Open roles: {listed}."
        )
    shown = [roles[role]] if role else list(roles.values())
    logger.info("event=get_challenge role=%s", role or "-")
    return {
        "about": ABOUT,
        "roles": [r.public() for r in shown],
        "challenge": CHALLENGE,
        "submission": {
            "tool": "careers_submit_application",
            "fields": {
                "role": "an open role id",
                "name": "the person's name, one line",
                "email": "where we reply",
                "resume_url": "an https link to a resume, document or profile",
                "skill": "the whole SKILL.md, with name and description in its frontmatter",
                "note": "50 to 300 words, written by the person",
            },
            "after": "The result holds a confirm_url the person must open within an hour.",
        },
        "other_way_to_apply": FALLBACK,
    }


@mcp.tool(annotations=ADDS)
async def careers_submit_application(
    role: Annotated[
        str, Field(description="The `id` of an open role, from careers_get_challenge.")
    ],
    name: Annotated[str, Field(description="The applicant's name, one line.")],
    email: Annotated[
        str, Field(description="The applicant's email address; NimbleBrain replies here.")
    ],
    resume_url: Annotated[
        str,
        Field(
            description="An https link to the applicant's resume, a document, or a profile page."
        ),
    ],
    skill: Annotated[
        str,
        Field(
            description=(
                "The whole SKILL.md the applicant built, starting with YAML frontmatter that "
                "has `name` and `description`. At most 20,000 characters."
            )
        ),
    ],
    note: Annotated[
        str,
        Field(
            description=(
                "50 to 300 words written by the applicant, not the agent: what the agent got "
                "wrong while building the skill, how they caught it, and what they would change."
            )
        ),
    ],
) -> dict[str, Any]:
    """Send a NimbleBrain job application for the person to confirm.

    Call this only after the person has reviewed the finished skill and their own note and
    has said to send it. It checks every field and either refuses with a list of what to fix
    (`bad_input`), or holds the application and returns a `confirm_url`. Nothing reaches
    NimbleBrain until the person opens that link within an hour and confirms, so always give
    them the link. One application per email address every 60 days (`conflict`).
    """
    s = config.settings
    if not s.ready():
        raise ServiceError(
            ErrorCode.INTERNAL,
            f"Applications aren't open right now. {FALLBACK}",
            detail="slack webhook or turnstile keys are not configured",
        )
    store = get_store()
    sub = normalized(
        Submission(role=role, name=name, email=email, resume_url=resume_url, skill=skill, note=note)
    )
    try:
        calls = await store.count_submit_call(client_ip(_current_request()))
        if calls > s.submit_limit_per_hour:
            raise ServiceError(
                ErrorCode.RATE_LIMITED,
                "Too many submissions from this network in the last hour. Try again in an hour.",
                retryable=True,
            )
        found = problems(sub, set(open_roles()))
        if found:
            raise ServiceError(
                ErrorCode.BAD_INPUT,
                "Fix these, show the person, and submit again:\n- " + "\n- ".join(found),
            )
        if await store.email_has_applied(sub.email):
            raise ServiceError(
                ErrorCode.CONFLICT,
                f"This email address has applied in the last {s.dedupe_days} days.",
            )
        if await store.posted_today() >= s.daily_cap:
            raise ServiceError(
                ErrorCode.RATE_LIMITED,
                "Today's applications are full. Try again after midnight UTC.",
                retryable=True,
            )
        token = await store.hold(sub)
    except RedisError as e:
        raise _store_failure(e) from e

    logger.info("event=submitted role=%s", sub.role)
    minutes = s.pending_ttl_seconds // 60
    return {
        "status": "awaiting_confirmation",
        "confirm_url": f"{s.public_url}/confirm/{token}",
        "expires_in_minutes": minutes,
        "next_step": (
            f"Give the person the confirm_url and ask them to open it within {minutes} "
            "minutes. The application is sent only when they confirm on that page."
        ),
    }


# ============================================================================
# The confirmation page
# ============================================================================


def _html(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        body,
        status_code=status,
        headers={"cache-control": "no-store", "referrer-policy": "no-referrer"},
    )


GONE = (
    "Link expired",
    "This link has expired or was already used. Ask your agent to submit again for a new one.",
)


@mcp.custom_route("/confirm/{token}", methods=["GET", "POST"])
async def confirm(request: Request) -> HTMLResponse:
    s = config.settings
    token = request.path_params["token"]
    if not s.ready():
        return _html(message_page("Not open right now", FALLBACK), 503)
    store = get_store()
    site_key = s.turnstile_site_key or ""
    secret = s.turnstile_secret_key or ""
    webhook = s.slack_webhook_url or ""

    try:
        if request.method == "GET":
            sub = await store.peek(token)
            role = open_roles().get(sub.role) if sub else None
            if sub is None or role is None:
                return _html(message_page(*GONE), 404)
            return _html(confirm_page(sub, role, site_key))

        claimed = await store.claim(token)
        if claimed is None:
            return _html(message_page(*GONE), 404)
        sub, ttl = claimed
        role = open_roles().get(sub.role)
        if role is None:
            return _html(message_page("Role closed", "This role is no longer open."), 410)

        form = parse_qs((await request.body()).decode(errors="replace"))
        answer = (form.get("cf-turnstile-response") or [""])[0]
        if not await outbound.verify_turnstile(secret, answer, client_ip(request)):
            await store.release(token, sub, ttl)
            return _html(
                confirm_page(
                    sub, role, site_key, error="That check didn't pass. Please try again."
                ),
                400,
            )

        refused = await store.reserve(sub.email, s.daily_cap)
        if refused == "duplicate":
            return _html(
                message_page(
                    "Already applied",
                    f"This email address has applied in the last {s.dedupe_days} days.",
                ),
                409,
            )
        if refused == "full":
            await store.release(token, sub, ttl)
            return _html(
                message_page(
                    "Full for today",
                    "Today's applications are full. Open this link again after midnight UTC, "
                    "or ask your agent to submit again then.",
                ),
                429,
            )

        try:
            await outbound.post_to_slack(webhook, outbound.application_message(sub, role))
        except outbound.OutboundError as e:
            logger.error("slack post failed: %s", e)
            await store.unreserve(sub.email)
            await store.release(token, sub, ttl)
            return _html(
                confirm_page(
                    sub, role, site_key, error="We couldn't send it just now. Please try again."
                ),
                502,
            )
    except RedisError as e:
        logger.error("redis failed on confirm: %s", e)
        return _html(
            message_page("Something went wrong", f"Please try again shortly. {FALLBACK}"), 503
        )

    logger.info("event=confirmed role=%s", sub.role)
    return _html(
        message_page(
            "You're in",
            "Your application is with the NimbleBrain team. One of us will email you.",
        )
    )


# ============================================================================
# Entrypoints
# ============================================================================

app = mcp.http_app()

if __name__ == "__main__":
    mcp.run()
