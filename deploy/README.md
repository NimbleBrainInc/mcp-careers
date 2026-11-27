# Deploy

The server is a stateless container: any instance serves any request, and the state is
expiring keys in Redis. Applicants do not sign in.

| Environment | Careers config | Slack channel |
|---|---|---|
| Staging | its own `CAREERS_CONFIG` | the hiring channel, shared for now |
| Production, at `https://careers.nimblebrain.ai/mcp` | its own `CAREERS_CONFIG` | the hiring channel |

## How a change ships

- **Staging, on merge.** `ci.yml` verifies, builds `mcp-careers:<short-sha>`, pushes it, and
  asks the deploy configuration to point staging at it.
- **Production, on a version tag.** Bump `version` in `pyproject.toml` and `server.json`
  together, merge, let that commit ride staging, then tag it:

  ```sh
  git tag v0.1.0 <sha> && git push origin v0.1.0
  ```

  `release.yml` refuses a tag that disagrees with `server.json`, retags the staging image
  as the version (no rebuild), and asks the deploy configuration to point production at
  it. A pushed `v*` tag promotes to production for real; there is no dry run.
- **Re-run a release** at its tag: `gh workflow run release.yml --ref v0.1.0`.

## Credentials

The workflows name every variable, secret and environment they need, and each job that
pushes or deploys skips until its credentials exist, so the repository is safe to merge
before them. Keys that can push an image or change a deployment are secrets of GitHub
environments limited to `main` or to `v*` tags, never repository or organization secrets,
which every `pull_request` run can read. Provisioning them is documented with NimbleBrain's
deploy configuration.

## Runtime settings

`AGENTS.md` lists every setting. A deployment needs these from its secret store:

| Setting | Value |
|---|---|
| `CAREERS_CONFIG` | the deployment's careers config as YAML (`examples/careers.yaml` has the shape); the server refuses to start without it |
| `CAREERS_PUBLIC_URL` | the environment's origin, e.g. `https://careers.nimblebrain.ai` |
| `REDIS_URL` | the Redis instance |
| `SLACK_WEBHOOK_URL` | an incoming webhook for the hiring channel |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | one Turnstile widget, limited to the environment's hosts |

Without the webhook and both Turnstile keys the server still starts, and the submit tool
refuses with `internal`, pointing applicants to email.

## Health

`GET /health` is liveness only; it touches neither Redis nor an outside service. The
container listens on port 8080.
