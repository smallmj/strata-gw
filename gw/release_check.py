"""release_check.py - are we behind? ask GitHub once an hour, whisper nothing
when the sky is dark. The console's yellow bar rides on this answer; there is
NO auto-update here - pulling the new version stays the master's double-click
(house rule: the long-running things belong to the master)."""
from __future__ import annotations

import json
import os
import re
import time
from urllib import request as urlrequest

from . import config
from . import console

_TTL_OK, _TTL_BAD = 3600.0, 300.0        # an answer, good or bad, is reused
_cache: dict = {"at": 0.0, "data": None}


def _api() -> str:
    """The probe URL comes ONLY from the env (tests, mirrors) or is derived
    from the configured repo URL - never from a request query (no SSRF door)."""
    u = os.environ.get("GW_RELEASE_API") or ""
    if u.startswith(("http://", "https://")):
        return u
    m = re.search(r"github\.com/([^/]+)/([^/]+)", console.github_url())
    if not m:
        return ""
    return "https://api.github.com/repos/%s/%s/releases/latest" % (m.group(1), m.group(2).rstrip("/"))


def _semver(t: str) -> tuple:
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", t or "")
    return tuple(int(x) for x in m.groups()) if m else ()


def check(timeout: float = 6.0) -> dict:
    """One honest look: reachable/latest/local/behind. behind=None whenever
    the comparison cannot be made honestly (offline, no clean tag)."""
    now = time.time()
    if _cache["data"] is not None:
        ttl = _TTL_OK if _cache["data"].get("reachable") else _TTL_BAD
        if now - _cache["at"] < ttl:
            return _cache["data"]
    url = _api()
    out: dict = {"reachable": False, "behind": None, "latest": None,
                 "local": console.version(), "url": None, "name": None}
    if url:
        try:
            rq = urlrequest.Request(url, headers={"User-Agent": "strata-gw",
                                                  "Accept": "application/vnd.github+json"})
            with config.OPENER.open(rq, timeout=timeout) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            latest = str(j.get("tag_name") or "").lstrip("v")
            out.update(reachable=True, latest=latest or None,
                       url=j.get("html_url"), name=j.get("name"))
            loc, rem = _semver(out["local"]), _semver(latest)
            if rem and loc:
                out["behind"] = rem > loc
        except (OSError, ValueError):
            pass                          # offline, rate-limited, nonsense: sleep on
    _cache.update(at=now, data=out)
    return out
