#!/usr/bin/env python3
"""strata-router.py - Strata multi-model gateway (port 18080).

Scans strata-*.json in its own directory, spawns one lazy backend
(`server.py --engine strata --config <json> --lazy`) per config on its own
port (18081+), aggregates GET /v1/models over all backends, and routes every
generation request by the "model" field of its JSON body. Before a backend
loads (it was unloaded), the router unloads the other backends first, so two
models never share the machine. A 503 "GPU is in use" from a backend is
retried for a while: the other model's unload may still be in flight.
Requests that carry no model field (the web UI above all) follow the
currently resident model, so its About/Monitor pages describe the engine
that is actually running.

Adding a model: let setup write its strata-<model>.json here, then restart
the gateway (strata.cmd). Nothing else to register; /v1/models picks it up.
Stdlib only.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from collections import deque

from gw import console

ROOT = os.path.dirname(os.path.abspath(__file__))
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
COMFY_URL = os.environ.get("STRATA_COMFY_URL", "http://127.0.0.1:8188")
COMFY_FREE_TIMEOUT_S = float(os.environ.get("STRATA_COMFY_FREE_TIMEOUT", "10"))
COMFY_FREE_TARGET_MIB = int(os.environ.get("STRATA_COMFY_FREE_TARGET", "20500"))
COMFY_FREE_WAIT_S = float(os.environ.get("STRATA_COMFY_FREE_WAIT", "120"))
WATCH_S = float(os.environ.get("STRATA_WATCH_S", "20"))   # state-transition watcher
PROXY_PATHS = ("/router/settings", "/router/config", "/router/mcp", "/router/status",
               "/router/metrics", "/router/props", "/router/slots")   # mirrored to the page

_lock = threading.Lock()                      # guards BACKENDS and port state
_spawn_locks: dict[str, threading.Lock] = {}  # one spawn at a time per config

# Internal calls must never go through a system proxy (http_proxy/HTTPS_PROXY
# would hijack 127.0.0.1 traffic on a box with a clash client running).
OPENER = urlrequest.build_opener(urlrequest.ProxyHandler({}))


class _Tee:
    """Mirror every print() into an in-memory ring so /router/log can stream the
    gateway console to the web page. Backend subprocesses write to the shared
    console through their own OS handles, not through us: they stay out of this
    ring - it is the router's own voice."""
    def __init__(self, stream) -> None:
        self.stream, self.partial = stream, ""

    def write(self, s):
        self.stream.write(s)
        self.partial += s
        while "\n" in self.partial:
            line, self.partial = self.partial.split("\n", 1)
            if line.strip():
                _LOG.append((time.time(), line))
        return len(s)

    def flush(self):
        self.stream.flush()


_LOG: deque = deque(maxlen=500)         # (epoch, line) for /router/log
_EVENTS: deque = deque(maxlen=120)     # (epoch, kind, text) for the console timeline
_intent: dict = {}                     # name -> epoch: a transition the router caused


def revent(kind: str, text: str) -> None:
    _EVENTS.append((time.time(), kind, text))


def note_intentional(name: str) -> None:
    _intent[name] = time.time()


def _watchdog() -> None:
    """Record state moves the router did NOT cause - the engine's own idle timer,
    or the ComfyUI bridge unloading it - on the timeline. Moves we made in the
    last 10 s are already logged, so they are skipped here."""
    last: dict[str, bool] = {}
    while True:
        time.sleep(WATCH_S)
        try:
            for b in list(BACKENDS.values()):
                r = b.alive() and b.resident() is True
                prev = last.get(b.name, False)
                if prev and not r and time.time() - _intent.get(b.name, 0.0) > 10.0:
                    revent("unload", f"{b.name} left the GPU on its own (idle timer or the ComfyUI bridge)")
                elif r and not prev and time.time() - _intent.get(b.name, 0.0) > 10.0:
                    revent("load", f"{b.name} became resident")
                last[b.name] = r
        except Exception:
            pass


_APPVER: dict = {}


def app_version() -> dict:
    """The Strata checkout's own tag, read once per gateway start."""
    if _APPVER:
        return _APPVER
    out = {}
    try:
        r = subprocess.run(["git", "-C", ROOT, "describe", "--tags"],
                           capture_output=True, text=True, timeout=6)
        if r.returncode == 0:
            out["version"] = r.stdout.strip().lstrip("v")
        r = subprocess.run(["git", "-C", ROOT, "log", "-1", "--format=%h"],
                           capture_output=True, text=True, timeout=6)
        if r.returncode == 0:
            out["commit"] = r.stdout.strip()
    except (OSError, ValueError):
        pass
    if not out.get("version"):
        # no git: fall back to the checkout's CMakeLists project version
        try:
            with open(os.path.join(ROOT, "CMakeLists.txt"), encoding="utf-8-sig") as f:
                m = re.search(r"project\(strata\s+VERSION\s+([0-9.]+)", f.read())
                if m:
                    out["version"] = m.group(1)
        except OSError:
            pass
    _APPVER.update(out)
    return _APPVER


def router_info() -> dict:
    """/router/info: the engine BUILD.json plus a per-backend /health snapshot."""
    build = None
    for cand in ("engine/BUILD.json", "BUILD.json"):
        p = os.path.join(ROOT, cand)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8-sig") as f:
                    build = json.load(f)
            except (OSError, ValueError):
                build = None
            break
    models = {}
    for b in sorted(BACKENDS.values(), key=lambda x: x.name):
        try:
            with OPENER.open(b.base + "/health", timeout=5) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            models[b.name] = {"alive": True, "max_context": d.get("max_context"),
                              "images": d.get("images"), "loaded": d.get("loaded"),
                              "image_generation": d.get("image_generation")}
        except (HTTPError, URLError, OSError, ValueError):
            models[b.name] = {"alive": False}
    return {"build": build, "app": app_version(), "models": models, "port": ROUTER_PORT,
            "comfy_free_target_mib": COMFY_FREE_TARGET_MIB}


ASSET_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}\.(?:png|webp|jpe?g|mp4|webm)$")

sys.stdout = _Tee(sys.stdout)


WATCH_JS = ('<script>/*strataGatewayWatch*/'
            '(function(){var n=0;'
            'setInterval(function(){'
            'fetch("/router/backends").then(function(r){return r.json()}).then(function(d){'
            'var any=(d.backends||[]).some(function(b){return b.loaded});'
            'if(!any){n++}else{n=0}'
            'if(n>=2){location.replace("/gateway")}'
            '}).catch(function(){})'
            '},2000);})();</script>')


# The console page now lives in console/ static files; gw/console.py assembles it.


class Backend:
    def __init__(self, cfg_path: str, cfg: dict, port: int):
        self.cfg_path = cfg_path
        self.name = cfg.get("model_name") or os.path.basename(cfg_path)
        self.aliases = [a for a in (cfg.get("aliases") or []) if isinstance(a, str)]
        self.key = cfg.get("api_key", "")
        self.port = port
        self.last_spawn = 0.0
        self.proc: subprocess.Popen | None = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def matches(self, model: str) -> bool:
        return model in (self.name, *self.aliases)

    def alive(self) -> bool:
        try:
            with OPENER.open(f"{self.base}/health", timeout=3):
                return True
        except HTTPError as e:
            return e.code in (401, 403)          # the API is up; it only wants the key
        except (URLError, OSError):
            return False

    def resident(self) -> bool | None:
        """True/False: is the model loaded; None: the backend is down or slow."""
        try:
            req = urlrequest.Request(
                f"{self.base}/v1/models",
                headers={"Authorization": f"Bearer {self.key}"} if self.key else {})
            with OPENER.open(req, timeout=5) as r:
                data = (json.loads(r.read() or b"{}") or {}).get("data") or []
        except (URLError, OSError, ValueError):
            return None
        for m in data:
            if m.get("id") == self.name:
                return ((m.get("status") or {}).get("value")) == "loaded"
        return False

    def spawn(self) -> None:
        lock = _spawn_locks.setdefault(self.cfg_path, threading.Lock())
        if not lock.acquire(blocking=False):
            return                               # another thread is spawning it
        try:
            if self.alive():
                return
            if time.time() - self.last_spawn < SPAWN_COOLDOWN_S:
                return
            self.last_spawn = time.time()
            if not os.path.isfile(PYTHON) or not os.path.isfile(SERVER_PY):
                print(f"[router] cannot spawn {self.name}: python/server.py missing", flush=True)
                return
            # Foreground child: the backend shares this console, so its startup
            # narrator and [strata] lines stream into the same window as the
            # router's. winjob.contain ties it (and its engine, vision encoder,
            # everything it starts later) to this process's lifetime: whatever
            # ends the router - Ctrl+C, the window's X, taskkill, a crash - the
            # job's kill-on-close takes the whole tree with it.
            self.proc = subprocess.Popen(
                [PYTHON, SERVER_PY, "--engine", "strata", "--config", self.cfg_path,
                 "--host", "0.0.0.0", "--port", str(self.port),
                 "--api-key", self.key, "--lazy"],
                cwd=ROOT, stdin=subprocess.DEVNULL)
            try:
                from serve import winjob
                winjob.contain(self.proc)
            except Exception:
                pass
            print(f"[router] spawned {self.name} on :{self.port} (lazy)", flush=True)
            revent("backend", f"{self.name} backend process started on :{self.port}")
        finally:
            lock.release()

    def wait_alive(self, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.alive():
                return True
            time.sleep(2.0)
        return False

    def unload(self, timeout: float = 60.0) -> None:
        """Best effort: stop the engine to free RAM/VRAM. busy (409) is fine here:
        the load's own min_free_vram check + the router's retry catch it."""
        try:
            req = urlrequest.Request(
                f"{self.base}/unload", method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.key}"}, data=b"{}")
            with OPENER.open(req, timeout=timeout) as r:
                print(f"[router] unload {self.name}: {r.status} {r.read()[:120]!r}", flush=True)
        except HTTPError as e:
            print(f"[router] unload {self.name}: HTTP {e.code}", flush=True)
        except (URLError, OSError) as e:
            print(f"[router] unload {self.name}: {e}", flush=True)
        invalidate_resident()
        note_intentional(self.name)


def scan_configs() -> dict[str, Backend]:
    """strata-*.json next to this file -> backends. Ports: a config's own port
    (when it is not the router's) wins, else the saved mapping, else the next
    free 1808x. The mapping is persisted so restarts keep the same ports."""
    saved: dict[str, int] = {}
    try:
        with open(PORTS_FILE, encoding="utf-8") as f:
            saved = {k: int(v) for k, v in (json.load(f) or {}).items()}
    except (OSError, ValueError):
        pass
    taken = {ROUTER_PORT}
    backends: dict[str, Backend] = {}
    entries = []
    for path in sorted(glob.glob(os.path.join(ROOT, "strata-*.json"))):
        base = os.path.basename(path)
        if re.search(r"\.bak|\.tmp|\.log", base):
            continue
        try:
            with open(path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict) or not cfg.get("model_name"):
                continue
        except (OSError, ValueError) as e:
            print(f"[router] skipping {base}: {e}", flush=True)
            continue
        entries.append((path, cfg))
    for path, cfg in sorted(entries, key=lambda x: x[1]["model_name"]):
        name = cfg["model_name"]
        port = saved.get(name)
        own = cfg.get("port")
        if not port and isinstance(own, int) and own not in taken and own != ROUTER_PORT:
            port = own
        if not port:
            port = FIRST_BACKEND_PORT
            while port in taken:
                port += 1
        taken.add(port)
        backends[path] = Backend(path, cfg, port)
    with _lock:
        new_saved = {b.name: b.port for b in backends.values()}
        if new_saved != saved:
            try:
                with open(PORTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(new_saved, f, indent=1)
            except OSError as e:
                print(f"[router] cannot save {PORTS_FILE}: {e}", flush=True)
    return backends


BACKENDS: dict[str, Backend] = {}


_resident_cache: dict[str, tuple[float, bool | None]] = {}


def resident_of(b: "Backend") -> bool | None:
    """b.resident() with a short cache: the webUI polls /metrics every second,
    and each answer costs a backend round trip."""
    now = time.monotonic()
    hit = _resident_cache.get(b.cfg_path)
    if hit is not None and now - hit[0] < RESIDENT_TTL_S:
        return hit[1]
    r = b.resident()
    _resident_cache[b.cfg_path] = (now, r)
    return r


class ComfyNotFree(Exception):
    """ComfyUI was asked to free its models but has not given the card back
    within the wait window (a generation task usually has to finish first)."""


def comfy_vram_free_mib() -> int | None:
    """Global free VRAM as ComfyUI itself sees it (torch mem_get_info via
    /system_stats); None when unreadable."""
    try:
        with OPENER.open(f"{COMFY_URL}/system_stats", timeout=COMFY_FREE_TIMEOUT_S) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        devs = data.get("devices") or []
        if not devs:
            return None
        v = devs[0].get("vram_free")
        return None if v is None else int(int(v) >> 20)
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        return None


def comfy_unload(wait: bool = True) -> bool:
    """Ask a running ComfyUI to drop its models so the card is really free.
    /free sets flags ComfyUI's prompt worker consumes at once when idle (the
    idle worker's get() wakes on set_flag's notify) - but after a long task it
    has only set the flag; the unload (VRAM *and* the model's RAM) lands
    seconds later, or minutes later when a task is still running. So: best
    effort send, then wait for the card to actually come back (the canvas
    'free memory' button blocks exactly the same way, which is why freeing by
    hand first makes a Strata load fast again). True = free to load;
    False = ComfyUI still holds the card after COMFY_FREE_WAIT_S."""
    try:
        req = urlrequest.Request(
            f"{COMFY_URL}/free", method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"unload_models": True, "free_memory": True}).encode())
        with OPENER.open(req, timeout=COMFY_FREE_TIMEOUT_S):
            print("[router] asked ComfyUI to free its models", flush=True)
    except (HTTPError, URLError, OSError) as e:
        print(f"[router] ComfyUI /free skipped: {e}", flush=True)
        return True                      # no ComfyUI running: nothing to wait for
    if not wait:
        return True
    free = comfy_vram_free_mib()
    if free is None:
        print("[router] ComfyUI VRAM is unreadable; loading without the free-card wait",
              flush=True)
        return True
    deadline = time.time() + COMFY_FREE_WAIT_S
    while free is not None and free < COMFY_FREE_TARGET_MIB:
        if time.time() >= deadline:
            print(f"[router] ComfyUI has not given the card back in {COMFY_FREE_WAIT_S:g} s "
                  f"({free} MiB free, want {COMFY_FREE_TARGET_MIB}); not loading", flush=True)
            return False
        time.sleep(1.0)
        free = comfy_vram_free_mib()
    print(f"[router] ComfyUI gave the card back ({free} MiB free)", flush=True)
    return True


_preferred: dict = {"name": None}       # 最近一次用户点名加载/卸载的模型（粘性）


def invalidate_resident() -> None:
    """状态刚被改变（load/unload/换装）: 丢掉 3s 驻留缓存，让跟随即时生效。"""
    _resident_cache.clear()


def set_preferred(name: str | None) -> None:
    if _preferred["name"] != name:
        _preferred["name"] = name
        print(f"[router] preferred model: {name}", flush=True)
        revent("switch", "preferred model: " + str(name))


def preferred_backend() -> "Backend | None":
    name = _preferred["name"]
    if not name:
        return None
    return next((b for b in BACKENDS.values() if b.name == name), None)


def any_resident() -> bool:
    return any(resident_of(b) is True for b in BACKENDS.values())


GENTLE_FREE_WAIT_S = 8.0      # the canvas button's evidence window; force uses COMFY_FREE_WAIT_S


def _comfy_probe() -> "dict | None":
    """VRAM/RAM as ComfyUI itself reports it; None when unreachable."""
    try:
        with OPENER.open(f"{COMFY_URL}/system_stats", timeout=COMFY_FREE_TIMEOUT_S) as r:
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
    """网关页 ComfyUI 状态条数据（含清理进行态：刷新页面也能接着转圈）。"""
    out = {"running": False, "vram_total_mib": None, "vram_free_mib": None,
           "free_target_mib": COMFY_FREE_TARGET_MIB, "freeing": None}
    if _comfy_free:
        out["freeing"] = {"op": _comfy_free.get("op"),
                          "elapsed_s": int(time.time() - _comfy_free.get("since", time.time()))}
    p = _comfy_probe()
    if p is not None:
        out.update({"running": True, "vram_total_mib": p["vram_total_mib"] or None,
                    "vram_free_mib": p["vram_free_mib"]})
    return out


def comfy_interrupt_and_clear() -> int:
    """强制清理第一步：清空排队项 + 打断正在跑的任务（ComfyUI 核心 API，
    和画布网关的 cancel 路径同款）。返回动过的任务数。"""
    pending: list = []
    running = 0
    try:
        with OPENER.open(f"{COMFY_URL}/queue", timeout=COMFY_FREE_TIMEOUT_S) as r:
            q = json.loads(r.read().decode("utf-8", "replace"))
        pending = [row[0] for row in (q.get("queue_pending") or [])
                   if isinstance(row, list) and row and row[0]]
        running = len(q.get("queue_running") or [])
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        pass
    if pending:
        try:
            req = urlrequest.Request(f"{COMFY_URL}/queue", method="POST",
                                     headers={"Content-Type": "application/json"},
                                     data=json.dumps({"delete": pending}).encode())
            with OPENER.open(req, timeout=COMFY_FREE_TIMEOUT_S):
                pass
        except (HTTPError, URLError, OSError):
            pass
    try:
        req = urlrequest.Request(f"{COMFY_URL}/interrupt", method="POST",
                                 headers={"Content-Type": "application/json"}, data=b"{}")
        with OPENER.open(req, timeout=COMFY_FREE_TIMEOUT_S):
            pass
    except (HTTPError, URLError, OSError):
        pass
    return len(pending) + running


_comfy_free: dict = {}        # 控制台清理进行态 {"op","since"}：按钮转圈以它为准


def comfy_free_console(force: bool) -> "dict | None":
    """控制台的「清理显存」按钮。
    温和 = 画布同款语义: 只 POST /free，轮询最多 GENTLE_FREE_WAIT_S，看显存读数是否真降
    （≥256 MiB 即认账；读数纹丝不动两次就提前收手，别白等）；绝不打断在跑的任务。
    强制 = 先 interrupt + 清队列，再 /free，用和 Load 放卡同一个等待窗与水位
    （COMFY_FREE_WAIT_S / COMFY_FREE_TARGET_MIB）确证卡已让出。None = ComfyUI 不可达。"""
    before = _comfy_probe()
    if before is None:
        return None
    t0 = time.time()
    _comfy_free["op"] = "force" if force else "gentle"
    _comfy_free["since"] = t0
    try:
        cleared = comfy_interrupt_and_clear() if force else 0
        try:
            req = urlrequest.Request(f"{COMFY_URL}/free", method="POST",
                                     headers={"Content-Type": "application/json"},
                                     data=json.dumps({"unload_models": True,
                                                      "free_memory": True}).encode())
            with OPENER.open(req, timeout=COMFY_FREE_TIMEOUT_S):
                pass
        except (HTTPError, URLError, OSError):
            pass                        # best effort; the measuring loop below judges anyway
        after = before
        last = before["vram_used_mib"]
        stable = 0
        while time.time() - t0 < (COMFY_FREE_WAIT_S if force else GENTLE_FREE_WAIT_S):
            time.sleep(0.3)
            probe = _comfy_probe()
            if probe is None:
                break
            after = probe
            if force:
                if after["vram_free_mib"] >= COMFY_FREE_TARGET_MIB:
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
    gave = after["vram_free_mib"] >= COMFY_FREE_TARGET_MIB
    revent("comfy", ("force" if force else "gentle") + " free: " +
           "%.1f GB 显存已释放，用时 %d 秒" % (freed_gb, int(time.time() - t0)) +
           ("，显卡已让出" if gave else "，尚未让出") +
           ("（清掉 %d 个任务）" % cleared if force and cleared else ""))
    return {"ok": True, "force": force,
            "freed_vram_mib": max(0, before["vram_used_mib"] - after["vram_used_mib"]),
            "freed_ram_mib": max(0, before["ram_used_mib"] - after["ram_used_mib"]),
            "waited_s": int(time.time() - t0),
            "tasks_cleared": cleared if force else 0,
            "gave_card": gave}


_busy: dict[str, dict] = {}    # model -> {"op","since"}: an in-flight load/unload.
                               # The gateway console draws its ring progress from here,
                               # so refreshing the page mid-load keeps the timer going.


def set_busy(name: str, op: str) -> None:
    _busy[name] = {"op": op, "since": time.time()}


def clear_busy(name: str) -> None:
    _busy.pop(name, None)


def busy_info(name: str):
    b = _busy.get(name)
    if not b:
        return None
    return {"op": b["op"], "elapsed_s": int(time.time() - b["since"])}


def default_backend() -> Backend | None:
    """无 model 字段请求的跟随顺序: 先跟驻留的模型（About/Monitor 说的是正在跑的引擎），
    再跟用户最近点选的模型（webUI 的 Load 按钮不再只能加载名字序第一档），
    最后回落名字序第一。"""
    ranked = sorted(BACKENDS.values(), key=lambda x: x.name)
    for b in ranked:
        if resident_of(b) is True:
            return b
    pref = preferred_backend()
    if pref is not None and pref.alive():
        return pref
    return next(iter(ranked), None)


def pick_backend(model: str | None) -> Backend | None:
    if model:
        for b in sorted(BACKENDS.values(), key=lambda x: x.name):
            if b.matches(model):
                return b
    return default_backend()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"                # close per response; SSE streams fine
    server_version = "strata-router/1"

    def log_message(self, fmt, *args):           # quieter default log
        pass

    # ---- helpers -------------------------------------------------------
    def _auth(self) -> str:
        return self.headers.get("Authorization", "")

    def _read_body(self) -> bytes:
        if (self.headers.get("Transfer-Encoding") or "").lower().endswith("chunked"):
            body = bytearray()
            while True:
                line = self.rfile.readline(65536).strip()
                size = int(line.split(b";")[0], 16)
                if size:
                    body += self.rfile.read(size)
                    self.rfile.read(2)           # CRLF
                else:
                    self.rfile.readline()
                    break
                if len(body) > (256 << 20):
                    break
            return bytes(body)
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length else b""

    def _cors_headers(self) -> None:
        """Browser pages (ST extensions) call /v1/* cross-origin; without these the browser blocks."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, x-api-key, anthropic-version, anthropic-beta")
        self.send_header("Access-Control-Max-Age", "600")

    def _send(self, status: int, body: bytes, ctype: str = "application/json",
                 headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode())

    def _forward_raw(self, backend: Backend, method: str, path_qs: str, body: bytes,
                     extra_timeout: float = 900.0) -> int:
        """Stream the backend's answer through, byte for byte."""
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
        if self._auth():
            headers["Authorization"] = self._auth()
        req = urlrequest.Request(backend.base + path_qs, data=body if body else None,
                                 headers=headers, method=method)
        try:
            resp = OPENER.open(req, timeout=extra_timeout)
        except HTTPError as e:
            resp = e                              # pass the backend's status/body through
        except (URLError, OSError) as e:
            self._json(502, {"error": {"message": f"backend {backend.name} unreachable: {e}"}})
            return 502
        with resp:
            status = resp.code
            self.send_response(status)
            ctype = resp.headers.get("Content-Type", "application/json")
            self.send_header("Content-Type", ctype)
            self._cors_headers()
            self.end_headers()
            try:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass                              # the client went away mid-stream
            return status

    def _forward_html(self, backend: Backend, path_qs: str) -> None:
        """GET a webUI HTML page, buffer it, inject the unload-watcher before </body>
        (marker check guards double injection), answer with a corrected length."""
        headers = {"Content-Type": self.headers.get("Content-Type", "text/html")}
        if self._auth():
            headers["Authorization"] = self._auth()
        req = urlrequest.Request(backend.base + path_qs, headers=headers, method="GET")
        try:
            resp = OPENER.open(req, timeout=15)
        except HTTPError as e:
            resp = e
        except (URLError, OSError) as e:
            self._json(502, {"error": {"message": f"backend {backend.name} unreachable: {e}"}})
            return
        with resp:
            status = resp.code
            ctype = resp.headers.get("Content-Type", "text/html")
            try:
                body = resp.read()
            except (ConnectionResetError, OSError):
                body = b""
            if status == 200 and "text/html" in ctype and b"strataGatewayWatch" not in body:
                inject = WATCH_JS.encode("utf-8")
                i = body.rfind(b"</body>")
                body = (body[:i] + inject + body[i:]) if i >= 0 else (body + inject)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self._cors_headers()
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionResetError, BrokenPipeError):
                pass

    # ---- routing -------------------------------------------------------
    def _models_all(self) -> None:
        out = []
        for b in sorted(BACKENDS.values(), key=lambda x: x.name):
            try:
                req = urlrequest.Request(f"{b.base}/v1/models",
                                         headers={"Authorization": self._auth()} if self._auth() else {})
                with OPENER.open(req, timeout=8) as r:
                    out.extend(json.loads(r.read() or b"{}").get("data") or [])
            except HTTPError as e:
                if e.code in (401, 403):          # the backend is up and wants the key: pass it on
                    body = e.read()
                    return self._send(e.code, body)
                b.spawn()                         # down: (re)start it, it lists itself when up
            except (URLError, OSError, ValueError):
                b.spawn()                         # down: (re)start it, it lists itself when up
        self._json(200, {"object": "list", "data": out,
                         "router": {"service": "strata-router", "port": ROUTER_PORT}})

    def _health_all(self) -> None:
        backends = []
        for b in sorted(BACKENDS.values(), key=lambda x: x.name):
            alive = b.alive()
            if not alive:
                b.spawn()
            backends.append({"model": b.name, "port": b.port, "alive": alive,
                             "loaded": b.resident() if alive else None,
                             "busy": busy_info(b.name)})
        self._json(200, {"status": "ok", "service": "strata-router", "port": ROUTER_PORT,
                         "backends": backends})

    def _prepare_load(self, target: Backend) -> None:
        """The target is not resident: free the machine for it, then wait for its
        API (a freshly spawned lazy backend binds within seconds or so)."""
        if not target.alive():
            target.spawn()
            if not target.wait_alive(LOAD_WAIT_S):
                raise RuntimeError(f"backend {target.name} did not come up on :{target.port}")
        if target.resident() is not True:            # None (fresh spawn) counts as "about to load"
            for b in sorted(BACKENDS.values(), key=lambda x: x.name):
                if b is not target and b.alive():
                    b.unload()
            if not comfy_unload():
                raise ComfyNotFree(f"ComfyUI still holds the GPU ({COMFY_FREE_WAIT_S:g} s "
                                   "after POST /free): a generation task may still be running")

    def _route(self, method: str) -> None:
        if method == "OPTIONS":                # CORS preflight: answer here, no backend roundtrip
            self.send_response(204)
            self._cors_headers()
            self.end_headers()
            return
        parsed = self.path.split("?", 1)
        path, qs = (parsed + [""])[0].rstrip("/") or "/", (parsed + ["", ""])[1]
        if method == "GET" and path in ("/v1/models", "/models"):
            return self._models_all()
        if method == "GET" and path in ("/health", "/api/health"):
            return self._health_all()
        if method == "GET" and path == "/gateway":
            body = console.render(ROUTER_PORT).encode("utf-8")
            return self._send(200, body, "text/html; charset=utf-8",
                             headers={"Cache-Control": "no-cache"})
        if method == "GET" and path == "/router/backends":
            return self._health_all()
        if method == "GET" and path == "/router/comfy":
            return self._json(200, comfy_stats())
        if method == "GET" and path == "/router/events":
            return self._json(200, {"events": [{"t": t, "kind": k, "text": x}
                                               for t, k, x in reversed(list(_EVENTS))]})
        if method == "GET" and path == "/router/log":
            n = 200
            m2 = re.search(r"(?:^|&)n=([0-9]+)", qs)
            if m2:
                n = max(0, min(500, int(m2.group(1))))
            return self._json(200, {"lines": [[t, line] for t, line in list(_LOG)[-n:]]})
        if method == "GET" and path == "/router/info":
            return self._json(200, router_info())
        if method == "GET" and path.startswith("/router/assets/"):
            # Static art + loop video for the console. Range + ETag so a <video>
            # streams properly and revalidation after the master swaps a file is
            # a 304 instead of a re-download.
            name = unquote(path[len("/router/assets/"):])
            if not ASSET_NAME.match(name):
                return self._json(404, {"error": {"message": "no such asset"}})
            p = os.path.join(ROOT, "gw-assets", name)
            try:
                size = os.path.getsize(p)
                etag = '"%s-%x-%x"' % (name, size, int(os.path.getmtime(p)))
            except OSError:
                return self._json(404, {"error": {"message": "no such asset"}})
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            ext = name.rsplit(".", 1)[-1].lower()
            ctype = {"png": "image/png", "webp": "image/webp", "jpg": "image/jpeg",
                     "jpeg": "image/jpeg", "mp4": "video/mp4", "webm": "video/webm"}[ext]
            lo, hi, status = 0, size - 1, 200
            rng = (self.headers.get("Range") or "").strip()
            m = re.match(r"bytes=(\d*)-(\d*)$", rng) if rng else None
            if m and size:
                a, b = m.group(1), m.group(2)
                if a:
                    lo, hi = int(a), (int(b) if b else size - 1)
                    hi = min(hi, size - 1)
                    if lo >= size or lo > hi:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % size)
                        self.end_headers()
                        return
                else:
                    lo = max(0, size - (int(b) if b else size))
                status = 206
            try:
                with open(p, "rb") as f:
                    f.seek(lo)
                    data = f.read(hi - lo + 1)
            except OSError:
                return self._json(404, {"error": {"message": "no such asset"}})
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache")   # 主人换素材后刷新即见
            self.send_header("ETag", etag)
            if status == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (lo, hi, size))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (ConnectionResetError, BrokenPipeError):
                pass
            return
        if method == "GET" and path in ("/", "/monitor"):
            if not any_resident():
                self.send_response(302)
                self.send_header("Location", "/gateway")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._forward_html(pick_backend(None), self.path)
        body = self._read_body() if method == "POST" else b""
        if method == "POST" and path == "/router/comfy/free":
            force = False
            if body:
                try:
                    jj = json.loads(body)
                    force = bool(isinstance(jj, dict) and jj.get("force"))
                except ValueError:
                    pass
            res = comfy_free_console(force)
            if res is None:
                return self._json(503, {"error": {"message": "ComfyUI 当前不可达（没在跑？）"}})
            return self._json(200, res)
        model = None
        if body:
            try:
                req = json.loads(body)
                if isinstance(req, dict):
                    model = req.get("model") if isinstance(req.get("model"), str) else None
            except ValueError:
                pass
        if not model and qs:
            m = re.search(r"(?:^|&)model=([^&]+)", qs)
            if m:
                model = m.group(1)
        backend = pick_backend(model)
        if backend is None:
            return self._json(503, {"error": {"message": "no strata-*.json configs found"}})
        if path.startswith("/router/"):
            if method in ("GET", "POST") and path in PROXY_PATHS:
                return self._forward_raw(backend, method, path[len("/router"):], body)
            return self._json(404, {"error": {"message": "unknown router endpoint"}})
        if method == "POST" and path in GEN_PATHS:
            pre_res = backend.resident()
            set_busy(backend.name, "load")       # a harness-triggered cold load shows
            try:                                  # on the console too, ring and all
                try:
                    self._prepare_load(backend)
                except ComfyNotFree as e:
                    return self._json(503, {"error": {"message": str(e) + "; let the task finish, press the canvas "
                                                      "\u6e05\u7406\u663e\u5b58\u5185\u5b58 button, or retry"}},
                                      headers={"Retry-After": "15"})
                except RuntimeError as e:
                    return self._json(502, {"error": {"message": str(e)}})
                if pre_res is not True:
                    revent("load", f"{backend.name} cold-loaded for a harness request")
                    note_intentional(backend.name)
                for attempt in range(6):          # the other model's unload may still be in flight
                    status = self._forward_raw(backend, method, self.path, body)
                    if status != 503 or attempt == 5:
                        return
                    if backend.resident() is not True:
                        for b in sorted(BACKENDS.values(), key=lambda x: x.name):
                            if b is not backend and b.alive():
                                b.unload()
                        comfy_unload(wait=False)  # already waited once; just re-poke
                        time.sleep(5.0)
                    else:
                        return
                return
            finally:
                clear_busy(backend.name)
        if method == "POST" and path in ("/load", "/unload"):
            op = "load" if path == "/load" else "unload"
            set_busy(backend.name, op)            # visible on /router/backends until done
            pre_res = backend.resident() is True  # bridge re-pokes /unload while nothing is
            t0 = time.time()                      # resident: only a real move deserves an event
            try:
                if op == "load":
                    try:
                        self._prepare_load(backend)   # spawn 目标 + 卸其它模型 + 等 ComfyUI 放卡
                    except ComfyNotFree as e:
                        revent("error", f"{backend.name} load blocked: ComfyUI kept the card")
                        return self._json(503, {"error": {"message": str(e)}},
                                          headers={"Retry-After": "15"})
                    except RuntimeError as e:
                        revent("error", f"{backend.name} load blocked: {e}")
                        return self._json(502, {"error": {"message": str(e)}})
                set_preferred(backend.name)
                invalidate_resident()
                status = self._forward_raw(backend, method, self.path, body)
                note_intentional(backend.name)
                if status < 400:
                    now_res = backend.resident() is True
                    if op == "load" and not pre_res and now_res:
                        revent("load", f"{backend.name} loaded via the console in {int(time.time() - t0)} s")
                    elif op == "unload" and pre_res and not now_res:
                        revent("unload", f"{backend.name} unloaded via the console")
                return status
            finally:
                clear_busy(backend.name)
        return self._forward_raw(backend, method, self.path, body)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_OPTIONS(self):
        self._route("OPTIONS")


def cleanup() -> None:
    """Stop the backend children. The winjob job is the real guarantee (it fires
    however this process ends); this just makes an ordinary exit tidier."""
    for b in list(BACKENDS.values()):
        p = b.proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass


def main() -> None:
    global BACKENDS
    if os.name != "nt" and not os.environ.get("STRATA_ROUTER_ANYHOST"):
        print(f"[router] note: designed for the Strata box (Windows); running on "
              f"{sys.platform}", flush=True)
    BACKENDS = scan_configs()
    if not BACKENDS:
        print(f"[router] no strata-*.json in {ROOT}; nothing to serve", flush=True)
        sys.exit(1)

    def on_close(signum, frame):                # the console window's X button
        cleanup()
        os._exit(0)

    if os.name == "nt":
        import signal
        try:
            signal.signal(signal.SIGBREAK, on_close)
        except (ValueError, OSError):
            pass
    for b in BACKENDS.values():
        if not b.alive():
            b.spawn()
    threading.Thread(target=_watchdog, daemon=True).start()
    httpd = ThreadingHTTPServer(("0.0.0.0", ROUTER_PORT), Handler)
    httpd.daemon_threads = True
    names = ", ".join(f"{b.name}(:{b.port})" for b in sorted(BACKENDS.values(), key=lambda x: x.name))
    print(f"[router] ready on :{ROUTER_PORT}  models: {names}", flush=True)
    print(f"[router] default model: {default_backend().name}", flush=True)
    print("[router] Ctrl+C or close this window to stop the gateway and the engines", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
