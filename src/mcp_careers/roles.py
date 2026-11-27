"""The deployment's careers config: who is hiring, the question, and the open roles.

The config is the deployment's, not this repository's. It arrives as the YAML itself in
CAREERS_CONFIG, or as a path in CAREERS_CONFIG_FILE (examples/careers.yaml has the shape).
The server refuses to start without one, so a deployment never comes up with another's roles.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from mcp_careers.config import Settings

MAX_QUESTION_CHARS = 500


class CareersConfigError(Exception):
    """The careers config is missing or malformed; the message says what to fix."""


@dataclass(frozen=True)
class Role:
    id: str
    title: str
    location: str
    summary: str
    type: str | None = None
    pay_range: str | None = None


@dataclass(frozen=True)
class Careers:
    about: str
    question: str
    roles: dict[str, Role]


def _text(settings: Settings) -> str:
    if settings.careers_config:
        return settings.careers_config
    if settings.careers_config_file:
        try:
            return Path(settings.careers_config_file).read_text()
        except OSError as e:
            raise CareersConfigError(
                f"CAREERS_CONFIG_FILE cannot be read: {settings.careers_config_file}"
            ) from e
    raise CareersConfigError(
        "No careers config: set CAREERS_CONFIG (the YAML) or CAREERS_CONFIG_FILE (a path). "
        "examples/careers.yaml has the shape."
    )


def _str(entry: dict, key: str, where: str, *, required: bool = True) -> str | None:
    value = entry.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CareersConfigError(f"{where}: `{key}` must be a non-empty string.")
    return value.strip()


def parse(text: str) -> Careers:
    """Read and check a careers config; raises CareersConfigError naming what is wrong."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise CareersConfigError(f"The careers config is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise CareersConfigError(
            "The careers config must be a mapping with about, question, roles."
        )
    about = _str(data, "about", "careers config")
    question = _str(data, "question", "careers config")
    assert about is not None and question is not None
    if len(question) > MAX_QUESTION_CHARS:
        raise CareersConfigError(f"`question` must be at most {MAX_QUESTION_CHARS} characters.")
    entries = data.get("roles")
    if not isinstance(entries, list):
        raise CareersConfigError("`roles` must be a list (it may be empty).")
    roles: dict[str, Role] = {}
    for i, entry in enumerate(entries):
        where = f"roles[{i}]"
        if not isinstance(entry, dict):
            raise CareersConfigError(f"{where} must be a mapping.")
        role_id = _str(entry, "id", where)
        assert role_id is not None
        if role_id in roles:
            raise CareersConfigError(f"{where}: duplicate role id `{role_id}`.")
        roles[role_id] = Role(
            id=role_id,
            title=_str(entry, "title", where) or "",
            location=_str(entry, "location", where) or "",
            summary=_str(entry, "summary", where) or "",
            type=_str(entry, "type", where, required=False),
            pay_range=_str(entry, "pay_range", where, required=False),
        )
    return Careers(about=about, question=question, roles=roles)


def load(settings: Settings) -> Careers:
    return parse(_text(settings))
