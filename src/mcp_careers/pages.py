"""The confirmation page: the one step a person takes themselves."""

from html import escape

from mcp_careers.roles import Role
from mcp_careers.submission import Submission

# Colors are NimbleBrain's brand palette (background, foreground, muted-foreground, border,
# primary), light then dark. Change them at the brand's source first, then here.
_STYLE = """
:root { color-scheme: light dark; --bg: #ffffff; --ink: #09090b; --quiet: #5c5c66;
  --line: #e4e4e7; --accent: #315EDB; --on-accent: #ffffff; }
@media (prefers-color-scheme: dark) { :root { --bg: #141414; --ink: #ededed; --quiet: #a3a3a3;
  --line: #2b2b2b; --accent: #799ff5; --on-accent: #000000; } }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.5 'Hanken Grotesk', system-ui, sans-serif; }
main { max-width: 560px; margin: 0 auto; padding: 48px 16px; }
h1 { font-size: 24px; margin: 0 0 8px; }
p { margin: 0 0 16px; color: var(--quiet); }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; margin: 24px 0;
  padding: 16px; border: 1px solid var(--line); border-radius: 8px; }
dt { color: var(--quiet); } dd { margin: 0; overflow-wrap: anywhere; }
button { font: inherit; padding: 10px 20px; border-radius: 8px; border: 0;
  background: var(--accent); color: var(--on-accent); cursor: pointer; margin-top: 16px; }
.cf-turnstile { margin-top: 8px; }
"""


def _page(title: str, body: str, *, turnstile: bool = False) -> str:
    script = (
        '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
        if turnstile
        else ""
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta name='robots' content='noindex'>"
        f"<title>{escape(title)} · NimbleBrain careers</title><style>{_STYLE}</style>{script}"
        f"</head><body><main>{body}</main></body></html>"
    )


def confirm_page(sub: Submission, role: Role, site_key: str, *, error: str | None = None) -> str:
    notice = f"<p><strong>{escape(error)}</strong></p>" if error else ""
    body = (
        "<h1>Send your application</h1>"
        "<p>Your agent put this together. Check it's right, then send it. "
        "It goes to the NimbleBrain team, and one of us will email you.</p>"
        f"{notice}"
        "<dl>"
        f"<dt>Role</dt><dd>{escape(role.title)}</dd>"
        f"<dt>Name</dt><dd>{escape(sub.name)}</dd>"
        f"<dt>Email</dt><dd>{escape(sub.email)}</dd>"
        f"<dt>Resume</dt><dd>{escape(sub.resume_url)}</dd>"
        f"<dt>Skill</dt><dd>{len(sub.skill):,} characters</dd>"
        f"<dt>Note</dt><dd>{len(sub.note.split())} words</dd>"
        "</dl>"
        "<form method='post'>"
        f"<div class='cf-turnstile' data-sitekey='{escape(site_key, quote=True)}'></div>"
        "<button type='submit'>Send application</button>"
        "</form>"
    )
    return _page("Send your application", body, turnstile=True)


def message_page(title: str, message: str) -> str:
    return _page(title, f"<h1>{escape(title)}</h1><p>{escape(message)}</p>")
