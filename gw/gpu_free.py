"""gpu_free.py - external VRAM card-handover ("让卡") against any image-generation
service exposing the /free + /system_stats + /queue + /interrupt API surface.

The original deployment drove one particular canvas service; everything here is
generic: probe reports, gentle vs forced release, and the load-time wait until
the card actually comes back. Nothing kills processes from the outside; we only
ask the holder politely (or interrupt its queue when forced).
"""
from __future__ import annotations

import json
import time

from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from . import config
from . import events


class ComfyNotFree(Exception):
    """The external VRAM holder was asked to free its models but has not given
    the card back within the wait window (a generation task usually has to
    finish first)."""


def comfy_vram_free_mib() -> int | None:
    """Global free VRAM as the holder itself sees it (torch mem_get_info via
    /system_stats); None when unreadable."""
    try:
        with config.OPENER.open(f"{config.COMFY_URL}/system_stats",
                                timeout=config.COMFY_FREE_TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        devs = data.get("devices") or []
        if not devs:
            return None
        v = devs[0].get("vram_free")
        return None if v is None else int(int(v) >> 20)
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        return None


def comfy_unload(wait: bool = True) -> bool:
    """Ask a running holder to drop its models so the card is really free.
    /free sets flags the prompt worker consumes at once when idle (the idle
    worker's get() wakes on set_flag's notify) - but after a long task it has
    only set the flag; the unload (VRAM *and* the model's RAM) lands seconds
    later, or minutes later when a task is still running. So: best effort
    send, then wait for the card to actually come back (the canvas 'free
    memory' button blocks exactly the same way, which is why freeing by hand
    first makes a model load fast again). True = free to load; False = the
    holder still has the card after COMFY_FREE_WAIT_S."""
    try:
        req = urlrequest.Request(
            f"{config.COMFY_URL}/free", method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"unload_models": True, "free_memory": True}).encode())
        with config.OPENER.open(req, timeout=config.COMFY_FREE_TIMEOUT_S):
            print("[router] asked the external holder to free its models", flush=True)
    except (HTTPError, URLError, OSError) as e:
        print(f"[router] external /free skipped: {e}", flush=True)
        return True                      # nothing running there: nothing to wait for
    if not wait:
        return True
    free = comfy_vram_free_mib()
    if free is None:
        print("[router] external VRAM is unreadable; loading without the free-card wait",
              flush=True)
        return True
    deadline = time.time() + config.COMFY_FREE_WAIT_S
    while free is not None and free < config.COMFY_FREE_TARGET_MIB:
        if time.time() >= deadline:
            print(f"[router] the external holder has not given the card back in "
                  f"{config.COMFY_FREE_WAIT_S:g} s ({free} MiB free, want "
                  f"{config.COMFY_FREE_TARGET_MIB}); not loading", flush=True)
            return False
        time.sleep(1.0)
        free = comfy_vram_free_mib()
    print(f"[router] the external holder gave the card back ({free} MiB free)", flush=True)
    return True


GENTLE_FREE_WAIT_S = 8.0      # the canvas button's evidence window; force uses COMFY_FREE_WAIT_S


def _comfy_probe() -> dict | None:
    """VRAM/RAM as the holder itself reports it; None when unreachable."""
    try:
        with config.OPENER.open(f"{config.COMFY_URL}/system_stats",
                                timeout=config.COMFY_FREE_TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        dev = (data.get("devices") or [{}])[0]
        total = int(dev.get("vram_total") or 0) >> 20
        free = int(dev.get("vram_free") or 0) >> 20
        ram_used = int(((data.get("system") or {}).get("ram_used")) or 0) >> 20
        return {"vram_total_mib": total, "vram_used_mib": total - free,
                "vram_free_mib": free, "ram_used_mib": ram_used}
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        return None


def comfy_stats() -> dict:
    """网关页外部显存状态条数据（含清理进行态：刷新页面也能接着转圈）。"""
    out = {"running": False, "vram_total_mib": None, "vram_free_mib": None,
           "free_target_mib": config.COMFY_FREE_TARGET_MIB, "freeing": None}
    if _comfy_free:
        out["freeing"] = {"op": _comfy_free.get("op"),
                          "elapsed_s": int(time.time() - _comfy_free.get("since", time.time()))}
    p = _comfy_probe()
    if p is not None:
        out.update({"running": True, "vram_total_mib": p["vram_total_mib"] or None,
                    "vram_free_mib": p["vram_free_mib"]})
    return out


def comfy_interrupt_and_clear() -> int:
    """强制清理第一步：清空排队项 + 打断正在跑的任务（出图服务核心 API，
    和画布网关的 cancel 路径同款）。返回动过的任务数。"""
    pending: list = []
    running = 0
    try:
        with config.OPENER.open(f"{config.COMFY_URL}/queue",
                                timeout=config.COMFY_FREE_TIMEOUT_S) as r:
            q = json.loads(r.read().decode("utf-8", "replace"))
        pending = [row[0] for row in (q.get("queue_pending") or [])
                   if isinstance(row, list) and row and row[0]]
        running = len(q.get("queue_running") or [])
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        pass
    if pending:
        try:
            req = urlrequest.Request(f"{config.COMFY_URL}/queue", method="POST",
                                     headers={"Content-Type": "application/json"},
                                     data=json.dumps({"delete": pending}).encode())
            with config.OPENER.open(req, timeout=config.COMFY_FREE_TIMEOUT_S):
                pass
        except (HTTPError, URLError, OSError):
            pass
    try:
        req = urlrequest.Request(f"{config.COMFY_URL}/interrupt", method="POST",
                                 headers={"Content-Type": "application/json"}, data=b"{}")
        with config.OPENER.open(req, timeout=config.COMFY_FREE_TIMEOUT_S):
            pass
    except (HTTPError, URLError, OSError):
        pass
    return len(pending) + running


_comfy_free: dict = {}        # 控制台清理进行态 {"op","since"}：按钮转圈以它为准


def comfy_free_console(force: bool) -> dict | None:
    """控制台的「清理显存」按钮。
    温和 = 画布同款语义: 只 POST /free，轮询最多 GENTLE_FREE_WAIT_S，看显存读数是否真降
    （≥256 MiB 即认账；读数纹丝不动两次就提前收手，别白等）；绝不打断在跑的任务。
    强制 = 先 interrupt + 清队列，再 /free，用和 Load 放卡同一个等待窗与水位
    （COMFY_FREE_WAIT_S / COMFY_FREE_TARGET_MIB）确证卡已让出。None = 外部服务不可达。"""
    before = _comfy_probe()
    if before is None:
        return None
    t0 = time.time()
    _comfy_free["op"] = "force" if force else "gentle"
    _comfy_free["since"] = t0
    try:
        cleared = comfy_interrupt_and_clear() if force else 0
        try:
            req = urlrequest.Request(f"{config.COMFY_URL}/free", method="POST",
                                     headers={"Content-Type": "application/json"},
                                     data=json.dumps({"unload_models": True,
                                                      "free_memory": True}).encode())
            with config.OPENER.open(req, timeout=config.COMFY_FREE_TIMEOUT_S):
                pass
        except (HTTPError, URLError, OSError):
            pass                        # best effort; the measuring loop below judges anyway
        after = before
        last = before["vram_used_mib"]
        stable = 0
        while time.time() - t0 < (config.COMFY_FREE_WAIT_S if force else GENTLE_FREE_WAIT_S):
            time.sleep(0.3)
            probe = _comfy_probe()
            if probe is None:
                break
            after = probe
            if force:
                if after["vram_free_mib"] >= config.COMFY_FREE_TARGET_MIB:
                    break
            else:
                if before["vram_used_mib"] - after["vram_used_mib"] >= 256:
                    break               # the canvas button's 'freed' evidence
                stable = stable + 1 if abs(after["vram_used_mib"] - last) <= 8 else 0
                last = after["vram_used_mib"]
                if stable >= 2 and time.time() - t0 >= 0.9:
                    break               # numbers moved twice: nothing is coming, stop early
    finally:
        _comfy_free.clear()
    freed_gb = max(0, before["vram_used_mib"] - after["vram_used_mib"]) / 1024.0
    gave = after["vram_free_mib"] >= config.COMFY_FREE_TARGET_MIB
    events.revent("comfy", ("force" if force else "gentle") + " free: " +
                  "%.1f GB 显存已释放，用时 %d 秒" % (freed_gb, int(time.time() - t0)) +
                  ("，显卡已让出" if gave else "，尚未让出") +
                  ("（清掉 %d 个任务）" % cleared if force and cleared else ""))
    return {"ok": True, "force": force,
            "freed_vram_mib": max(0, before["vram_used_mib"] - after["vram_used_mib"]),
            "freed_ram_mib": max(0, before["ram_used_mib"] - after["ram_used_mib"]),
            "waited_s": int(time.time() - t0),
            "tasks_cleared": cleared if force else 0,
            "gave_card": gave}
