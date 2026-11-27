"""The confirmation page, the one step a person takes themselves, and its message pages."""

import base64
from html import escape
from pathlib import Path

from mcp_careers.roles import Role
from mcp_careers.submission import Application

ASSETS = Path(__file__).parent / "assets"
NOTE_PREVIEW_CHARS = 280


def _data_uri(name: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode((ASSETS / name).read_bytes()).decode()


# The full logo, from NimbleBrain's brand source: the light variant on light grounds, the
# dark one on dark. Images, not inline SVG, so the two copies' gradient ids cannot collide.
_LOGO = (
    "<picture class='logo'>"
    f"<source media='(prefers-color-scheme: dark)' srcset='{_data_uri('nb-logo-full-dark.svg')}'>"
    f"<img src='{_data_uri('nb-logo-full-light.svg')}' alt='NimbleBrain' width='168' height='33'>"
    "</picture>"
)

# Colors are the website's theme tokens: one accent (electric), the ink and the paper ground.
# The surface is flat; the logo is the only color besides the accent. Change them at the
# brand's source first.
_STYLE = """
:root { color-scheme: light dark;
  --bg: #f1f5fa; --card: #ffffff; --ink: #0e1320; --quiet: #494f61; --rule: #dfe5ed;
  --accent: #1433F9; --accent-strong: #0b0fbe; --on-accent: #ffffff;
  --danger: #b42318; --danger-bg: #fef3f2; }
@media (prefers-color-scheme: dark) { :root {
  --bg: #0e1320; --card: #151b2b; --ink: #f4f6fb; --quiet: #a7b0c4; --rule: #262e42;
  --accent: #4f7ffb; --accent-strong: #9db7ef; --on-accent: #0e1320;
  --danger: #fda29b; --danger-bg: #2a1215; } }
* { box-sizing: border-box; }
html { background: var(--bg); }
body { margin: 0; min-height: 100vh; color: var(--ink);
  font: 17px/1.55 'Hanken Grotesk', system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased; }
main { max-width: 560px; margin: 0 auto; padding: 56px 16px 40px; }
.logo { display: block; margin: 0 0 32px; }
.logo img { display: block; height: 28px; width: auto; }
.card { background: var(--card); border: 1px solid var(--rule); border-radius: 24px;
  padding: 32px; }
h1 { font-size: 30px; line-height: 1.15; font-weight: 700; letter-spacing: -0.01em; margin: 0 0 8px; }
.lead { color: var(--quiet); margin: 0 0 24px; }
.summary { margin: 0 0 24px; border-top: 1px solid var(--rule); }
.row { display: grid; grid-template-columns: 9rem 1fr; gap: 16px; padding: 12px 0;
  border-bottom: 1px solid var(--rule); }
.row dt { color: var(--quiet); font-size: 15px; }
.row dd { margin: 0; overflow-wrap: anywhere; }
.row dd.note { white-space: pre-line; font-size: 15px; }
a { color: var(--accent); text-underline-offset: 3px; }
a:hover { color: var(--accent-strong); }
.hint { font-size: 15px; color: var(--quiet); margin: 0 0 24px; padding-left: 12px;
  border-left: 2px solid var(--rule); }
.notice { margin: 0 0 24px; padding: 12px 16px; border-radius: 12px; font-size: 15px;
  color: var(--danger); background: var(--danger-bg); }
.cf-turnstile { min-height: 65px; margin: 0 0 16px; }
button { width: 100%; font: inherit; font-weight: 600; padding: 14px 20px; border: 0;
  border-radius: 12px; background: var(--accent); color: var(--on-accent); cursor: pointer; }
button:hover { filter: brightness(1.08); }
button:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (max-width: 480px) { .card { padding: 24px 20px; } .row { grid-template-columns: 1fr; gap: 2px; } }
"""

_FONT = (
    "<link rel='preconnect' href='https://fonts.googleapis.com'>"
    "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
    "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;600;700&display=swap'>"
)


def _page(title: str, body: str, *, turnstile: bool = False) -> str:
    script = (
        "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js' async defer></script>"
        if turnstile
        else ""
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta name='robots' content='noindex'>"
        f"<title>{escape(title)} · NimbleBrain careers</title>{_FONT}<style>{_STYLE}</style>{script}"
        f"</head><body><main>{_LOGO}{body}</main></body></html>"
    )


def _link(url: str) -> str:
    safe = escape(url, quote=True)
    return f"<a href='{safe}' target='_blank' rel='noopener noreferrer'>{escape(url)}</a>"


def _row(label: str, value_html: str, cls: str = "") -> str:
    klass = f" class='{cls}'" if cls else ""
    return f"<div class='row'><dt>{escape(label)}</dt><dd{klass}>{value_html}</dd></div>"


def confirm_page(app: Application, role: Role, site_key: str, *, error: str | None = None) -> str:
    rows = [
        _row("Role", escape(role.title)),
        _row("Name", escape(app.name)),
        _row("Email", escape(app.email)),
        _row("Resume", _link(app.resume_url)),
    ]
    if app.link:
        rows.append(_row("Built with agents", _link(app.link)))
    if app.note:
        preview = (
            app.note if len(app.note) <= NOTE_PREVIEW_CHARS else app.note[:NOTE_PREVIEW_CHARS] + "…"
        )
        rows.append(_row("Your answer", escape(preview), "note"))
    notice = f"<p class='notice' role='alert'>{escape(error)}</p>" if error else ""
    body = (
        "<div class='card'>"
        "<h1>Send your application</h1>"
        "<p class='lead'>Your agent put this together. Check it's right, then send it to the "
        "NimbleBrain team. One of us will email you.</p>"
        f"{notice}"
        f"<dl class='summary'>{''.join(rows)}</dl>"
        "<p class='hint'>Check your resume link in a private window. If it asks you to sign "
        "in, we won't be able to open it.</p>"
        "<form method='post'>"
        f"<div class='cf-turnstile' data-sitekey='{escape(site_key, quote=True)}' "
        "data-theme='auto' data-size='flexible'></div>"
        "<button type='submit'>Send application</button>"
        "</form>"
        "</div>"
    )
    return _page("Send your application", body, turnstile=True)


def message_page(title: str, message: str) -> str:
    body = (
        "<div class='card'>"
        f"<h1>{escape(title)}</h1>"
        f"<p class='lead' style='margin:0'>{escape(message)}</p>"
        "</div>"
    )
    return _page(title, body)
