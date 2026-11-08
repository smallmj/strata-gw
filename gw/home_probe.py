"""Locate the Strata engine root - auto-probe or manual pointer.

The gateway can live anywhere; what matters is finding the Strata install.
A directory is trusted by SHAPE, never by name: setup.py at the top level
plus serve/server.py (engine layout) or an engine/ folder (embedded layout).
Candidates come from GW_HOME_CANDIDATES (";"-joined, test/ops override), the
common install places, the sibling of the gateway checkout, and finally the
checkout itself (the production layout keeps the gateway inside the engine).

set_home() persists the choice into gateway.json - read hot on every call,
so the adopt takes effect without a restart - and never drops other keys.
"""
from __future__ import annotations

import json
import os

from . import config


def looks_like_strata(d: str | None) -> bool:
    """Shape test: real engine installs pass, empty name-matching folders fail."""
    if not d or not os.path.isdir(d):
        return False
    if not os.path.isfile(os.path.join(d, "setup.py")):
        return False
    return (os.path.isfile(os.path.join(d, "serve", "server.py"))
            or os.path.isdir(os.path.join(d, "engine")))


def candidates() -> list:
    out: list = []
    env_c = config.env("GW_HOME_CANDIDATES")
    if env_c:
        out = [x.strip() for x in env_c.split(";") if x.strip()]
    else:
        e = os.environ
        base: list = []
        for drv in ("C:", "D:", "E:", "F:"):          # Windows drive roots
            base.append(drv + os.sep + "Strata")
        for key in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)",
                    "USERPROFILE", "HOME"):           # per-user / system installs
            v = e.get(key)
            if v:
                base += [os.path.join(v, "Strata"), os.path.join(v, "Programs", "Strata")]
        base.append("/opt/Strata")
        # the gateway cloned right next to the engine is the common OSS layout
        base.append(os.path.join(os.path.dirname(config.ROOT), "Strata"))
        out = [b for b in base if os.path.isdir(b)]
    # the checkout itself may BE the engine root (production layout) - last
    out.append(config.ROOT)
    seen: list = []
    for p in out:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.append(ap)
    return seen


def probe() -> dict:
    c = [{"path": p, "valid": looks_like_strata(p)} for p in candidates()]
    auto = next((c0["path"] for c0 in c if c0["valid"]), None)
    return {"candidates": c, "auto": auto}


def current() -> dict:
    h = config.strata_home()
    if config.env("STRATA_HOME"):
        src = "env"
    elif str(config.gateway_cfg().get("strata_home") or ""):
        src = "gateway.json"
    else:
        src = "root"
    return {"home": h, "source": src, "valid": looks_like_strata(h)}


def set_home(path: str) -> str | None:
    """Validate then persist. Returns the stored absolute path, or None when
    the folder is not an engine (nothing is written in that case)."""
    if not looks_like_strata(path):
        return None
    ap = os.path.abspath(path)
    gj = os.path.join(config.ROOT, "gateway.json")
    data: dict = {}
    if os.path.isfile(gj):
        try:
            with open(gj, encoding="utf-8-sig") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            return None          # a corrupt gateway.json must not be steamrolled
    data["strata_home"] = ap
    tmp = gj + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, gj)
    return ap
