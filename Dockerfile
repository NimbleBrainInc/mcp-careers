FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b

COPY --from=ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 /uv /usr/local/bin/uv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Exactly the committed uv.lock: `--locked` fails the build if it and pyproject.toml disagree.
# Dependencies first, in their own layer, so a source change reuses it.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --no-cache

RUN useradd --uid 10001 --no-create-home app
USER 10001
EXPOSE 8080

# Stateless: every pod serves any request; the state is in Redis.
CMD ["uvicorn", "mcp_careers.server:app", "--host", "0.0.0.0", "--port", "8080"]
