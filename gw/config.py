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
TESTED_UP_TO = {"engine": "0.1.65", "strata": "v0.2.19"}

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


# ---- engine source -----------------------------------------------------------------------
# How a backend picks its engine binary. "config" (the default): the scanned
# run config's own "exe" path, byte for byte what setup.py wrote. "component":
# the spawn hands server.py the upstream component reference instead
# ("component:strata-engine"; serve/server_parts/http_api.with_component_engine
# resolves it), so the engine comes from the component store the desktop app
# and Control maintain - newest installed package, a manual rollback pin
# honored, the signature and every file's SHA-256 verified at start. The
# scanned JSONs stay read-only in both modes; everything but "exe" is
# inherited untouched.
ENGINE_SOURCE_CONFIG = "config"
ENGINE_SOURCE_COMPONENT = "component"
COMPONENT_REFERENCE = "component:strata-engine"
COMPONENT_MANIFEST = "engine-component.json"


def engine_source() -> str:
    """env STRATA_ENGINE_SOURCE > gateway.json "engine_source" > "config".
    Anything but "component" falls back to "config" (the scanned paths win)."""
    raw = (env("STRATA_ENGINE_SOURCE") or str(gateway_cfg().get("engine_source") or "")).strip()
    return raw if raw == ENGINE_SOURCE_COMPONENT else ENGINE_SOURCE_CONFIG


def components_dir() -> str:
    """The per-user component store, mirroring
    strata_control.engine_component.components_dir(): STRATA_COMPONENTS_DIR
    wins (the app and the tests set it), else the OS default."""
    d = env("STRATA_COMPONENTS_DIR")
    if d:
        return d
    if os.name == "nt":
        base = env("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "Strata", "components")
    xdg = env("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(xdg, "strata", "components")


def _component_version_key(value) -> tuple:
    """The same ordering engine_component uses: numeric parts compare as ints."""
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-+]", str(value)))


def component_engine_dir() -> str | None:
    """The package folder a component start would use, at display resolution:
    the pinned folder when the store's state file names one, else the newest
    installed. The AUTHORITATIVE resolution (platform, backend, GPU arch,
    driver floor, signature, integrity) happens in server.py at spawn; this
    only picks the folder for the version stamp and the picture reader's
    path. None when the store holds nothing readable."""
    eng = os.path.join(components_dir(), "engine")
    if not os.path.isdir(eng):
        return None
    best = None
    for name in os.listdir(eng):
        folder = os.path.join(eng, name)
        manifest = os.path.join(folder, COMPONENT_MANIFEST)
        if not os.path.isfile(manifest):
            continue
        try:
            with open(manifest, encoding="utf-8-sig") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or not meta.get("version"):
            continue
        if best is None or _component_version_key(meta["version"]) > _component_version_key(best[1]["version"]):
            best = (folder, meta)
    pin = None
    try:
        with open(os.path.join(components_dir(), ".updates", "state.json"), encoding="utf-8-sig") as f:
            pin = ((json.load(f) or {}).get("engine") or {}).get("pinned")
    except (OSError, ValueError, AttributeError):
        pin = None
    if isinstance(pin, str) and pin and "/" not in pin and "\\" not in pin \
            and os.path.isfile(os.path.join(eng, pin, COMPONENT_MANIFEST)):
        return os.path.join(eng, pin)
    return best[0] if best else None


def engine_stamp() -> dict | None:
    """The engine BUILD.json the gateway presents. With engine_source
    "component", the in-use package's own stamp (its manifest's version when
    the package ships no BUILD.json); otherwise the install's, newest layout
    first (terminal/engine/, engine/, top level). None when neither exists."""
    if engine_source() == ENGINE_SOURCE_COMPONENT:
        d = component_engine_dir()
        if not d:
            return None
        for name, pick in (("BUILD.json", True), (COMPONENT_MANIFEST, False)):
            try:
                with open(os.path.join(d, name), encoding="utf-8-sig") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(meta, dict) and (meta.get("version") or not pick):
                return meta if meta.get("version") else None
        return None
    for cand in ("terminal/engine/BUILD.json", "engine/BUILD.json", "BUILD.json"):
        p = os.path.join(strata_home(), cand)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8-sig") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None
    return None

WATCH_S = float(os.environ.get("STRATA_WATCH_S", "20"))   # state-transition watcher

PROXY_PATHS = ("/router/settings", "/router/config", "/router/mcp", "/router/status",
               "/router/metrics", "/router/props", "/router/slots")   # mirrored to the page

ASSET_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}\.(?:png|webp|jpe?g|mp4|webm|woff2)$")

# Internal calls must never go through a system proxy (http_proxy/HTTPS_PROXY
# would hijack 127.0.0.1 traffic on a box with a clash client running).
OPENER = urlrequest.build_opener(urlrequest.ProxyHandler({}))
