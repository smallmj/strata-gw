"""config.py - paths, ports and env constants for the gateway. Stdlib only."""
from __future__ import annotations

import json
import os
import re
from urllib import request as urlrequest

# The newest host-Strata generation this gateway was walked end-to-end on.
# Single source in the repo: bump together with tests/compat-baseline.json and
# the sim-kit protocol stamp in ONE release-day commit (T19), after the compat
# canary reports the newest upstream tag diff-free. Advisory only: a newer
# engine paints a yellow banner, it never blocks anything.
TESTED_UP_TO = {"engine": "0.1.62", "strata": "v0.2.16"}

# repo root (the directory holding strata-router.py; gw/ lives under it)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROUTER_PORT = 18075   # live value resolved at boot by router_port() below
def router_port() -> int:
    """Which port the gateway LISTENS on at boot: env STRATA_ROUTER_PORT wins,
    then gateway.json "router_port" (saved from the settings page), then the
    old 18075 default. main.py stamps ROUTER_PORT with this at startup."""
    e = env("STRATA_ROUTER_PORT")
    if e:
        try:
            return int(e)
        except ValueError:
            pass
    g = gateway_cfg().get("router_port")
    try:
        g = int(g)
        if 1024 <= g <= 65535:
            return g
    except (TypeError, ValueError):
        pass
    return 18075


FIRST_BACKEND_PORT = int(os.environ.get("STRATA_FIRST_BACKEND_PORT", "18101"))
PORTS_FILE = os.path.join(ROOT, "router-ports.json")
SPAWN_COOLDOWN_S = 60.0
LOAD_WAIT_S = 300.0           # a lazy backend's API comes up well inside this;
                              # 0.1.60 drafting may pull ~5.2 GB of speculative
                              # draft weights on a box's first cold start (the
                              # upstream issue log saw 450 s for that fetch)
RESIDENT_TTL_S = 3.0          # how long a residency answer is trusted without re-asking
GEN_PATHS = ("/v1/chat/completions", "/v1/completions", "/v1/responses",
             "/v1/messages", "/v1/embeddings", "/chat/completions", "/completions")



def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def strata_home() -> str:
    """Strata engine root: env STRATA_HOME > gateway.json "strata_home" > repo ROOT.
    The production install keeps the gateway inside the engine root; an open-source
    checkout may live elsewhere and point at the engine via either knob."""
    h = env("STRATA_HOME") or str(gateway_cfg().get("strata_home") or "")
    if not h:
        return ROOT
    return h if os.path.isabs(h) else os.path.join(ROOT, h)


def resolve_python():
    """Cross-platform engine python: STRATA_PYTHON env wins outright, then the
    .venv under the engine root - and under <root>/terminal/, which is where
    v0.2.16 keeps it (Windows Scripts layout or POSIX bin layout).
    None = not found."""
    p = env("STRATA_PYTHON")
    if p:
        return p
    home = strata_home()
    for sub in ("terminal", ""):            # v0.2.16 first, legacy as fallback
        base = os.path.join(home, sub, ".venv") if sub else os.path.join(home, ".venv")
        for cand in (os.path.join(base, "Scripts", "python.exe"),
                     os.path.join(base, "bin", "python"),
                     os.path.join(base, "bin", "python3")):
            if os.path.isfile(cand):
                return cand
    return None


def server_py() -> str:
    """The engine's serve wrapper script. v0.2.16 moved the whole install under
    <home>/terminal/; older installs keep it at <home>/serve/. Resolved per
    call (strata_home() is hot), so an adopted home takes effect without a
    restart. When neither exists, the legacy path comes back anyway - the
    caller's "engine not found" message must name a plausible place."""
    home = strata_home()
    for cand in (os.path.join(home, "terminal", "serve", "server.py"),
                 os.path.join(home, "serve", "server.py")):
        if os.path.isfile(cand):
            return cand
    return os.path.join(home, "serve", "server.py")


def gateway_cfg() -> dict:
    """Optional gateway.json next to the entry (re-read per call: hot reload).
    Sections: "gpu_free" (external VRAM handover), later "github_url" etc."""
    try:
        with open(os.path.join(ROOT, "gateway.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}

WATCH_S = float(os.environ.get("STRATA_WATCH_S", "20"))   # state-transition watcher

PROXY_PATHS = ("/router/settings", "/router/config", "/router/mcp", "/router/status",
               "/router/metrics", "/router/props", "/router/slots")   # mirrored to the page

ASSET_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}\.(?:png|webp|jpe?g|mp4|webm|woff2)$")

# Internal calls must never go through a system proxy (http_proxy/HTTPS_PROXY
# would hijack 127.0.0.1 traffic on a box with a clash client running).
OPENER = urlrequest.build_opener(urlrequest.ProxyHandler({}))
