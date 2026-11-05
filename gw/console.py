"""console.py - serve the load-console page from console/ static files.

The page lives in plain files (console/index.html, later console/style.css +
console/app.js) instead of being embedded in Python. This module assembles it
on every request and substitutes the build placeholders:

  __VERSION__     from the VERSION file at the repo root
  __GITHUB_URL__  gateway.json "github_url", default below
  __GW_PORT__     the port this gateway actually listens on
"""
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSOLE_DIR = os.path.join(_ROOT, "console")

GITHUB_URL_DEFAULT = "https://github.com/smallmj/strata-gw"


def _gateway_cfg() -> dict:
    try:
        with open(os.path.join(_ROOT, "gateway.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def version() -> str:
    try:
        with open(os.path.join(_ROOT, "VERSION"), encoding="utf-8-sig") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def github_url() -> str:
    u = _gateway_cfg().get("github_url")
    return u if isinstance(u, str) and u.startswith(("http://", "https://")) else GITHUB_URL_DEFAULT


def _read(name: str) -> str:
    with open(os.path.join(CONSOLE_DIR, name), encoding="utf-8") as f:
        return f.read()


def _assets() -> list:
    """Optional static pieces folded back inline, in order:
    (link-tag, file) / (script-tag, file). Missing file = tag stays as is."""
    out = []
    for tag, name in (
        ('<link rel="stylesheet" href="style.css">', "style.css"),
        ('<script src="i18n.js"></script>', "i18n.js"),
        ('<script src="app.js"></script>', "app.js"),
    ):
        if os.path.isfile(os.path.join(CONSOLE_DIR, name)):
            out.append((tag, name))
    return out


def render(port: int) -> str:
    page = _read("index.html")
    for tag, name in _assets():
        body = _read(name).rstrip("\n")
        if tag.startswith("<link"):
            repl = "<style>\n" + body + "\n</style>"
        elif name == "i18n.js":
            repl = "<script>\n" + body + "\n</script>"
        else:
            repl = "<script>\n" + body + "\n</script>"
        page = page.replace(tag, repl)
    return (page.replace("__VERSION__", version())
                .replace("__GITHUB_URL__", github_url())
                .replace("__GW_PORT__", str(port)))
