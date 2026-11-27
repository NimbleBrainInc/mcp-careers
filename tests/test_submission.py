"""Field checks and the Slack message, without the wire."""

from mcp_careers.outbound import application_message, slack_escape
from mcp_careers.server import CAREERS
from mcp_careers.submission import Application, problems
from tests.conftest import good_args

ROLES = set(CAREERS.roles)
ROLE = CAREERS.roles["agent-engineer"]
Q = CAREERS.question


def app(**overrides: str) -> Application:
    return Application(**good_args(**overrides))


def test_a_good_application_has_no_problems() -> None:
    assert problems(app(), ROLES, Q) == []


def test_links_must_be_plain_https() -> None:
    for url in ("http://x.test/cv", "javascript:alert(1)", "https://x.test/a|b", "https:///cv"):
        assert any("`resume_url`" in p for p in problems(app(resume_url=url), ROLES, Q)), url
        assert any("`profile_url`" in p for p in problems(app(profile_url=url), ROLES, Q)), url


def test_a_malformed_link_is_a_problem_not_an_error() -> None:
    url = "https://[broken"
    assert any("`resume_url`" in p for p in problems(app(resume_url=url), ROLES, Q))
    assert any("`profile_url`" in p for p in problems(app(profile_url=url), ROLES, Q))


def test_a_note_over_the_character_cap_is_refused() -> None:
    assert any("`note`" in p for p in problems(app(note="x" * 2_001), ROLES, Q))


def test_an_empty_link_is_fine() -> None:
    assert problems(app(profile_url=""), ROLES, Q) == []


def test_the_answer_is_required() -> None:
    assert any("`note`" in p for p in problems(app(note=""), ROLES, Q))


def test_a_multiline_name_is_refused() -> None:
    assert any("`name`" in p for p in problems(app(name="Ada\nLovelace"), ROLES, Q))


def test_slack_escaping_covers_control_characters() -> None:
    assert slack_escape("<!channel> & <@U1>") == "&lt;!channel&gt; &amp; &lt;@U1&gt;"


def test_a_full_note_fits_slack_untrimmed() -> None:
    note = ("x" * 9 + " ") * 200  # 2,000 characters, the most a note may hold
    block = application_message(app(note=note.strip()), ROLE, Q)["blocks"][-1]["text"]["text"]
    assert len(block) < 3_000 and "trimmed" not in block


def test_an_accepted_note_always_fits_one_slack_section() -> None:
    note = "x\n" * 299 + "&" * 1_402  # 2,000 characters and 300 words, escaping to more
    assert problems(app(note=note), ROLES, Q) == []
    block = application_message(app(note=note), ROLE, Q)["blocks"][-1]["text"]["text"]
    assert len(block) <= 3_000 and block.endswith("characters in all)")
    assert all(line.startswith(">") for line in block.splitlines())


def test_the_message_leads_with_who_applied_for_what() -> None:
    message = application_message(app(note=""), ROLE, Q)
    first = message["blocks"][0]["text"]["text"]
    assert first.startswith(":inbox_tray: *Ada Lovelace* applied for *Agent Engineer*")
    assert first.count("\n•  ") == 3
    assert "|example.com/ada.pdf>" in first and "|github.com/ada>" in first
    assert message["text"] == "Ada Lovelace applied for Agent Engineer"


def test_the_answer_is_labelled_with_its_question() -> None:
    blocks = application_message(app(), ROLE, Q)["blocks"]
    assert "what did it get wrong" in blocks[1]["elements"][0]["text"]


def test_every_note_line_is_quoted_and_cannot_end_the_quote() -> None:
    note = "first line\n> not a real quote marker\n\nlast <!here>"
    block = application_message(app(note=note), ROLE, Q)["blocks"][-1]["text"]["text"]
    assert all(line.startswith(">") for line in block.splitlines())
    assert "&gt; not a real quote marker" in block and "<!here>" not in block
