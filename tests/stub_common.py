"""stub_common.py - shared test scaffolding for every tests/test_*.py.

Starts a real gateway (the repo tree copied into a temp dir) against stub
backends and, optionally, a stub external VRAM holder. Each test file imports
this, makes its own asserts through ok(), prints PASS lines, ends with
"ALL PASS" and cleans up (temp tree removed, processes stopped).
"""
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTER_PORT = int(os.environ.get("GW_TEST_PORT", "18090"))


HEAT_LAYERS, HEAT_EXPERTS = 4, 8    # stub-shrunken but shape-true (real box: 48x512)


def _heat_payload(configured=True):
    """/api/expert-heat face (design record §5, strata-face field set). The
    layers are stub/kit-shrunken 48x512 -> 4x8 but the semantics stay true:
    rank[] is row-major, rank[l*experts + e] = 0-based within-layer rank,
    0 = hottest (design record section 9.1); the formula (e+3l)%E keeps every
    layer a permutation of 0..experts-1. configured=False is the SECOND hidden
    face (#22, T7): the endpoint answers 200 but no expert profile is saved -
    the console section stays hidden for it exactly as for the 404. tests/
    stub_common.py and the sim kit carry this factory byte-identically
    (the H-series byte-ident pin in test_console_ctl)."""
    if not configured:
        return {"configured": False, "every_min": 0, "saved_at": None,
                "layers": 0, "experts": 0, "ranked": 0, "rank": []}
    L, E = HEAT_LAYERS, HEAT_EXPERTS
    return {"configured": True, "every_min": 10, "saved_at": 1763560000.0,
            "layers": L, "experts": E, "ranked": L * E,
            "rank": [(e + 3 * l) % E for l in range(L) for e in range(E)]}


def _conv_cache(mode):
    """v0.2.16 /metrics top-level conversation_cache (strata-face field set):
    every field present, values fake but types real (T4 renders against this)."""
    on = mode == "on"
    return {"enabled": on, "budget_mib": 4096 if on else 0,
            "slots": 8, "parked": 2 if on else 0,
            "bytes": 3221225472 if on else 0,
            "evictions": 0, "parks": 12 if on else 0,
            "restores": 9 if on else 0,
            "last_event": "restored" if on else None,
            "last_tokens": 1204 if on else None,
            "last_at": 100.5 if on else None,
            "refused": {"ram_floor": 0, "budget": 0}, "refused_total": 0,
            "last_refused": None, "requests": 40, "requests_reused": 14,
            "reused_tokens": 3100, "prompt_tokens": 9800,
            "last_reused": 640 if on else None, "last_prompt": 1800 if on else None}


def _mcp_payload(mode):
    """The v0.2.16 /mcp face (strata-face field set: servers[]:{name,transport,
    status,tools:[{tool,description}],info,error} + total tools). T5 renders
    against this: full = the three states one engine reports at once — a
    connected server with 10 tools (past the card's 8-chip cap), an errored
    server whose engine text carries escaping-hostile chars, and a disabled
    one. Values fake, shape real. empty = configured, no servers; absent is
    handled by the route (404), not by this factory."""
    if mode != "full":
        return {"servers": [], "tools": 0}
    return {"servers": [
        {"name": "strata-tools", "transport": "stdio", "status": "connected",
         "info": "in-process bundle", "error": None,
         "tools": [{"tool": "search_docs", "description": "full-text search over docs"},
                   {"tool": "fetch_url", "description": 'GET a URL & parse "<html>"'},
                   {"tool": "read_file", "description": "read one file"},
                   {"tool": "list_cards", "description": "list enrolled cards"},
                   {"tool": "tap_events", "description": "peek the event ring"},
                   {"tool": "snap_state", "description": "dump one snapshot"},
                   {"tool": "diff_bundle", "description": "diff two bundle dirs"},
                   {"tool": "prune_logs", "description": "drop old log lines"},
                   {"tool": "tail_live", "description": "follow live lines"},
                   {"tool": "watch_deck", "description": "watch the card deck"}]},
        {"name": "weather", "transport": "http", "status": "error",
         "info": "", "error": 'upstream refused: <weather.example> "key" & more',
         "tools": []},
        {"name": "legacy-db", "transport": "sse", "status": "disabled",
         "info": "", "error": None,
         "tools": [{"tool": "query", "description": "run a saved query"},
                   {"tool": "ping", "description": "server liveness"}]}],
        "tools": 12}


def _facts_engine():
    """engine.* face for the About facts block (#21, design record §4): the
    optional fields riding on top of kv/max_context/spec (which both faces
    already carry). Values fake, shape real — kv_resident is pinned to the
    ratio face ∈[0,1] (the formatter falls back to MiB above 1), arena/
    vram_free ride plain MiB ints, pool/cap plain ints. tests/stub_common.py
    and the sim kit carry this factory byte-identically (F4d pin); both
    merge it into their /metrics engine dict via **_facts_engine()."""
    return {"kv_resident": 0.92, "mtp_max": 2, "arena_mib": 512,
            "vram_free_mib": 22000, "pool_workers": 12, "prefill_cap": 4096}


class Stub:
    """Fake lazy backend: /health, /v1/models, POST /load, POST /unload.
    v0.2.16 face (#16): '/' serves the HTML marker; /props /slots /api/expert-heat
    answer their real shapes; every unknown path (including /monitor, which the
    real serve never had) mirrors the engine's 404."""
    def __init__(self, name, port):
        self.name, self.port, self.loaded = name, port, False
        self.load_calls, self.unload_calls = 0, 0
        self.shared, self.posts = {}, []
        self.max_context = 524288
        self.cc_mode, self.heat = "on", "on"    # metrics cache tri-state / heat tri-state (on|false|off)
        self.par, self.adm = False, False       # live queue variants (T71): parallel slots / refusal counters
        self.mcp_mode = "empty"                 # /mcp tri-state (T5): full / empty / absent(404)
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, code, body, ctype="application/json"):
                if isinstance(body, (bytes, bytearray)): b = bytes(body)
                elif isinstance(body, str): b = body.encode()
                else: b = json.dumps(body).encode()
                self.send_response(code); self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            def do_GET(self):
                p = self.path.split("?")[0]
                if p == "/health":
                    return self._send(200, {"status": "ok", "max_context": outer.max_context,
                                            "model": outer.name, "images": True,
                                            "api_key": False, "loaded": outer.loaded, "service": "strata"})
                if p == "/settings":
                    return self._send(200, {"shared": bool(outer.shared), "defaults": outer.shared})
                if p == "/config":
                    return self._send(200, {"file": "strata-x.json",
                                            "keys": [{"key": "idle_unload_s", "value": 1800,
                                                      "help": "unload after N idle seconds", "kind": "number"},
                                                     {"key": "max_queue", "value": 32,
                                                      "help": "429 past this many waiting (0 = no cap)",
                                                      "kind": "number"}],
                                            "note": "used from the next start"})
                if p == "/mcp":
                    # tri-state switch (T5): full face / empty face / the old
                    # engine's 404 — the MCP card degrades against these three.
                    if outer.mcp_mode == "absent":
                        return self._send(404, {"error": "no-such-endpoint: /mcp"})
                    return self._send(200, _mcp_payload(outer.mcp_mode))
                if p == "/status":
                    return self._send(200, {"busy": False, "who": outer.name})
                if p == "/metrics":
                    _m = {
                        "engine": {"model": outer.name, "max_context": outer.max_context,
                                   "version": "0.1.56", "expert_slots": 7711,
                                   "expert_cache_mib": 14451, "kv": "k8v4", "spec": 4,
                                   **_facts_engine()},
                        "stub_tag": f"stub:{outer.name}",
                        "live": dict({"state": "idle", "queued": 0, "phase": None, "prompt_tokens": None,
                                 "prompt_read": None, "prompt_total": None, "generated": None,
                                 "max_tokens": None, "elapsed_s": None, "tok_s": None,
                                 "reused": 0, "tok_s_mean": None,
                                 "prefill_tok_s_mean": None},
                                **({} if not outer.par else
                                   {"parallel": True, "running": 1, "waiting": 1, "admitting": 1,
                                    "slots": [{"slot": 0, "state": "generating", "prompt_read": 1204,
                                               "generated": 512, "elapsed_s": 3.0, "tok_s": 41.0},
                                              {"slot": 1, "state": "idle", "held_tokens": 8192}]}),
                                **({} if not outer.adm else
                                   # SPECULATIVE shape, not in v0.2.16 — the
                                   # strata-face live table has no admission
                                   # object; the switch exists to exercise the
                                   # panel's render/degrade face (T71)
                                   {"admission": {"total": 9, "ram_floor": 2, "budget": 7}})),
                        "requests": [], "requests_kept": 0,
                        "totals": {"requests": 0, "prompt_tokens": 0, "reused": 0, "output_tokens": 0,
                                   "prompt_ms": 0.0, "decode_ms": 0.0, "since": 100.0,
                                   "drafts_offered": 0, "drafts_accepted": 0},
                        "hardware": {"gpu_util": 30, "gpu_mem_used": 23622320128,
                                     "gpu_mem_total": 25769803776, "gpu_temp": 71, "gpu_power": 307.3,
                                     "gpu_power_limit": 350.0, "gpu_pcie_gen": 3, "gpu_pcie_gen_max": 3,
                                     "gpu_pcie_width": 16, "gpu_pcie_rx_mb": 1.57, "cpu": 44.2,
                                     "ram_used": 65131073536, "ram_total": 68590182400,
                                     "disk_read_mb": 5.86, "disk_write_mb": 0.41,
                                     "tok_s": 0.0, "prefill_tok_s_mean": 2002.1},
                        "hardware_static": {"gpu_name": "SomeGPU 24G", "gpu_count": 1,
                                            "cpu_name": "SomeCPU", "cores": 10, "threads": 20, "psutil": True},
                        "history": {"tok_s": [70, 80], "gpu_util": [20, 30],
                                    "gpu_mem_used": [23622320128] * 2, "gpu_temp": [70, 71],
                                    "gpu_power": [300, 307], "gpu_pcie_rx_mb": [17609.0, 1.57],
                                    "cpu": [16.9, 44.2], "ram_used": [64994316288, 65131073536],
                                    "disk_read_mb": [0.04, 5.86], "prefill_tok_s_mean": [1996.2, 2002.1]},
                        "time": 123.0}
                    if outer.cc_mode != "absent":
                        _m["conversation_cache"] = _conv_cache(outer.cc_mode)
                    return self._send(200, _m)
                if p == "/v1/models":
                    return self._send(200, json.dumps({"object": "list", "data": [
                        {"id": outer.name, "object": "model", "owned_by": "stub",
                         "status": {"value": "loaded" if outer.loaded else "unloaded"}}]}))
                if p == "/props":
                    # llama.cpp-style /props (v0.2.16 face): real shape,
                    # stub keeps only what the console renders - no 30 KB template.
                    return self._send(200, {
                        "default_generation_settings": {"max_tokens": 8192, "temperature": 1.0,
                                                        "top_p": 0.95, "top_k": 20},
                        "total_slots": 1, "model_alias": outer.name,
                        "chat_template": "<short stub template, not the real 30 KB text>",
                        "chat_template_caps": {"thinking": True, "tools": True},
                        "modalities": ["text"], "models_autoload": [],
                        "is_sleeping": not outer.loaded,
                        "model_path": "/stub/models/" + outer.name + ".gguf",
                        "build_info": {"version": "0.1.62-stub"}})
                if p == "/slots":
                    # llama.cpp-style /slots: [] when the model is not loaded.
                    if not outer.loaded:
                        return self._send(200, [])
                    return self._send(200, [{"id": 0, "n_ctx": 8192, "is_processing": False,
                                             "n_prompt_tokens": 0}])
                if p == "/v1/status":
                    # real v0.2.16 face (compat-baseline console_routes pin):
                    # honest ~1KB subset; every top-level key the console reads.
                    return self._send(200, {"service": "strata", "model": outer.name,
                                            "loaded": outer.loaded, "auto_load": True,
                                            "structured_output": True, "engine": "0.1.56",
                                            "uptime_s": 123.0, "cache_max_tokens": 8192,
                                            "context": {"n_ctx": outer.max_context},
                                            "concurrency": {"serving": 1, "requested": 1},
                                            "dialects": ["chat"], "vision": True,
                                            "image_generation": True,
                                            "activity": {"in_flight": 0},
                                            "last_timings": {}, "vram": {}, "machine": {}})
                if p == "/api/expert-heat":
                    # tri-state switch (#16 + #22): "off" = the real serve with
                    # no expert profile (404); "false" = the endpoint answers
                    # 200 but reports configured:false; "on" = the grid face.
                    if outer.heat == "off":
                        return self._send(404, {"error": "no expert profile configured"})
                    return self._send(200, _heat_payload(outer.heat != "false"))
                if p == "/":
                    return self._send(200, f"<html><body>stub:{outer.name}</body></html>", "text/html; charset=utf-8")
                # v0.2.16 truth (#16): the real serve 404s every unknown path
                # (no /monitor, no /queue, no /experts) - so must the stub.
                return self._send(404, {"error": "no-such-endpoint: " + p})
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(n)
                p = self.path.split("?")[0]
                if p == "/settings" or p == "/config":
                    outer.posts.append((p, self.headers.get("Authorization", ""), body.decode()))
                    if p == "/settings":
                        try: outer.shared = (json.loads(body.decode() or b"{}") or {}).get("defaults") or {}
                        except ValueError: outer.shared = {}
                    return self._send(200, {"ok": True})
                if p == "/v1/chat/completions":
                    inner = json.dumps({"tags": ["on-device", "quantized", "self-described"],
                                        "dossier": "Demo stub self-description: an offline "
                                                   "quantized model that lives entirely on "
                                                   "this machine and speaks when asked."})
                    return self._send(200, json.dumps(
                        {"choices": [{"message": {"content": inner}}]}))
                if p == "/load":
                    outer.loaded = True; outer.load_calls += 1
                    return self._send(200, json.dumps({"status": "loaded", "echo": body.decode()}))
                if p == "/unload":
                    outer.loaded = False; outer.unload_calls += 1
                    return self._send(200, json.dumps({"status": "unloaded"}))
                return self._send(200, "{}")
        self.srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def shutdown(self):
        self.srv.shutdown()
        self.srv.server_close()     # a dead stub must refuse connections, not hang them


class StubHolder:
    """Fake external VRAM holder (/free + /system_stats + /queue + /interrupt).
    mode: none=numbers untouched | drops=/free or /interrupt frees the card | hold=stuck."""
    def __init__(self, port):
        self.vram_total, self.vram_free = 24576, 22000      # MiB
        self.ram_total, self.ram_used = 65536, 40000
        self.mode, self.free_calls, self.interrupt_calls = "none", 0, 0
        self.queue_deletes = []
        self.pending, self.running = [["pid1", "x"], ["pid2", "x"]], [{"prompt_id": "run1"}]
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            def _drop(self):
                if outer.mode == "drops":
                    outer.vram_free, outer.ram_used = 21000, 24000
            def do_GET(self):
                p = self.path.split("?")[0]
                if p == "/system_stats":
                    M = 1048576
                    return self._send(200, {"system": {"ram_total": outer.ram_total * M, "ram_used": outer.ram_used * M},
                                            "devices": [{"name": "cuda:0", "type": "cuda", "index": 0,
                                                          "vram_total": outer.vram_total * M, "vram_free": outer.vram_free * M}]})
                if p == "/queue":
                    return self._send(200, {"queue_pending": outer.pending, "queue_running": outer.running})
                return self._send(404, {"error": "nope"})
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(n)
                p = self.path.split("?")[0]
                if p == "/free":
                    outer.free_calls += 1; self._drop()
                    return self._send(200, {})
                if p == "/queue":
                    try:
                        dele = (json.loads(body.decode() or b"{}") or {}).get("delete") or []
                    except ValueError:
                        dele = []
                    outer.queue_deletes.extend(dele)
                    outer.pending = [row for row in outer.pending if row[0] not in dele]
                    return self._send(200, {})
                if p == "/interrupt":
                    outer.interrupt_calls += 1; outer.running = []; self._drop()
                    return self._send(200, {})
                return self._send(404, {})
        self.srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def shutdown(self):
        self.srv.shutdown()
        self.srv.server_close()     # a dead stub must refuse connections, not hang them


class Gateway:
    """Copy the repo tree (minus junk) into a temp dir, plant strata-*.json
    configs for the given model names, spawn the gateway, wait until ready."""
    # gateway.json excluded: the operator's private file (strata_home,
    # gpu_free, engine_source...) must not leak into a test gateway's scan -
    # with a real strata_home planted, every suite would discover and lazily
    # spawn the REAL production configs. Tests that need a gateway.json write
    # their own into the temp tree.
    _SKIP = {".git", "testdir", "tests", "__pycache__", "strata-router.py.orig",
             "gateway.json"}

    def __init__(self, models, ports, holder_port=None, extra_env=None):
        self.root = tempfile.mkdtemp(prefix="gwtest-")
        for item in sorted(os.listdir(REPO)):
            if item in self._SKIP:
                continue
            s, d = os.path.join(REPO, item), os.path.join(self.root, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy(s, d)
        self.cfg_paths = {}
        for name, port in zip(models, ports):
            p = os.path.join(self.root, f"strata-{name}.json")
            with open(p, "w") as f:
                json.dump({"model_name": name, "port": port, "api_key": "",
                           "idle_unload_s": 1800}, f)
            self.cfg_paths[name] = p
        os.makedirs(os.path.join(self.root, "gw-assets"), exist_ok=True)
        open(os.path.join(self.root, "gw-assets", "bg-loop.mp4"), "wb").write(b"VFIX" * 750)
        open(os.path.join(self.root, "gw-assets", "qwen-chan.png"), "wb").write(b"\x89PNG fake mascot")
        open(os.path.join(self.root, "gw-assets", "sc117-chan.png"), "wb").write(b"\x89PNG fake mascot")
        env = dict(os.environ, STRATA_ROUTER_PORT=str(ROUTER_PORT), STRATA_ROUTER_ANYHOST="1",
                   GW_GPU_FREE_WAIT="4", STRATA_WATCH_S="2",
                   STRATA_SWEEP="0",            # a test gateway must NEVER sweep the host
                   STRATA_HOME=self.root)       # nor discover the host's real model configs
        if holder_port:
            env["GW_GPU_URLS"] = f"http://127.0.0.1:{holder_port}"
        if extra_env:
            env.update(extra_env)
        self.env = env
        self.proc = subprocess.Popen([sys.executable, os.path.join(self.root, "strata-router.py")], env=env)

    def req_bin(self, method, path):
        r = urllib.request.Request(f"http://127.0.0.1:{ROUTER_PORT}{path}", method=method)
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers
        except (urllib.error.URLError, OSError) as e:
            return 0, str(e).encode(), {}

    # ---- HTTP helpers (against the running gateway) -------------------
    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(f"http://127.0.0.1:{ROUTER_PORT}{path}", data=data, method=method,
                                   headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
        except (urllib.error.URLError, OSError) as e:
            return 0, str(e)

    def raw(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=15)
        hdrs = dict(headers or {})
        if body is not None:
            hdrs.setdefault("Content-Type", "application/json")
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=hdrs)
        r = c.getresponse()
        data = r.read()
        loc = r.getheader("Location") or ""
        ctype = r.getheader("Content-Type") or ""
        c.close()
        return r.status, data, loc, ctype

    def get(self, path):
        return self.req("GET", path)

    def post(self, path, body=None):
        return self.req("POST", path, body if body is not None else {})

    def delete(self, path):
        return self.req("DELETE", path)

    def get_text(self, path):
        return self.req("GET", path)[1]

    # ---- lifecycle -----------------------------------------------------
    def wait_ready(self, expect_models=None):
        deadline = time.time() + 20
        while time.time() < deadline:
            s, h = self.get("/router/backends")
            try:
                bl = json.loads(h).get("backends")
            except ValueError:
                bl = None
            if s == 200 and bl:
                if expect_models is None or sorted(b["model"] for b in bl) == sorted(expect_models):
                    return
            time.sleep(0.4)
        raise RuntimeError("gateway did not come up in time")

    def cards_file(self):
        return os.path.join(self.root, "cards", "cards.json")

    def restart(self):
        """Restart the gateway on the SAME temp ROOT: runtime state files
        (router-setup.json history, cards, ports) survive the process - this
        is how the 'badge still shows after a gateway restart' pins run."""
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = subprocess.Popen([sys.executable,
                                      os.path.join(self.root, "strata-router.py")],
                                     env=self.env)

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.root, ignore_errors=True)


def ok(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)
