"""backends.py - discover strata-*.json configs, manage lazy backend processes,
residency answers, the preferred-model stickiness and engine info aggregation."""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import threading
import time

from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from . import config
from . import events

_lock = threading.Lock()                      # guards BACKENDS and port state
_spawn_locks: dict[str, threading.Lock] = {}  # one spawn at a time per config
_CFG_FACTS: dict[str, dict] = {}              # static card facts, per config path


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

    def cfg_facts(self) -> dict:
        """Curated static facts straight from the model json (works offline).
        Every value is read from the user's own config file - never hardcoded,
        never a tier name written into this repo."""
        hit = _CFG_FACTS.get(self.cfg_path)
        if hit is not None:
            return hit
        try:
            with open(self.cfg_path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
        a = [str(x) for x in (cfg.get("args") or [])]

        def arg(flag):
            i = a.index(flag) if flag in a else -1
            return a[i + 1] if 0 <= i and i + 1 < len(a) else None

        quant = None
        pack = arg("--pack")
        if pack:
            quant = str(pack).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or None
        if not quant and "-" in self.name:
            tail = self.name.rsplit("-", 1)[-1]
            if any(ch.isdigit() for ch in tail):      # tier-ish suffix only
                quant = tail or None
        mc = arg("--max-context")
        rope = arg("--rope-scaling")
        rope_scale = arg("--rope-scale")
        if rope and rope_scale:
            rope = rope + " x" + rope_scale
        facts = {
            "quant": quant,
            "max_context": int(mc) if mc and mc.isdigit() else None,
            "kv": arg("--kv"),
            "rope": rope,
            "drafting": cfg.get("drafting") or ("mtp" if arg("--mtp") else None),
            "spec": arg("--spec"),
            "idle_unload_s": cfg.get("idle_unload_s"),
            "reasoning_effort": cfg.get("reasoning_effort"),
            "sampling": cfg.get("sampling") or {},
        }
        # ux v8: keep the SAME key set for every model — missing entries stay
        # as None so the console renders one fixed row schema, never
        # "present on one card, absent on the next".
        _CFG_FACTS[self.cfg_path] = facts
        return facts

    def alive(self) -> bool:
        try:
            with config.OPENER.open(f"{self.base}/health", timeout=3):
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
            with config.OPENER.open(req, timeout=5) as r:
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
            if time.time() - self.last_spawn < config.SPAWN_COOLDOWN_S:
                return
            self.last_spawn = time.time()
            py = config.resolve_python()
            if not os.path.isfile(config.SERVER_PY):
                print("[router] cannot spawn %s: serve/server.py missing under %s - "
                      "Strata engine not found; set STRATA_HOME or gateway.json \"strata_home\" "
                      "(未找到 Strata 引擎，请配置 STRATA_HOME / gateway.json)"
                      % (self.name, config.strata_home()), flush=True)
                return
            if not py or not os.path.isfile(py):
                print("[router] cannot spawn %s: Strata python env missing - set STRATA_PYTHON "
                      "(looked for .venv under %s) (未找到引擎 Python 环境)"
                      % (self.name, config.strata_home()), flush=True)
                return
            # Foreground child: the backend shares this console, so its startup
            # narrator and engine lines stream into the same window as the
            # router's. winjob.contain ties it (and its engine, vision encoder,
            # everything it starts later) to this process's lifetime: whatever
            # ends the router - Ctrl+C, the window's X, taskkill, a crash - the
            # job's kill-on-close takes the whole tree with it.
            self.proc = subprocess.Popen(
                [py, config.SERVER_PY, "--engine", "strata", "--config", self.cfg_path,
                 "--host", "0.0.0.0", "--port", str(self.port),
                 "--api-key", self.key, "--lazy"],
                cwd=config.ROOT, stdin=subprocess.DEVNULL)
            from . import winjob as _winjob
            if not _winjob.contain(self.proc):
                print("[router] note: job-object tie-in unavailable here; "
                  "Ctrl+C / console close still stop the tree via the "
                  "signal handlers", flush=True)
            print(f"[router] spawned {self.name} on :{self.port} (lazy)", flush=True)
            events.revent("backend", f"{self.name} backend process started on :{self.port}")
        finally:
            lock.release()

    def wait_alive(self, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.alive():
                return True
            time.sleep(2.0)
        return False

    GEN_PROMPT = {
        "zh": "面向模型管理面板做自我简介。只输出严格 JSON，不要其他文字："
              '{"tags": ["4-6个短标签"], "dossier": "80-150字的自我介绍"}。'
              "标签覆盖能力域与风格特征。",
        "en": "Introduce yourself for a model console. Reply with strict JSON only: "
              '{"tags": ["4-6 short tags"], "dossier": "an 80-150 character self-introduction"}. '
              "Tags should cover capability domains and style traits.",
    }

    def gendossier(self, lang: str = "zh") -> dict | None:
        """Ask the LOADED model to describe itself -> {tags, dossier}; None if it
        can't be asked (offline or unparseable failure). Residency itself is
        judged once, up in the route — a second hidden probe here used to
        flatten a busy-engine flap into the same "not loaded" 409."""
        body = {"model": self.name, "stream": False, "max_tokens": 420, "temperature": 0.8,
                "messages": [{"role": "user",
                              "content": self.GEN_PROMPT.get(lang, self.GEN_PROMPT["zh"])}]}
        req = urlrequest.Request(
            f"{self.base}/v1/chat/completions", method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"},
            data=json.dumps(body).encode())
        try:
            with config.OPENER.open(req, timeout=120) as r:
                txt = (json.loads(r.read() or b"{}")["choices"][0]["message"]["content"]) or ""
        except (URLError, OSError, ValueError, KeyError, IndexError):
            return None
        tags, dossier = [], ""
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                j = json.loads(m.group(0))
                dossier = str(j.get("dossier") or "").strip()
                t = j.get("tags")
                if isinstance(t, list):
                    tags = [str(x).strip() for x in t if str(x).strip()][:8]
            except ValueError:
                pass
        if not dossier:
            dossier = txt.strip()[:220]
        if not tags and not dossier:
            return None
        return {"model": self.name, "tags": tags, "dossier": dossier}

    def unload(self, timeout: float = 60.0) -> None:
        """Best effort: stop the engine to free RAM/VRAM. busy (409) is fine here:
        the load's own min_free_vram check + the router's retry catch it."""
        try:
            req = urlrequest.Request(
                f"{self.base}/unload", method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.key}"}, data=b"{}")
            with config.OPENER.open(req, timeout=timeout) as r:
                print(f"[router] unload {self.name}: {r.status} {r.read()[:120]!r}", flush=True)
        except HTTPError as e:
            print(f"[router] unload {self.name}: HTTP {e.code}", flush=True)
        except (URLError, OSError) as e:
            print(f"[router] unload {self.name}: {e}", flush=True)
        invalidate_resident()
        events.note_intentional(self.name)


def scan_configs() -> dict[str, Backend]:
    """strata-*.json next to the entry -> backends. Ports: a config's own port
    (when it is not the router's) wins, else the saved mapping, else the next
    free 1808x. The mapping is persisted so restarts keep the same ports."""
    saved: dict[str, int] = {}
    try:
        with open(config.PORTS_FILE, encoding="utf-8") as f:
            saved = {k: int(v) for k, v in (json.load(f) or {}).items()}
    except (OSError, ValueError):
        pass
    taken = {config.ROUTER_PORT}
    backends: dict[str, Backend] = {}
    entries = []
    for path in sorted(glob.glob(os.path.join(config.ROOT, "strata-*.json"))):
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
        if not port and isinstance(own, int) and own not in taken and own != config.ROUTER_PORT:
            port = own
        if not port:
            port = config.FIRST_BACKEND_PORT
            while port in taken:
                port += 1
        taken.add(port)
        backends[path] = Backend(path, cfg, port)
    with _lock:
        new_saved = {b.name: b.port for b in backends.values()}
        if new_saved != saved:
            try:
                with open(config.PORTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(new_saved, f, indent=1)
            except OSError as e:
                print(f"[router] cannot save {config.PORTS_FILE}: {e}", flush=True)
    return backends


BACKENDS: dict[str, Backend] = {}

_resident_cache: dict[str, tuple[float, bool | None]] = {}


def resident_of(b: Backend) -> bool | None:
    """b.resident() with a short cache: the webUI polls /metrics every second,
    and each answer costs a backend round trip."""
    now = time.monotonic()
    hit = _resident_cache.get(b.cfg_path)
    if hit is not None and now - hit[0] < config.RESIDENT_TTL_S:
        return hit[1]
    r = b.resident()
    _resident_cache[b.cfg_path] = (now, r)
    return r


_preferred: dict = {"name": None}       # 最近一次用户点名加载/卸载的模型（粘性）


def invalidate_resident() -> None:
    """状态刚被改变（load/unload/换装）: 丢掉 3s 驻留缓存，让跟随即时生效。"""
    _resident_cache.clear()


def cache_resident(b: Backend, value: bool | None) -> None:
    """Store a freshly-read residency answer, so the next any_resident() within
    the TTL window does not pay for another round trip - and never answers
    from a stale entry written mid-load."""
    _resident_cache[b.cfg_path] = (time.monotonic(), value)


def set_preferred(name: str | None) -> None:
    if _preferred["name"] != name:
        _preferred["name"] = name
        print(f"[router] preferred model: {name}", flush=True)
        events.revent("switch", "preferred model: " + str(name))


def preferred_backend() -> Backend | None:
    name = _preferred["name"]
    if not name:
        return None
    return next((b for b in BACKENDS.values() if b.name == name), None)


def any_resident() -> bool:
    return any(resident_of(b) is True for b in BACKENDS.values())


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


_APPVER: dict = {}


def app_version() -> dict:
    """The Strata checkout's own tag, read once per gateway start."""
    if _APPVER:
        return _APPVER
    out = {}
    try:
        r = subprocess.run(["git", "-C", config.ROOT, "describe", "--tags"],
                           capture_output=True, text=True, timeout=6)
        if r.returncode == 0:
            out["version"] = r.stdout.strip().lstrip("v")
        r = subprocess.run(["git", "-C", config.ROOT, "log", "-1", "--format=%h"],
                           capture_output=True, text=True, timeout=6)
        if r.returncode == 0:
            out["commit"] = r.stdout.strip()
    except (OSError, ValueError):
        pass
    if not out.get("version"):
        # no git: fall back to the checkout's CMakeLists project version
        try:
            with open(os.path.join(config.ROOT, "CMakeLists.txt"), encoding="utf-8-sig") as f:
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
        p = os.path.join(config.ROOT, cand)
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
            with config.OPENER.open(b.base + "/health", timeout=5) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            models[b.name] = {"alive": True, "max_context": d.get("max_context"),
                              "images": d.get("images"), "loaded": d.get("loaded"),
                              "image_generation": d.get("image_generation"),
                              "cfg": b.cfg_facts()}
        except (HTTPError, URLError, OSError, ValueError):
            models[b.name] = {"alive": False, "cfg": b.cfg_facts()}
    from . import gpu_free
    st = gpu_free.settings()
    return {"build": build, "app": app_version(), "models": models, "port": config.ROUTER_PORT,
            "gpu_free_target_mib": gpu_free.effective_target(st),
            "gpu_free_urls": st["urls"]}
