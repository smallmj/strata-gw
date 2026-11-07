"""setup_wizard.py - drive the Strata install tool (setup.py) from the console:
read its support list, run non-interactive recruits, stream the log, keep the
run history for 重新入册, run the PC check for the onboarding page, and report
disk usage (read-only; the gateway never deletes models - master's rule)."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import threading
import time
from collections import deque

from . import backends, config

_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")     # family/tier slugs, argv-safe

# Runs inside the STRATA venv (setup.py imports strata_control - only the
# engine's own python can read its lists). Constants-only import, verified
# side-effect-free on a live 0.2.x install (probe 2026-11-07).
PROBE = r'''
import sys, json
home = sys.argv[1]
sys.path.insert(0, home)
import setup as s
KEEP = {"title", "by", "about", "tag", "name", "vision"}
TKEEP = {"about", "download_gb", "ram_gb", "arena_gb", "families", "shards", "vision"}
def lite(d, keys):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = {kk: (list(vv) if isinstance(vv, (tuple, list, set, dict)) else vv)
                      for kk, vv in v.items() if kk in keys}
    return out
fams = lite(dict(s.FAMILIES), KEEP)
fams.update(lite(dict(s.PREVIEW_FAMILIES), KEEP))
for k, v in s.MULTI_FILE_FAMILIES.items():
    d = {kk: (list(vv) if isinstance(vv, (tuple, list)) else vv)
         for kk, vv in v.items() if kk in KEEP}
    d["tiers"] = lite(dict(v.get("models") or {}), {"about", "ram_gb", "label"})
    fams[k] = d
json.dump({"families": fams, "tiers": lite(dict(s.MODELS), TKEEP)},
          sys.stdout, ensure_ascii=False)
'''

_cache: dict = {"key": "", "cat": None}


def catalog() -> tuple[int, dict]:
    home = config.strata_home()
    py = config.resolve_python()
    setup_py = os.path.join(home, "setup.py")
    if not py or not os.path.isfile(setup_py):
        return 503, {"error": {"message":
            "Strata setup not found under %s - install Strata first, or point "
            "gateway.json \"strata_home\" at it (未找到 Strata 安装，请先装 Strata 引擎)" % home}}
    key = "%s|%s" % (setup_py, os.path.getmtime(setup_py))
    if _cache["key"] == key and _cache["cat"] is not None:
        return 200, _cache["cat"]
    try:
        r = subprocess.run([py, "-c", PROBE, home], capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return 503, {"error": {"message": "setup list probe failed: "
                                   + (r.stderr or r.stdout)[-300:]}}
        cat = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return 503, {"error": {"message": "setup list probe failed: %s" % e}}
    _cache.update(key=key, cat=cat)
    return 200, cat
