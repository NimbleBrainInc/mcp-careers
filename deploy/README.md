# Deploy

The server is a stateless app on NimbleBrain's cluster: any pod serves any request, and
the state is expiring keys in Redis. It is not a platform fleet server; applicants are not
tenants.

| Environment | URL | Roles shown | Slack channel |
|---|---|---|---|
| Staging | `https://careers.preview.nimblebrain.ai/mcp` | `CAREERS_ENV=staging` | the hiring channel, shared for now: staging shows only the test role, whose title ends in "(test)" |
| Production | `https://careers.nimblebrain.ai/mcp` | `CAREERS_ENV=production` | the hiring channel |

## How a change ships

- **Staging, on merge.** `ci.yml` verifies, builds `mcp-careers:<short-sha>`, pushes it to
  ECR, and dispatches `fleet-image-pushed` to the deploy-config repo, which points staging
  at the new image. GitOps rolls it.
- **Production, on a version tag.** Bump `version` in `pyproject.toml` and `server.json`
  together, merge, let that commit ride staging, then tag it:

  ```sh
  git tag v0.1.0 <sha> && git push origin v0.1.0
  ```

  `release.yml` refuses a tag that disagrees with `server.json`, retags the staging image
  as the version (no rebuild), and dispatches `prod-image-promoted`. A pushed `v*` tag
  promotes to production for real; there is no dry run.
- **Re-run a release** at its tag: `gh workflow run release.yml --ref v0.1.0`.

## Provisioning, once

The CI jobs that push and promote skip until these exist, so the repo is safe to merge
before them.

| What | Where |
|---|---|
| ECR repository `mcp-careers`, tags immutable | infrastructure |
| `AWS_ROLE_ARN`, an OIDC role that can push to it | repository variable |
| `EDGE_BUMP_APP_ID`, `DEPLOY_CONFIG_REPO` | organization variables |
| `EDGE_BUMP_APP_KEY` | secret of the `deploy-config-edge` environment (deployment branch `main` only) |
| `PROD_PROMOTE_APP_ID` | organization variable |
| `PROD_PROMOTE_APP_KEY` | secret of the `deploy-config-prod` environment (deployment tags `v*` only) |
| `mcp-careers` in the deploy-config receivers' allowlists, and an app entry per environment | deploy-config repo |
| `CI_SLACK_WEBHOOK_URL` (optional) | repository secret, for failed runs on main |

The app keys live in environments, never as repository or organization secrets, because
every `pull_request` run can read those.

## Runtime settings

Each environment needs these from its secret store; `AGENTS.md` lists every setting.

| Setting | Value |
|---|---|
| `CAREERS_ENV` | `staging` or `production` |
| `CAREERS_PUBLIC_URL` | the environment's origin, e.g. `https://careers.nimblebrain.ai` |
| `REDIS_URL` | the shared Redis |
| `SLACK_WEBHOOK_URL` | an incoming webhook for that environment's channel |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | one Turnstile widget, limited to both hosts |

Without the webhook and both Turnstile keys the server still starts, and the submit tool
refuses with `internal`, pointing applicants to email.

## Health

`GET /health` is liveness only; it touches neither Redis nor an outside service.
The container listens on port 8080.
