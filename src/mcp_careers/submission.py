"""What an application holds, and the checks it must pass before anyone is asked to confirm it.

Every field is model output, so every field is checked here, and nothing in a submission is
ever fetched: `resume_url` is passed to Slack as a link, never opened.
"""

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

MAX_NAME = 100
MAX_EMAIL = 254
MAX_URL = 500
MAX_SKILL = 20_000
NOTE_MIN_WORDS = 50
NOTE_MAX_WORDS = 300

_EMAIL = re.compile(r"^[^@\s<>|]+@[^@\s<>|]+\.[^@\s<>|]+$")
# Characters that would break or inject into a Slack link (`<url|text>`).
_URL_FORBIDDEN = re.compile(r"[\s<>|\"']")
_FRONTMATTER = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*(\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class Submission:
    role: str
    name: str
    email: str
    resume_url: str
    skill: str
    note: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def word_count(text: str) -> int:
    return len(text.split())


def problems(sub: Submission, open_roles: set[str]) -> list[str]:
    """Everything wrong with a submission, each as an instruction the agent can act on."""
    found: list[str] = []

    if sub.role not in open_roles:
        listed = ", ".join(sorted(open_roles)) or "none right now"
        found.append(f"`role` must be one of the open roles: {listed}.")

    name = sub.name.strip()
    if not name:
        found.append("`name` is empty.")
    elif len(name) > MAX_NAME or "\n" in name:
        found.append(f"`name` must be one line of at most {MAX_NAME} characters.")

    email = sub.email.strip()
    if len(email) > MAX_EMAIL or not _EMAIL.match(email):
        found.append("`email` must be a single valid email address.")

    url = sub.resume_url.strip()
    parts = urlsplit(url)
    if (
        len(url) > MAX_URL
        or parts.scheme != "https"
        or not parts.netloc
        or _URL_FORBIDDEN.search(url)
    ):
        found.append(
            f"`resume_url` must be an https link of at most {MAX_URL} characters "
            "(a PDF, a document, or a profile page)."
        )

    skill = sub.skill.strip()
    if not skill:
        found.append("`skill` is empty: send the whole SKILL.md.")
    elif len(skill) > MAX_SKILL:
        found.append(f"`skill` is over {MAX_SKILL:,} characters.")
    else:
        match = _FRONTMATTER.match(skill)
        body = match.group("body") if match else ""
        if not match or not re.search(r"^name:\s*\S", body, re.M):
            found.append("`skill` must start with YAML frontmatter that has a `name`.")
        if not match or not re.search(r"^description:\s*\S", body, re.M):
            found.append("`skill` frontmatter must have a `description`.")

    words = word_count(sub.note)
    if not NOTE_MIN_WORDS <= words <= NOTE_MAX_WORDS:
        found.append(
            f"`note` must be {NOTE_MIN_WORDS} to {NOTE_MAX_WORDS} words (it has {words}), "
            "written by the person: what the agent got wrong, how they caught it, and what "
            "they would change with another day."
        )

    return found


def normalized(sub: Submission) -> Submission:
    return Submission(
        role=sub.role.strip(),
        name=sub.name.strip(),
        email=sub.email.strip(),
        resume_url=sub.resume_url.strip(),
        skill=sub.skill.strip(),
        note=sub.note.strip(),
    )
