"""gpu_free.py - external VRAM card-handover ("\u8ba9\u5361").

Works against ANY image-generation service that exposes the /free +
/system_stats (+ optional /queue and /interrupt) API surface - the common
denominator among canvas-style generators. Nothing here names or hunts a
specific product: the gateway probes a configured URL list, politely asks
the holder to release its models, and (when forced) interrupts its queue
before waiting for the card to actually come back. We never kill processes
from the outside; nvidia-smi is used read-only for the water level.

Settings live in gateway.json under "gpu_free":
    {"urls": ["http://127.0.0.1:8188", "http://127.0.0.1:8189"],
     "target_mib": 0,        # 0 = auto: 0.85x the resident backend\'s gpu_mem_total
     "wait_s": 120,          # forced handover patience
     "gentle_wait_s": 8,     # the "free memory" button\'s evidence window
     "timeout_s": 10}        # per-request HTTP timeout
Env overrides: GW_GPU_URLS (comma list), GW_GPU_FREE_TARGET, GW_GPU_FREE_WAIT,
GW_GPU_FREE_TIMEOUT. The file is re-read per call (hot reload by design).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time

from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from . import config
from . import events

DEFAULT_PROBE = ("http://127.0.0.1:8188", "http://127.0.0.1:8189")
DEFAULT_WAIT_S = 120.0
DEFAULT_GENTLE_WAIT_S = 8.0
DEFAULT_TIMEOUT_S = 10.0


class CardNotFree(Exception):
    """The external holder was asked to free its models but has not given the
    card back within the wait window (a generation task usually has to finish
    first)."""


def settings() -> dict:
    sec = config.gateway_cfg().get("gpu_free")
    sec = sec if isinstance(sec, dict) else {}
    urls = sec.get("urls")
    if not isinstance(urls, list) or not urls:
        env = (config.env("GW_GPU_URLS", "") or "").strip()
        urls = [u.strip() for u in env.split(",") if u.strip()] if env else list(DEFAULT_PROBE)
    target = sec.get("target_mib")
    if not isinstance(target, int) or target < 0:
        target = int(config.env("GW_GPU_FREE_TARGET", "0") or 0)
    wait_s = sec.get("wait_s") if isinstance(sec.get("wait_s"), (int, float)) \
        else float(config.env("GW_GPU_FREE_WAIT", str(DEFAULT_WAIT_S)))
    gentle = sec.get("gentle_wait_s") if isinstance(sec.get("gentle_wait_s"), (int, float)) \
        else DEFAULT_GENTLE_WAIT_S
    timeout = sec.get("timeout_s") if isinstance(sec.get("timeout_s"), (int, float)) \
        else float(config.env("GW_GPU_FREE_TIMEOUT", str(DEFAULT_TIMEOUT_S)))
    return {"urls": [str(u) for u in urls], "target_mib": int(target),
            "wait_s": float(wait_s), "gentle_wait_s": float(gentle),
            "timeout_s": float(timeout)}


def _get(url: str, path: str, timeout: float):
    with config.OPENER.open(url + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _post(url: str, path: str, obj, timeout: float) -> bool:
    req = urlrequest.Request(url + path, method="POST",
                             headers={"Content-Type": "application/json"},
                             data=json.dumps(obj).encode())
    try:
        with config.OPENER.open(req, timeout=timeout):
            return True
    except (HTTPError, URLError, OSError):
        return False


def probe(url: str, timeout: float) -> dict | None:
    """VRAM/RAM as the holder itself reports them; None when unreachable."""
    try:
        data = _get(url, "/system_stats", timeout)
        dev = (data.get("devices") or [{}])[0]
        total = int(dev.get("vram_total") or 0) >> 20
        free = int(dev.get("vram_free") or 0) >> 20
        ram_used = int(((data.get("system") or {}).get("ram_used")) or 0) >> 20
        return {"vram_total_mib": total, "vram_used_mib": total - free,
                "vram_free_mib": free, "ram_used_mib": ram_used}
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        return None


def discover(st: dict):
    for url in st["urls"]:
        p = probe(url, st["timeout_s"])
        if p is not None:
            return url, p
    return None, None


def auto_target_mib():
    """0.85x the GPU memory the engine itself reports - the load that wants
    the card knows how much it needs; fall back to best effort when unreadable."""
    from . import backends
    b = backends.preferred_backend() or backends.default_backend()
    if b is None:
        return None
    try:
        with config.OPENER.open(f"{b.base}/metrics", timeout=5) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        total = int((d.get("hardware") or {}).get("gpu_mem_total") or 0)
        if total <= 0:
            return None
        return int(total * 0.85) >> 20
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        return None


def effective_target(st: dict):
    if st["target_mib"] > 0:
        return st["target_mib"]
    return auto_target_mib()


def nvidia_smi_mib():
    """(free, total) MiB from nvidia-smi, read-only; (None, None) when the
    tool is absent or unhappy. Never kills or interrupts anything."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None, None
    try:
        r = subprocess.run([exe, "--query-gpu=memory.free,memory.total",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=6)
        if r.returncode != 0:
            return None, None
        line = (r.stdout.strip().splitlines() or [""])[0]
        free_s, _, total_s = line.partition(",")
        return int(free_s.strip()), int(total_s.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None


_free_inflight: dict = {}     # release-in-flight {"op","since"}: spinners survive a refresh


def gpu_stats() -> dict:
    """Status for the console\'s external-VRAM strip (an in-flight release keeps
    the spinner honest across a page refresh)."""
    st = settings()
    out = {"running": False, "source": None, "vram_total_mib": None, "vram_free_mib": None,
           "free_target_mib": None, "auto_target_mib": None, "freeing": None}
    if _free_inflight:
        out["freeing"] = {"op": _free_inflight.get("op"),
                          "elapsed_s": int(time.time() - _free_inflight.get("since", time.time()))}
    url, p = discover(st)
    if p is not None:
        out.update({"running": True, "source": "external",
                    "vram_total_mib": p["vram_total_mib"] or None,
                    "vram_free_mib": p["vram_free_mib"]})
        out["free_target_mib"] = effective_target(st)
        if st["target_mib"] == 0:
            out["auto_target_mib"] = out["free_target_mib"]
        return out
    free, total = nvidia_smi_mib()
    if free is not None:
        out.update({"running": False, "source": "smi", "vram_total_mib": total or None,
                    "vram_free_mib": free})
    return out


def poke(st: dict) -> None:
    """Best-effort re-poke of /free without waiting (the retry loop\'s second
    nudge after another model\'s unload settles)."""
    url, _ = discover(st)
    if url:
        _post(url, "/free", {"unload_models": True, "free_memory": True}, st["timeout_s"])


def interrupt_and_clear(url: str, st: dict) -> int:
    """Forced release step one: drop queued items + interrupt the running one
    (the canvas cancel path). Returns the number of tasks touched."""
    pending: list = []
    running = 0
    try:
        q = _get(url, "/queue", st["timeout_s"])
        pending = [row[0] for row in (q.get("queue_pending") or [])
                   if isinstance(row, list) and row and row[0]]
        running = len(q.get("queue_running") or [])
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        pass
    if pending:
        _post(url, "/queue", {"delete": pending}, st["timeout_s"])
    _post(url, "/interrupt", {}, st["timeout_s"])
    return len(pending) + running


def ensure_card() -> bool:
    """Load-time gate: ask the holder to drop its models so the card is really
    free. /free sets flags the holder\'s prompt worker consumes at once when
    idle - but after a long task it has only set the flag; the unload (VRAM
    *and* model RAM) lands seconds later, or minutes later when a task is
    still running. So: best effort send, then wait for the card to actually
    come back. True = free to load; False = still held after wait_s. No
    holder = True (nothing to wait for); unreadable numbers = True (send best
    effort, do not block the load)."""
    st = settings()
    url, p = discover(st)
    if url is None:
        return True
    if _post(url, "/free", {"unload_models": True, "free_memory": True}, st["timeout_s"]):
        print("[router] asked the external holder to free its models", flush=True)
    else:
        print("[router] external /free skipped", flush=True)
        return True
    target = effective_target(st)
    if target is None:
        print("[router] no VRAM target readable; loading without the free-card wait", flush=True)
        return True
    p = probe(url, st["timeout_s"])
    if p is None:
        return True
    deadline = time.time() + st["wait_s"]
    while p is not None and p["vram_free_mib"] < target:
        if time.time() >= deadline:
            print("[router] the external holder has not given the card back in "
                  "{0:g} s ({1} MiB free, want {2}); "
                  "not loading".format(st["wait_s"], p["vram_free_mib"], target), flush=True)
            return False
        time.sleep(1.0)
        p = probe(url, st["timeout_s"])
    print("[router] the external holder gave the card back "
          "{0} MiB free".format((p or {}).get("vram_free_mib")), flush=True)
    return True


def free_console(force: bool):
    """The console\'s release buttons.
    Gentle  = canvas "free memory" semantics: only POST /free, poll up to
              gentle_wait_s, accept a real >=256 MiB drop as evidence; give up
              early when the numbers sit still twice. Never interrupts a run.
    Forced  = interrupt + clear the queue first, then /free, using the same
              wait window and water line as the load gate.
    None when no external holder answers."""
    st = settings()
    url, before = discover(st)
    if url is None or before is None:
        return None
    t0 = time.time()
    _free_inflight["op"] = "force" if force else "gentle"
    _free_inflight["since"] = t0
    try:
        cleared = interrupt_and_clear(url, st) if force else 0
        _post(url, "/free", {"unload_models": True, "free_memory": True}, st["timeout_s"])
        after = before
        last = before["vram_used_mib"]
        stable = 0
        while time.time() - t0 < (st["wait_s"] if force else st["gentle_wait_s"]):
            time.sleep(0.3)
            p2 = probe(url, st["timeout_s"])
            if p2 is None:
                break
            after = p2
            if force:
                tgt = effective_target(st) or before["vram_free_mib"]
                if after["vram_free_mib"] >= tgt:
                    break
            else:
                if before["vram_used_mib"] - after["vram_used_mib"] >= 256:
                    break               # the "freed" evidence
                stable = stable + 1 if abs(after["vram_used_mib"] - last) <= 8 else 0
                last = after["vram_used_mib"]
                if stable >= 2 and time.time() - t0 >= 0.9:
                    break               # numbers sat twice: nothing is coming, stop early
    finally:
        _free_inflight.clear()
    tgt = effective_target(st) or 0
    freed_gb = max(0, before["vram_used_mib"] - after["vram_used_mib"]) / 1024.0
    gave = after["vram_free_mib"] >= tgt
    events.revent("gpu", ("force" if force else "gentle") + " free: " +
                  "%.1f GB \u663e\u5b58\u5df2\u91ca\u653e\uff0c\u7528\u65f6 %d \u79d2" % (freed_gb, int(time.time() - t0)) +
                  ("\uff0c\u663e\u5361\u5df2\u8ba9\u51fa" if gave else "\uff0c\u5c1a\u672a\u8ba9\u51fa") +
                  ("\uff08\u6e05\u6389 %d \u4e2a\u4efb\u52a1\uff09" % cleared if force and cleared else ""))
    return {"ok": True, "force": force,
            "freed_vram_mib": max(0, before["vram_used_mib"] - after["vram_used_mib"]),
            "freed_ram_mib": max(0, before["ram_used_mib"] - after["ram_used_mib"]),
            "waited_s": int(time.time() - t0),
            "tasks_cleared": cleared if force else 0,
            "gave_card": gave}
