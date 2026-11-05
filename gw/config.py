"""config.py - paths, ports and env constants for the gateway. Stdlib only."""
from __future__ import annotations

import json
import os
import re
from urllib import request as urlrequest

# repo root (the directory holding strata-router.py; gw/ lives under it)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROUTER_PORT = int(os.environ.get("STRATA_ROUTER_PORT", "18080"))
FIRST_BACKEND_PORT = 18081
PORTS_FILE = os.path.join(ROOT, "router-ports.json")
SERVER_PY = os.path.join(ROOT, "serve", "server.py")
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
SPAWN_COOLDOWN_S = 60.0
LOAD_WAIT_S = 180.0           # a lazy backend's API comes up well inside this
RESIDENT_TTL_S = 3.0          # how long a residency answer is trusted without re-asking
GEN_PATHS = ("/v1/chat/completions", "/v1/completions", "/v1/responses",
             "/v1/messages", "/v1/embeddings", "/chat/completions", "/completions")



def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


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

ASSET_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}\.(?:png|webp|jpe?g|mp4|webm)$")

# Internal calls must never go through a system proxy (http_proxy/HTTPS_PROXY
# would hijack 127.0.0.1 traffic on a box with a clash client running).
OPENER = urlrequest.build_opener(urlrequest.ProxyHandler({}))
