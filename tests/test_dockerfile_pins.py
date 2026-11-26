"""Every external image the Dockerfile uses is pinned by digest, and CI runs the same uv.

A rebuild of the same commit must pull the same bytes, or the image changes while
nothing in the repo did.
"""

import os
import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"

FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.I)
COPY_FROM = re.compile(r"^\s*COPY\s+(?:--\S+\s+)*--from=(\S+)", re.I)
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def external_images(text: str) -> list[str]:
    stages: set[str] = set()
    refs: list[str] = []
    for line in text.splitlines():
        if m := FROM.match(line):
            if m.group(1) not in stages:
                refs.append(m.group(1))
            if m.group(2):
                stages.add(m.group(2))
        elif (m := COPY_FROM.match(line)) and m.group(1) not in stages and not m.group(1).isdigit():
            refs.append(m.group(1))
    return refs


def test_every_external_image_is_pinned_by_digest():
    refs = external_images(DOCKERFILE.read_text())
    assert refs
    unpinned = [ref for ref in refs if not DIGEST.search(ref)]
    assert not unpinned, f"pin these as tag@sha256:<index digest>: {unpinned}"


def _verify_steps() -> list[dict]:
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    return ci["jobs"]["verify"]["steps"]


def test_ci_installs_the_uv_the_image_copies_in(tmp_path):
    # CI reads the uv version from the Dockerfile rather than keeping a copy, so a green
    # `uv sync --locked` in CI is a verdict from the image's own uv. This runs that CI
    # step's script against the real Dockerfile and checks setup-uv consumes its output.
    steps = _verify_steps()
    [step] = [s for s in steps if s.get("id") == "uv"]
    [setup] = [s for s in steps if s.get("uses", "").startswith("astral-sh/setup-uv@")]
    assert setup["with"]["version"] == "${{ steps.uv.outputs.version }}"
    assert steps.index(step) < steps.index(setup)

    out = tmp_path / "github_output"
    subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        cwd=REPO_ROOT,
        env={**os.environ, "GITHUB_OUTPUT": str(out)},
        check=True,
    )
    [image_uv] = [
        r for r in external_images(DOCKERFILE.read_text()) if r.startswith("ghcr.io/astral-sh/uv:")
    ]
    assert out.read_text() == f"version={image_uv.split(':', 1)[1].split('@', 1)[0]}\n"


def test_ci_uv_step_fails_rather_than_falling_back_to_latest(tmp_path):
    # An empty version makes setup-uv install the latest uv, which is the drift this
    # step exists to prevent, so a Dockerfile it cannot read must fail the run.
    [step] = [s for s in _verify_steps() if s.get("id") == "uv"]
    (tmp_path / "Dockerfile").write_text("FROM python:3.13-slim\nRUN pip install uv\n")
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(tmp_path / "out")},
        capture_output=True,
    )
    assert result.returncode != 0
