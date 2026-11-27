"""What an application holds, and the checks it must pass before anyone is asked to confirm it.

Every field is model output, so every field is checked here, and nothing in an application
is ever fetched: the links are passed to Slack as links, never opened.
"""

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

MAX_NAME = 100
MAX_EMAIL = 254
MAX_URL = 500
MAX_NOTE_WORDS = 300
# A cap in characters too, so a note always fits one Slack block untrimmed.
MAX_NOTE_CHARS = 2_000

_EMAIL = re.compile(r"^[^@\s<>|]+@[^@\s<>|]+\.[^@\s<>|]+$")
# Characters that would break or inject into a Slack link (`<url|text>`).
_URL_FORBIDDEN = re.compile(r"[\s<>|\"']")


@dataclass(frozen=True)
class Application:
    role: str
    name: str
    email: str
    resume_url: str
    link: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def word_count(text: str) -> int:
    return len(text.split())


def _bad_url(url: str) -> bool:
    parts = urlsplit(url)
    return (
        len(url) > MAX_URL
        or parts.scheme != "https"
        or not parts.netloc
        or bool(_URL_FORBIDDEN.search(url))
    )


def problems(app: Application, open_roles: set[str]) -> list[str]:
    """Everything wrong with an application, each as an instruction the agent can act on."""
    found: list[str] = []

    if app.role not in open_roles:
        listed = ", ".join(sorted(open_roles)) or "none right now"
        found.append(f"`role` must be one of the open roles: {listed}.")

    if not app.name:
        found.append("`name` is empty.")
    elif len(app.name) > MAX_NAME or "\n" in app.name:
        found.append(f"`name` must be one line of at most {MAX_NAME} characters.")

    if len(app.email) > MAX_EMAIL or not _EMAIL.match(app.email):
        found.append("`email` must be a single valid email address.")

    if _bad_url(app.resume_url):
        found.append(
            f"`resume_url` must be an https link of at most {MAX_URL} characters, to a resume "
            "or a profile anyone can open without signing in."
        )

    if app.link and _bad_url(app.link):
        found.append(f"`link` must be an https link of at most {MAX_URL} characters, or empty.")

    words = word_count(app.note)
    if words > MAX_NOTE_WORDS or len(app.note) > MAX_NOTE_CHARS:
        found.append(
            f"`note` must be at most {MAX_NOTE_WORDS} words and {MAX_NOTE_CHARS:,} characters "
            f"(it has {words} words, {len(app.note):,} characters)."
        )

    return found


def normalized(app: Application) -> Application:
    return Application(
        role=app.role.strip(),
        name=app.name.strip(),
        email=app.email.strip(),
        resume_url=app.resume_url.strip(),
        link=app.link.strip(),
        note=app.note.strip(),
    )
