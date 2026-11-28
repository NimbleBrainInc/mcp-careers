# mcp-careers

The NimbleBrain careers MCP server: an applicant's agent reads the open roles and submits;
the person confirms on a page with Turnstile; the application posts to Slack. Public repo.

## Layout

```
src/mcp_careers/
├── server.py        # FastMCP server: the two tools, /confirm/{token}, /health
├── config.py        # every setting, from the environment
├── roles.py         # loads and checks the deployment's careers config
├── submission.py    # the fields and every check on them
├── store.py         # Redis keys, all expiring (layout in its docstring)
├── outbound.py      # Turnstile siteverify, the Slack webhook, the Slack message
├── pages.py         # the confirmation and message pages
├── assets/          # the full logo, light and dark, from the brand source
└── skills/apply-to-nimblebrain/
    └── SKILL.md     # served at skill://apply-to-nimblebrain/SKILL.md
```

## Rules

- **Nothing posts without a person.** Only the confirmation page's POST, after Turnstile
  passes, calls Slack. The submit tool holds and returns a link; it never posts.
- **Every field is untrusted.** Checks live in `submission.py`. Nothing in an application is
  fetched: `resume_url` and `link` are links in the Slack message, never opened. The server
  does not check that they open: LinkedIn refuses automated requests, and fetching an
  applicant's URL from inside the cluster is a server-side request forgery risk. The skill and
  the confirmation page ask the person to check instead.
- **Applicant text is escaped for Slack** (`slack_escape`) and sent as a quote, so it
  cannot ping a channel or forge a link. Agents must not read the channel it posts to.
- **The careers content is the deployment's, never this repo's.** Who is hiring, the
  question applicants answer, and the open roles come from the deployment's config
  (`CAREERS_CONFIG`, or a path in `CAREERS_CONFIG_FILE`; `examples/careers.yaml` has the
  shape). The server refuses to start without one. Nothing in code or tool descriptions names
  a role or the question.
- **One source per fact.** The Server Card's name, version, title, description and website
  are restated in `server.json`, and `tests/test_server_card.py` holds them equal.
- **A breaking change to a tool's inputs takes a new tool name.** A connected client can keep
  an old copy of a tool's schema until it reconnects, so removing a field, newly requiring
  one, or changing a type breaks it. Add the tool under a new name, keep the old one for one
  release, then remove it. Adding an optional field or rewording a description is safe in
  place. The golden files show every surface change in review.
- **The public repo carries no internal detail**: no tenant names, internal hostnames, or
  paths into private repos, in code, docs or fixtures.

## Server SDK

Built on `nimblebrain-server-sdk`: every tool is annotated `READS`, `ADDS` or `CHANGES`;
a failure is a raised `ServiceError` (`add_error_contract`); the skill is registered with
`add_skills` and never served by hand; the card comes from `add_server_card`. Tests that
cross the wire run on both protocol eras (`mode="auto"` and `"legacy"`).

## Settings

| Variable | Default | |
|---|---|---|
| `CAREERS_CONFIG` | none | The careers config as YAML: `about`, `question`, `roles`. |
| `CAREERS_CONFIG_FILE` | none | A path to the same, when `CAREERS_CONFIG` is unset. One of the two is required. |
| `CAREERS_PUBLIC_URL` | `http://127.0.0.1:8000` | Origin of the confirmation link. |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | |
| `SLACK_WEBHOOK_URL` | none | Required to accept applications. |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | none | Required to accept applications. |
| `CAREERS_DAILY_CAP` | `10` | Posted applications per UTC day. |
| `CAREERS_SUBMIT_LIMIT_PER_HOUR` | `10` | Submit calls per client IP per hour. |
| `CAREERS_DEDUPE_DAYS` | `60` | One application per email in this window. |
| `CAREERS_PENDING_TTL_SECONDS` | `3600` | How long a confirmation link lasts. |
| `CAREERS_TRUSTED_PROXY_HOPS` | `1` | X-Forwarded-For entries from the right that name the client. |
| `CAREERS_WEEKLY_DIGEST` | `1` | `0` stops the Monday post of last week's funnel counts to the Slack webhook. |

Without the Slack webhook and both Turnstile keys, the submit tool refuses with `internal`
and says to try again later.

## Verify

```sh
uv sync --locked
uv run ruff format --check . && uv run ruff check . && uv run ty check src && uv run pytest
```

`uv.lock` is the gate for every dependency: CI and the image both install with `--locked`.
Change a dependency with `uv lock` and commit the lock with it. CI runs the uv the
Dockerfile pins, and `tests/test_dockerfile_pins.py` fails if an image loses its digest or
CI stops reading that pin. Renovate opens the dependency PRs; `nimblebrain-server-sdk`
waits for approval, since a v0.x minor may break the API.

## The surface is pinned by a golden record

`tests/golden/{auto,legacy}.json` record what a host sees on each protocol era: the tools
with their schemas and annotations, the resources and a digest of each skill file, the
instructions, and the Server Card. A difference fails the test and writes
`<era>.actual.json`. To accept an intended change, `UPDATE_GOLDEN=1 uv run pytest
tests/test_golden.py`, and the diff goes through review with the PR.

## Versioning and deploy

The version is `pyproject.toml`'s; `__version__` reads it from the installed package, and
`server.json` restates it (`tests/test_server_card.py`). Bump both before tagging a release.
Shipping, releases and provisioning: `deploy/README.md`.
