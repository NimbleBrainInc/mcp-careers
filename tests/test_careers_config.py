"""The deployment's careers config: where it comes from, and what it refuses."""

from dataclasses import replace
from pathlib import Path

import pytest

from mcp_careers import config
from mcp_careers.roles import CareersConfigError, load, parse

EXAMPLE = Path(__file__).parent.parent / "examples" / "careers.yaml"
VALID = """
about: We build things.
question: What did your agent get wrong?
roles:
  - {id: a, title: A, location: Remote, summary: Do a.}
"""


def settings(**kw):
    return replace(config.settings, **{"careers_config": None, "careers_config_file": None, **kw})


def test_no_config_refuses_and_says_how_to_fix() -> None:
    with pytest.raises(CareersConfigError, match="CAREERS_CONFIG"):
        load(settings())


def test_the_yaml_wins_over_the_file() -> None:
    careers = load(settings(careers_config=VALID, careers_config_file=str(EXAMPLE)))
    assert list(careers.roles) == ["a"] and careers.about == "We build things."


def test_the_example_config_loads() -> None:
    careers = load(settings(careers_config_file=str(EXAMPLE)))
    assert careers.question and set(careers.roles) == {"agent-engineer", "open-application"}


def test_an_unreadable_file_refuses() -> None:
    with pytest.raises(CareersConfigError, match="cannot be read"):
        load(settings(careers_config_file="/nonexistent/careers.yaml"))


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("not: [valid", "not valid YAML"),
        ("- a list", "mapping"),
        ("about: x\nroles: []", "`question`"),
        ("about: x\nquestion: y", "`roles`"),
        ("about: x\nquestion: y\nroles:\n  - {id: a, title: A, location: R}", "`summary`"),
        (
            "about: x\nquestion: y\nroles:\n"
            "  - {id: a, title: A, location: R, summary: S}\n"
            "  - {id: a, title: B, location: R, summary: S}",
            "duplicate",
        ),
    ],
)
def test_a_malformed_config_refuses_naming_the_problem(text: str, names: str) -> None:
    with pytest.raises(CareersConfigError, match=names):
        parse(text)


def test_an_unknown_role_key_is_refused() -> None:
    with pytest.raises(CareersConfigError, match="team"):
        parse(
            "about: x\nquestion: y\nroles:\n  - {id: a, title: A, location: R, summary: S, team: X}"
        )


def test_no_open_roles_is_allowed() -> None:
    assert parse("about: x\nquestion: y\nroles: []").roles == {}
