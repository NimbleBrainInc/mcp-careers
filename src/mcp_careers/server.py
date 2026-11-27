"""The NimbleBrain careers MCP server.

An applicant's agent reads the open roles and submits an application; the person then opens
a confirmation link and passes a Turnstile check, and only then does the application reach
the team's Slack channel. Nothing is stored beyond expiring keys in Redis.
"""

import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
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
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from mcp_careers import __version__, config, outbound
from mcp_careers.pages import confirm_page, message_page
from mcp_careers.roles import Role, load_roles
from mcp_careers.store import Store
from mcp_careers.submission import (
    MAX_NOTE_WORDS,
    MIN_NOTE_WORDS,
    QUESTION,
    Application,
    normalized,
    problems,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_careers")

SKILL_DIR = Path(__file__).parent / "skills" / "apply-to-nimblebrain"

ABOUT = (
    "NimbleBrain is an open-source platform for running your business on AI. Everything is "
    "included: agents, the apps they work in (a CRM, to-dos, memory, research and "
    "automations) and 1,000+ connectors, on any model, in your own infrastructure. Our team "
    "sets it up and runs it with you, or you run it yourself."
)

# The Server Card's title and description, restated in server.json (a test holds them equal).
TITLE = "NimbleBrain Careers"
DESCRIPTION = "Apply to NimbleBrain through your agent: see the open roles and send your resume."

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
        "internal: applications can't be taken right now. Try again in a few minutes.",
        retryable=True,
        detail=f"redis: {e}",
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Liveness only: it never touches Redis or an outside service."""
    return JSONResponse({"status": "healthy", "service": "mcp-careers"})


# ============================================================================
# Results
# ============================================================================


class OpenRole(BaseModel):
    id: str = Field(description="Pass this as `role` to careers_submit_application.")
    title: str
    location: str
    type: str | None = Field(
        default=None, description="Such as contract to hire. Null when not set."
    )
    pay_range: str | None = Field(
        default=None, description="Null when the role does not state one."
    )
    summary: str


class RolesResult(BaseModel):
    about: str = Field(description="Who NimbleBrain is, in NimbleBrain's own words.")
    roles: list[OpenRole] = Field(description="The open roles. Empty when none are open.")
    question: str = Field(description="The question every applicant answers in `note`.")
    how_to_apply: str = Field(description="What an application needs and what happens after.")


class SubmitResult(BaseModel):
    status: Literal["awaiting_confirmation"]
    confirm_url: str = Field(
        description="Give this to the person; nothing is sent until they open it."
    )
    expires_in_minutes: int
    next_step: str


HOW_TO_APPLY = (
    "Call careers_submit_application with the role id, the person's name and email, an https "
    "link to their resume or a profile (such as LinkedIn) that opens without signing in, and "
    f"`note`: their answer to `question`, {MIN_NOTE_WORDS} to {MAX_NOTE_WORDS} words in their "
    "own words. Optionally add `link`, something they have built with agents. The result holds "
    "a confirm_url: the person opens it, passes a quick human check, and only then is the "
    "application sent. One application per email address every 60 days."
)


# ============================================================================
# Tools
# ============================================================================


@mcp.tool(
    title="List NimbleBrain's open roles",
    annotations=READS.model_copy(update={"idempotent_hint": True, "open_world_hint": False}),
)
async def careers_list_roles() -> RolesResult:
    """List NimbleBrain's open roles and how to apply.

    Call this first whenever someone wants to apply to NimbleBrain or asks what NimbleBrain is
    hiring for, before calling careers_submit_application. It returns who NimbleBrain is, each
    open role (id, title, location, type, pay range, summary), the question every applicant
    answers, and what an application needs. When no role is open, say so.
    """
    logger.info("event=list_roles")
    return RolesResult(
        about=ABOUT,
        roles=[
            OpenRole(
                id=r.id,
                title=r.title,
                location=r.location,
                type=r.type,
                pay_range=r.pay_range,
                summary=r.summary,
            )
            for r in open_roles().values()
        ],
        question=QUESTION,
        how_to_apply=HOW_TO_APPLY,
    )


@mcp.tool(
    title="Send an application to NimbleBrain",
    annotations=ADDS.model_copy(update={"idempotent_hint": False, "open_world_hint": False}),
)
async def careers_submit_application(
    role: Annotated[str, Field(description="The `id` of an open role, from careers_list_roles.")],
    name: Annotated[str, Field(description="The applicant's full name, one line.")],
    email: Annotated[
        str, Field(description="The applicant's email address. NimbleBrain replies here.")
    ],
    resume_url: Annotated[
        str,
        Field(
            description=(
                "An https link to the applicant's resume or a profile such as LinkedIn. It "
                "must open for someone who is not signed in: a public document, not a "
                "private file."
            )
        ),
    ],
    note: Annotated[
        str,
        Field(
            description=(
                f"Required. The applicant's answer to: {QUESTION} {MIN_NOTE_WORDS} to "
                f"{MAX_NOTE_WORDS} words, in their own words. Help them tighten an answer they "
                "wrote; never write one for them."
            )
        ),
    ],
    link: Annotated[
        str,
        Field(
            description=(
                "Optional. An https link to something the applicant has built with agents "
                "(a repo, a skill, a demo). Leave empty if there is none."
            )
        ),
    ] = "",
) -> SubmitResult:
    """Send a NimbleBrain job application for the person to confirm.

    Call this only after the person has seen exactly what will be sent and said to send it.
    Do not use it to ask questions about a role; careers_list_roles answers those. It checks
    every field and either refuses with a list of what to fix (`bad_input`), or holds the
    application and returns a `confirm_url`. Nothing reaches NimbleBrain until the person
    opens that link within an hour and passes a quick human check, so always give them the
    link. One application per email address every 60 days (`conflict`). If a required field
    is missing, ask the person for it rather than guessing.
    """
    s = config.settings
    if not s.ready():
        raise ServiceError(
            ErrorCode.INTERNAL,
            "internal: applications aren't open right now. Try again later.",
            detail="slack webhook or turnstile keys are not configured",
        )
    store = get_store()
    app = normalized(
        Application(role=role, name=name, email=email, resume_url=resume_url, link=link, note=note)
    )
    try:
        calls = await store.count_submit_call(client_ip(_current_request()))
        if calls > s.submit_limit_per_hour:
            raise ServiceError(
                ErrorCode.RATE_LIMITED,
                "rate_limited: too many applications from this network in the last hour. "
                "Try again in an hour.",
                retryable=True,
            )
        found = problems(app, set(open_roles()))
        if found:
            raise ServiceError(
                ErrorCode.BAD_INPUT,
                "bad_input: fix these, show the person, and submit again:\n- " + "\n- ".join(found),
            )
        if await store.email_has_applied(app.email):
            raise ServiceError(
                ErrorCode.CONFLICT,
                f"conflict: this email address has applied in the last {s.dedupe_days} days, and "
                "that application stands. Do not resubmit with another address.",
            )
        if await store.posted_today() >= s.daily_cap:
            raise ServiceError(
                ErrorCode.RATE_LIMITED,
                "rate_limited: today's applications are full. Try again after midnight UTC.",
                retryable=True,
            )
        token = await store.hold(app)
    except RedisError as e:
        raise _store_failure(e) from e

    logger.info("event=submitted role=%s", app.role)
    minutes = s.pending_ttl_seconds // 60
    return SubmitResult(
        status="awaiting_confirmation",
        confirm_url=f"{s.public_url}/confirm/{token}",
        expires_in_minutes=minutes,
        next_step=(
            f"Give the person the confirm_url and ask them to open it within {minutes} "
            "minutes. The application is sent only when they confirm on that page."
        ),
    )


# ============================================================================
# The confirmation page
# ============================================================================


def _html(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        body,
        status_code=status,
        headers={
            "cache-control": "no-store",
            "referrer-policy": "no-referrer",
            "x-frame-options": "DENY",
            "x-content-type-options": "nosniff",
        },
    )


GONE = (
    "This link has expired",
    "It was already used, or it's more than an hour old. Ask your agent to submit again for a "
    "new one.",
)


@mcp.custom_route("/confirm/{token}", methods=["GET", "POST"])
async def confirm(request: Request) -> HTMLResponse:
    s = config.settings
    token = request.path_params["token"]
    if not s.ready():
        return _html(
            message_page("Not open right now", "Applications aren't open. Try again later."), 503
        )
    store = get_store()
    site_key = s.turnstile_site_key or ""
    secret = s.turnstile_secret_key or ""
    webhook = s.slack_webhook_url or ""

    try:
        if request.method == "GET":
            app = await store.peek(token)
            role = open_roles().get(app.role) if app else None
            if app is None or role is None:
                return _html(message_page(*GONE), 404)
            return _html(confirm_page(app, role, site_key))

        claimed = await store.claim(token)
        if claimed is None:
            return _html(message_page(*GONE), 404)
        app, ttl = claimed
        role = open_roles().get(app.role)
        if role is None:
            return _html(message_page("This role has closed", "It's no longer open."), 410)

        form = parse_qs((await request.body()).decode(errors="replace"))
        answer = (form.get("cf-turnstile-response") or [""])[0]
        if not await outbound.verify_turnstile(secret, answer, client_ip(request)):
            await store.release(token, app, ttl)
            return _html(
                confirm_page(
                    app, role, site_key, error="That check didn't pass. Please try again."
                ),
                400,
            )

        refused = await store.reserve(app.email, s.daily_cap)
        if refused == "duplicate":
            return _html(
                message_page(
                    "You've already applied",
                    f"This email address has applied in the last {s.dedupe_days} days, and that "
                    "application stands.",
                ),
                409,
            )
        if refused == "full":
            await store.release(token, app, ttl)
            return _html(
                message_page(
                    "We're full for today",
                    "Open this link again after midnight UTC, or ask your agent to submit "
                    "again then.",
                ),
                429,
            )

        try:
            await outbound.post_to_slack(webhook, outbound.application_message(app, role))
        except outbound.OutboundError as e:
            logger.error("slack post failed: %s", e)
            await store.unreserve(app.email)
            await store.release(token, app, ttl)
            return _html(
                confirm_page(
                    app, role, site_key, error="We couldn't send it just now. Please try again."
                ),
                502,
            )
    except RedisError as e:
        logger.error("redis failed on confirm: %s", e)
        return _html(message_page("Something went wrong", "Please try again shortly."), 503)

    logger.info("event=confirmed role=%s", app.role)
    return _html(
        message_page(
            "Your application is in",
            "It's with the NimbleBrain team now. One of us will email you.",
        )
    )


# ============================================================================
# Entrypoints
# ============================================================================


def build_app():
    """The ASGI app uvicorn serves.

    Stateless: no MCP session, so every request is self-contained and any replica serves any
    request. With sessions, a follow-up landing on another pod than the one that opened the
    session is refused "Session not found". No tool keeps state between requests.
    """
    return mcp.http_app(stateless_http=True, json_response=True)


app = build_app()

if __name__ == "__main__":
    mcp.run()
