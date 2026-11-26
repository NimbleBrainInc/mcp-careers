"""Field checks and the Slack message, without the wire."""

from mcp_careers.outbound import application_message, slack_escape
from mcp_careers.roles import load_roles
from mcp_careers.submission import Submission, problems
from tests.conftest import good_args

ROLES = {"test-agent-engineer"}


def sub(**overrides: str) -> Submission:
    return Submission(**good_args(**overrides))


def test_a_good_submission_has_no_problems() -> None:
    assert problems(sub(), ROLES) == []


def test_the_resume_link_must_be_plain_https() -> None:
    for url in ("http://x.test/cv", "javascript:alert(1)", "https://x.test/a|b", "https:///cv"):
        assert any("`resume_url`" in p for p in problems(sub(resume_url=url), ROLES)), url


def test_the_skill_needs_frontmatter_with_name_and_description() -> None:
    found = problems(sub(skill="# just a heading"), ROLES)
    assert any("`name`" in p for p in found) and any("`description`" in p for p in found)


def test_a_multiline_name_is_refused() -> None:
    assert any("`name`" in p for p in problems(sub(name="Ada\nLovelace"), ROLES))


def test_slack_escaping_covers_control_characters() -> None:
    assert slack_escape("<!channel> & <@U1>") == "&lt;!channel&gt; &amp; &lt;@U1&gt;"


def test_a_long_skill_is_trimmed_to_fit_slack() -> None:
    role = load_roles("development")["test-agent-engineer"]
    long_skill = good_args()["skill"] + "x" * 10_000
    message = application_message(sub(skill=long_skill), role)
    skill_block = message["blocks"][-1]["text"]["text"]
    assert len(skill_block) < 3_000 and "trimmed" in skill_block


def test_applicant_fences_cannot_close_the_code_block() -> None:
    role = load_roles("development")["test-agent-engineer"]
    message = application_message(sub(note=good_args()["note"] + " ``` *bold*"), role)
    note_block = message["blocks"][-2]["text"]["text"]
    assert note_block.count("```") == 2
