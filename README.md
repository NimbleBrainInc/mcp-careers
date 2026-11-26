# NimbleBrain Careers MCP server

Apply to NimbleBrain through your agent. Connect this server, ask your agent to help you
apply, and it walks you through the challenge: build a skill from your own work, and tell
us what your agent got wrong along the way.

```text
I want to apply to NimbleBrain. Add the MCP server at https://careers.nimblebrain.ai/mcp,
then use its apply-to-nimblebrain skill to walk me through it.
```

Prefer not to apply through an agent? Email careers@nimblebrain.ai with a resume and a
link to your work.

## Connect it

| Host | How |
|------|-----|
| Claude Code | `claude mcp add --transport http nimblebrain-careers https://careers.nimblebrain.ai/mcp` |
| claude.ai | Settings, Connectors, add a custom connector with the URL above |
| Any other MCP host | Add a remote (streamable HTTP) server with the URL above |

## How it works

| Tool | Kind | Does |
|------|------|------|
| `careers_get_challenge` | reads | Who we are, the open roles, the challenge, and what a submission needs. |
| `careers_submit_application` | adds | Checks an application and returns a confirmation link. |

The server also publishes one skill, `apply-to-nimblebrain`, that tells your agent how to
help you.

Nothing is sent when your agent calls the submit tool. You open the confirmation link,
check what's being sent, and pass a quick human check. Only then does your application
reach the NimbleBrain team. The link lasts an hour.

## What we keep

Your application goes to the team's Slack once you confirm it. Before that it sits for at
most an hour in a cache. Afterwards we keep a one-way hash of your email for 60 days, to
allow one application per person in that window. To have your application deleted, email
careers@nimblebrain.ai.

## Develop

```bash
uv sync
uv run ruff format --check . && uv run ruff check . && uv run ty check src && uv run pytest
redis-server --port 6379 --daemonize yes   # or: docker run --rm -d -p 6379:6379 redis:7-alpine
cp .env.example .env                        # then set SLACK_WEBHOOK_URL
set -a; . ./.env; set +a
uv run uvicorn mcp_careers.server:app --host 127.0.0.1 --port 8000   # http://127.0.0.1:8000/mcp
```

`.env.example` uses Cloudflare's published Turnstile test keys, which always pass.
Deploying: `deploy/README.md`.

## License

MIT
