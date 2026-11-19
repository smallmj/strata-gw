#!/usr/bin/env python3
"""test_gateway_switch.py - strata-router.py 模型选择加载 + 自动退回选择页的测试（stub 后端）。
用法: python3 test_gateway_switch.py [router.py路径]   (默认 ./strata-router.py)
期望: 每条断言打 PASS，最后 ALL PASS，exit 0。跑完自清（临时目录删除）。
"""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = tempfile.mkdtemp(prefix="gwtest-")
HERE = os.path.dirname(os.path.abspath(__file__))
VIS = os.environ.get("GW_VISUAL") == "1"
ROUTER_SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), os.pardir, "strata-router.py")
ROUTER_PORT = 18090

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

def _mcp_payload(mode):
    """The v0.2.16 /mcp face (strata-face field set: servers[]:{name,transport,
    status,tools:[{tool,description}],info,error} + total tools). T5 renders
    against this: full = the three states one engine reports at once — a
    connected server with 10 tools (past the card's 8-chip cap), an errored
    server whose engine text carries escaping-hostile chars, and a disabled
    one. Values fake, shape real. (Kept byte-identical to tests/stub_common.py
    and the sim kit's copy — K-SIM5 pins the endpoint set, this pins the face.)"""
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


class Stub:
    """假后端: /health、/v1/models、POST /load、POST /unload;"/" 回 HTML 标记,
    v0.2.16 face (#16): /props /slots /api/expert-heat 真形状,未知路径 404(真 serve 没有 /monitor)。"""
    def __init__(self, name, port):
        self.name, self.port, self.loaded = name, port, False
        self.load_calls, self.unload_calls = 0, 0
        self.shared, self.posts = {}, []
        self.cc_mode, self.heat = "on", "on"    # metrics cache 三态 / heat 三态 (on|false|off)
        self.par, self.adm = False, False       # metrics live 队列变体 (T71): parallel slots / 拒收计数
        self.mcp_mode = "empty"                 # /mcp 三态 (T72/T5): full / empty / absent(404)
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
                    return self._send(200, {"status": "ok", "max_context": 524288,
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
                    # 三态开关 (T72): full face / empty face / 旧引擎 404 —
                    # MCP 卡按这三种降级。
                    if outer.mcp_mode == "absent":
                        return self._send(404, {"error": "no-such-endpoint: /mcp"})
                    return self._send(200, _mcp_payload(outer.mcp_mode))
                if p == "/status":
                    return self._send(200, {"busy": False, "who": outer.name})
                if p == "/metrics":
                    _m = {
                        "engine": {"model": outer.name, "max_context": 524288, "version": "0.1.56",
                                   "expert_slots": 7711, "expert_cache_mib": 14451, "kv": "k8v4", "spec": 4},
                        "stub_tag": f"stub:{outer.name}",
                        "live": dict({"state": "idle", "queued": 0, "phase": None, "prompt_tokens": None,
                                 "prompt_read": None, "prompt_total": None, "generated": None,
                                 "max_tokens": None, "elapsed_s": None, "tok_s": None,
                                 "reused": 0, "tok_s_mean": None, "prefill_tok_s_mean": None},
                                **({} if not outer.par else
                                   {"parallel": True, "running": 1, "waiting": 1, "admitting": 1,
                                    "slots": [{"slot": 0, "state": "generating", "prompt_read": 1204,
                                               "generated": 512, "elapsed_s": 3.0, "tok_s": 41.0},
                                              {"slot": 1, "state": "idle", "held_tokens": 8192}]}),
                                **({} if not outer.adm else
                                   {"admission": {"total": 9, "ram_floor": 2, "budget": 7}})),
                        "requests": [{"id": "r1", "time": 111.0, "duration_s": 3.0, "finish": "stop",
                                      "prompt_tokens": 100, "reused": 40, "prompt_ms": 60.0,
                                      "output_tokens": 50, "decode_tok_s": 83.0, "hit_rate": 0.873,
                                      "pcie_share": 0.02}],
                        "requests_kept": 1,
                        "totals": {"requests": 1, "prompt_tokens": 100, "reused": 40, "output_tokens": 50,
                                   "prompt_ms": 60.0, "decode_ms": 602.0, "since": 100.0,
                                   "drafts_offered": 20, "drafts_accepted": 12},
                        "hardware": {"gpu_util": 30, "gpu_mem_used": 23622320128, "gpu_mem_total": 25769803776,
                                     "gpu_temp": 71, "gpu_power": 307.3, "gpu_power_limit": 350.0,
                                     "gpu_pcie_gen": 3, "gpu_pcie_gen_max": 3, "gpu_pcie_width": 16,
                                     "gpu_pcie_rx_mb": 1.57, "cpu": 44.2,
                                     "ram_used": 65131073536, "ram_total": 68590182400,
                                     "disk_read_mb": 5.86, "disk_write_mb": 0.41,
                                     "tok_s": 0.0, "prefill_tok_s_mean": 2002.1},
                        "hardware_static": {"gpu_name": "NVIDIA GeForce RTX 3090", "gpu_count": 1,
                                            "cpu_name": "i9-10900K", "cores": 10, "threads": 20, "psutil": True},
                        "history": {"tok_s": [70, 80], "gpu_util": [20, 30], "gpu_mem_used": [23622320128] * 2,
                                    "gpu_temp": [70, 71], "gpu_power": [300, 307],
                                    "gpu_pcie_rx_mb": [17609.0, 1.57], "cpu": [16.9, 44.2],
                                    "ram_used": [64994316288, 65131073536], "disk_read_mb": [0.04, 5.86],
                                    "prefill_tok_s_mean": [1996.2, 2002.1]},
                        "time": 123.0}
                    if outer.cc_mode != "absent":
                        _m["conversation_cache"] = _conv_cache(outer.cc_mode)
                    return self._send(200, _m)
                if p == "/v1/models":
                    return self._send(200, json.dumps({"object": "list", "data": [
                        {"id": outer.name, "object": "model", "owned_by": "stub",
                         "status": {"value": "loaded" if outer.loaded else "unloaded"}}]}))
                if p in ("/", "/monitor"):
                    return self._send(200, f"<html><body>stub:{outer.name}</body></html>", "text/html; charset=utf-8")
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
                                            "context": {"n_ctx": 524288},
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
                if p == "/load":
                    try:
                        slow = "test_slowload" in (json.loads(body.decode() or b"{}") or {})
                    except ValueError:
                        slow = False
                    if slow:
                        time.sleep(2.5)               # a real cold load takes minutes; busy must be visible then
                    outer.loaded = True; outer.load_calls += 1
                    return self._send(200, json.dumps({"status": "loaded", "echo": body.decode()}))
                if p == "/unload":
                    outer.loaded = False; outer.unload_calls += 1
                    return self._send(200, json.dumps({"status": "unloaded"}))
                if p == "/v1/chat/completions":
                    try:
                        _pm = (json.loads(body.decode() or b"{}").get("messages") or [{}])[-1].get("content") or ""
                    except ValueError:
                        _pm = ""
                    if "Translate" in _pm or "self-report" in _pm or "third-person" in _pm:
                        return self._send(200, {"choices": [{"message": {"content":
                            'Sure: {"tags": ["self-report", "test tag", "qa"], '
                            '"dossier": "Automation test operative for the gateway; reading, parsing and Q&A in a plain style."}'}}]})
                    return self._send(200, {"choices": [{"message": {"content":
                        '好的：{"tags": ["自述", "测试标签", "问答"], '
                        '"dossier": "我是网关自动化档案测试模型，覆盖读解与问答能力，风格平实。"}'}}]})
                return self._send(200, "{}")
        self.srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

class HolderStub:
    """假出图服务（外部显存占用者）: /system_stats + /free + /queue + /interrupt。
    mode: none=不动作 | drops=/free 或 /interrupt 后让卡(vram_free 拉到 21000) | hold=数字死活不动"""
    def __init__(self, port):
        self.vram_total, self.vram_free = 24576, 22000      # MiB（够 Load 用，先闲置）
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

class DeadStub:
    """T26b2: health 正常(活着)但任何 POST 直接掐连接不回包 —— 复现真机
    'engine.exe 崩了而 serve 包装还活着' 的 502 Remote end closed。"""
    def __init__(self, name, port):
        self.name, self.port = name, port
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                if self.path.split("?")[0] == "/health":
                    b = json.dumps({"status": "ok", "model": outer.name,
                                    "loaded": False, "service": "strata",
                                    "api_key": False}).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(b))); self.end_headers()
                    self.wfile.write(b)
                else:
                    self.send_response(404); self.end_headers()
            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    if length:
                        self.rfile.read(length)
                except (ValueError, OSError):
                    pass
                try:
                    self.connection.close()
                except OSError:
                    pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

class ReleaseStub:
    """假 GitHub /releases/latest: counts its hits so the hourly cache
    can be pinned without waiting an hour."""
    def __init__(self, port, payload):
        self.payload, self.hits = payload, 0
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                outer.hits += 1
                b = json.dumps(outer.payload).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        self.srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


CF = HolderStub(18097)
REL = ReleaseStub(18099, {"tag_name": "v9.9.9", "name": "T30 test release",
                          "html_url": "https://github.com/smallmj/strata-gw/releases/tag/v9.9.9"})
MA = "qwen3.8-flash-next-iq3_s" if VIS else "aaa-qwen"
MB = "sc117-qwen3.8-flash-next-abliterated-iq3_s" if VIS else "bbb-sc117"
A = Stub(MA, 18095)      # 名字排序第一 = 无驻留且无偏好时的默认
B = Stub(MB, 18096)
D = DeadStub("ddd-dead", 18094)   # T26b2: serve 活着、engine 死了的连接重置现场
MA_CFG = {"model_name": MA, "port": 18095, "api_key": "",
          # neutral fake tier values (never real engine tokens here — lint)
          "args": ["--pack", "/tmp/stub/pack-q9", "--kv", "z9z9",
                   "--rope-scaling", "lame", "--rope-scale", "2", "--spec", "4"],
          "sampling": {"temperature": 1.0, "top_p": 0.95, "top_k": 20},
          "idle_unload_s": 1800, "drafting": "drafty", "reasoning_effort": "medium"}
for name, port in ((MA, 18095), (MB, 18096)):
    with open(os.path.join(ROOT, f"strata-{name}.json"), "w") as f:
        json.dump(MA_CFG if name == MA else
                  {"model_name": name, "port": port, "api_key": ""}, f)
SRC_DIR = os.path.dirname(os.path.abspath(ROUTER_SRC))
_SKIP = {".git", "testdir", "gw-assets", "tests", "__pycache__", "strata-router.py.orig"}
for _item in sorted(os.listdir(SRC_DIR)):
    if _item in _SKIP or _item == os.path.basename(os.path.abspath(ROUTER_SRC)):
        continue
    _s, _d = os.path.join(SRC_DIR, _item), os.path.join(ROOT, _item)
    if os.path.isdir(_s):
        shutil.copytree(_s, _d, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        shutil.copy(_s, _d)
shutil.copy(ROUTER_SRC, os.path.join(ROOT, "strata-router.py"))
os.makedirs(os.path.join(ROOT, "gw-assets"), exist_ok=True)
# 视频素材 fixture：VIS 用真片（HERE/assets-real/bg-loop.mp4），非 VIS 用 3000 字节假片
if VIS and os.path.exists(os.path.join(HERE, "assets-real", "bg-loop.mp4")):
    shutil.copy(os.path.join(HERE, "assets-real", "bg-loop.mp4"),
                os.path.join(ROOT, "gw-assets", "bg-loop.mp4"))
else:
    open(os.path.join(ROOT, "gw-assets", "bg-loop.mp4"), "wb").write(b"VFIX" * 750)
if VIS:
    # give the temp ROOT a realistic build identity so /router/info chips render truthfully
    with open(os.path.join(ROOT, "CMakeLists.txt"), "w") as f:
        f.write("cmake_minimum_required(VERSION 3.24)\nproject(strata VERSION 0.2.10 LANGUAGES CXX)\n")
    os.makedirs(os.path.join(ROOT, "engine"), exist_ok=True)
    with open(os.path.join(ROOT, "engine", "BUILD.json"), "w") as f:
        json.dump({"version": "0.1.56", "source": "f-0291-rc1", "commit": "06698c674673",
                   "archs": [75, 86, 89, 120], "ptx": True, "cuda": "13.0",
                   "vision": "gpu-cuda13"}, f)
    for _n in ("qwen-chan.png", "sc117-chan.png"):
        _adj = os.path.join(HERE, "assets-real", _n.replace(".png", "-adj.png"))
        shutil.copy(_adj if os.path.exists(_adj)
                    else os.path.join(HERE, "assets-real", _n.replace(".png", "-real.png")),
                    os.path.join(ROOT, "gw-assets", _n))
else:
    open(os.path.join(ROOT, "gw-assets", "qwen-chan.png"), "wb").write(b"\x89PNG fake mascot")
# the console's local font must pass the same static pipeline: seed a minimal
# real-shape woff2 (magic wOF2) so T36b probes whitelist + content-type, not the repo blob
open(os.path.join(ROOT, "gw-assets", "jbmono-latin.woff2"), "wb").write(b"wOF2" + bytes(24))

env = dict(os.environ, STRATA_ROUTER_PORT=str(ROUTER_PORT), STRATA_ROUTER_ANYHOST="1",
             STRATA_SWEEP="0", STRATA_HOME=ROOT,   # tests never sweep the host or see its configs,
           GW_SCAN_WATCH_S="1",             # T26b: the scan watcher earns its keep fast here
           GW_GPU_URLS="http://127.0.0.1:18097",      # live stub holder, idle
           GW_RELEASE_API="http://127.0.0.1:18099/releases/latest",   # T30: pretend GitHub
           GW_GPU_FREE_WAIT="4",                 # force 等待窗缩短，测试不真等 120s
           STRATA_WATCH_S="2")                         # 看门狗提速，事件转场测试等得起
router = subprocess.Popen([sys.executable, os.path.join(ROOT, "strata-router.py")], env=env)

import urllib.request, urllib.error
def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"http://127.0.0.1:{ROUTER_PORT}{path}", data=data, method=method,
                               headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)                           # 还没 bind: 交给轮询重试

def raw(method, path, body=None):
    """不跟随重定向的原始请求: 返回 (status, body, Location)。"""
    c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=15)
    c.request(method, path, body=json.dumps(body) if body is not None else None,
              headers={"Content-Type": "application/json"} if body is not None else {})
    r = c.getresponse(); data = r.read().decode("utf-8", "replace"); loc = r.getheader("Location") or ""
    c.close(); return r.status, data, loc

def ok(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: sys.exit(1)

try:
    s, h, backends = 0, "", None
    deadline = time.time() + 15
    while time.time() < deadline:
        s, h = req("GET", "/router/backends")
        try:
            backends = json.loads(h).get("backends")
        except ValueError:
            backends = None
        if s == 200 and backends: break
        time.sleep(0.5)
    if VIS:
        print("VISUAL gateway ready: http://127.0.0.1:%d/gateway  (real model names + real mascot art)" % ROUTER_PORT, flush=True)
        import signal
        signal.pause()
    ok(s == 200 and backends and sorted(b["model"] for b in backends) == ["aaa-qwen", "bbb-sc117"],
       "T1 router up, GET /router/backends lists both models")

    s, h = req("GET", "/gateway")
    ok(s == 200 and "Strata 网关" in h
       and 'id="gforce"' in h and "强制让卡" in h and "让卡" in h
       and 'id="train-src"' in h and 'id="sec-about"' in h
       and 'id="sec-dyn"' in h and 'id="sec-monitor"' in h
       and "立绘待入" in h,
       "T2 GET /gateway console: sections + give-card buttons + art placeholder")
    s, hc = req("GET", "/router/cards")
    ok(s == 200 and "qwen3.8-flash-next-iq3_s" in hc
       and "sc117-qwen3.8-flash-next-abliterated-iq3_s" in hc
       and 'router/assets/qwen-chan.png' in hc and 'router/assets/sc117-chan.png' in hc,
       "T2c factory dossier cards come from /router/cards (data, not baked page)")

    s, h = req("GET", "/gateway")
    ok("__VERSION__" not in h and "__GW_PORT__" not in h and "__GITHUB_URL__" not in h,
       "T2b build placeholders substituted in the served page")

    s, h = req("GET", "/metrics")
    ok(s == 200 and "stub:aaa-qwen" in h, "T3 no model, none resident -> API follows name-sorted first")

    st, h, loc = raw("GET", "/")
    ok(st == 302 and loc == "/gateway", "T4 no resident: opening the webUI bounces to the gateway page")

    s, h = req("GET", "/router/gpu")
    c = json.loads(h)
    ok(s == 200 and c.get("running") is True and c.get("vram_free_mib") == 22000
       and c.get("freeing") is None,
       "T5 GET /router/gpu reads the live holder stub (idle, no free in flight)")

    s, h = req("POST", "/load", {"model": "bbb-sc117"})
    ok(s == 200, "T6 POST /load {model} accepted")
    ok(B.load_calls == 1, "T7 sc117 backend got the /load")
    ok(A.unload_calls == 1, "T8 router unloaded the other backend first")

    st, h, loc = raw("GET", "/")
    ok(st == 200 and "stub:bbb-sc117" in h and "strataGatewayWatch" in h,
       "T9 resident sc117: webUI served, watch script injected")

    s, h = req("GET", "/metrics")
    ok("stub:bbb-sc117" in h, "T10 API now follows the resident model")

    B.loaded = False                                   # 模拟 idle-unload / 换装卸载
    time.sleep(3.5)                                    # 等 3s 驻留缓存过期（RESIDENT_TTL_S=3.0）
    st, h, loc = raw("GET", "/")
    ok(st == 302 and loc == "/gateway", "T11 after unload: opening the webUI bounces to the gateway page")

    lb, ub = B.load_calls, A.load_calls
    s, h = req("POST", "/load", {})
    ok(s == 200 and B.load_calls == lb + 1 and A.load_calls == ub,
       "T12 bare /load follows the preferred model, not name order")

    s, h = req("POST", "/load", {"model": "aaa-qwen"})
    ok(s == 200, "T13 switch back to qwen")
    st, h, loc = raw("GET", "/")
    ok(st == 200 and "stub:aaa-qwen" in h, "T14 resident wins over preferred (regression of 2026-10-14 fix)")

    s, _ = req("OPTIONS", "/load")
    ok(s == 204, "T15 CORS preflight still local-answered")

    res = []
    t = threading.Thread(target=lambda: res.append(req("POST", "/load", {"model": "bbb-sc117", "test_slowload": 1})))
    t.start()
    time.sleep(0.7)
    s, h = req("GET", "/router/backends")
    bb = next(x for x in json.loads(h)["backends"] if x["model"] == "bbb-sc117")
    ok(s == 200 and (bb.get("busy") or {}).get("op") == "load",
       "T16 busy op=load visible while a load is in flight (survives page refresh)")
    t.join(20)
    s, h = req("GET", "/router/backends")
    bb = next(x for x in json.loads(h)["backends"] if x["model"] == "bbb-sc117")
    ok(res and res[0][0] == 200 and bb["loaded"] is True and bb.get("busy") is None,
       "T17 load finished: loaded true, busy cleared")

    # T1 truth-up (#16): the engine has no /monitor in v0.2.16 - the gateway
    # must never forward it. One unconditional 302 to the console's Monitor
    # anchor, resident or not.
    st, h, loc = raw("GET", "/monitor")
    ok(st == 302 and loc == "/gateway#sec-monitor" and "stub:bbb-sc117" not in h,
       "T18 /monitor with a model resident: 302 to the console Monitor anchor, no engine forward")

    s, h = req("POST", "/unload", {"model": "bbb-sc117"})
    time.sleep(3.5)                                    # 等 3s 驻留缓存过期
    st, h, loc = raw("GET", "/monitor")
    ok(st == 302 and loc == "/gateway#sec-monitor",
       "T19 /monitor bounces to the same anchor after unload (no residency branch)")
    _rt = open(os.path.join(ROOT, "gw", "routes.py"), encoding="utf-8").read()
    ok('/monitor")' not in _rt and '"/gateway#sec-monitor"' in _rt,
       "T19b old structure is gone: routes.py no longer pairs '/' with '/monitor' "
       "and carries the anchored Location literally (negative pin, T43 style)")

    # ---- 外部显存让卡按钮（free-memory 语义）----
    CF.vram_free, CF.ram_used, CF.mode = 2000, 40000, "drops"
    s, h = req("POST", "/router/gpu/free", {"force": False})
    j = json.loads(h)
    ok(s == 200 and j.get("ok") and j.get("force") is False
       and j.get("freed_vram_mib", 0) >= 1000 and j.get("freed_ram_mib", 0) >= 1000,
       "T20 gentle free: /free sent, VRAM+RAM release reported")

    ib = CF.interrupt_calls
    CF.vram_free, CF.mode = 2000, "hold"
    s, h = req("POST", "/router/gpu/free", {"force": False})
    j = json.loads(h)
    ok(s == 200 and j.get("freed_vram_mib") == 0 and j.get("gave_card") is False,
       "T21 gentle with nothing to free: freed 0, gave_card false")
    ok(CF.interrupt_calls == ib, "T22 gentle mode never touches /interrupt")

    CF.vram_free, CF.ram_used, CF.mode = 2000, 40000, "drops"
    CF.pending, CF.running = [["pda", "x"], ["pdb", "x"]], [{"prompt_id": "rc"}]
    s, h = req("POST", "/router/gpu/free", {"force": True})
    j = json.loads(h)
    ok(s == 200 and j.get("gave_card") is True and j.get("freed_vram_mib", 0) >= 1000
       and j.get("tasks_cleared") == 3 and CF.interrupt_calls >= ib + 1
       and "pda" in CF.queue_deletes and "pdb" in CF.queue_deletes,
       "T23 force free: interrupt + clear queue + /free, waits until the card is back")

    CF.mode, CF.vram_free = "hold", 500
    res2 = []
    t2 = threading.Thread(target=lambda: res2.append(req("POST", "/router/gpu/free", {"force": True})))
    t2.start()
    time.sleep(1.0)
    s, h = req("GET", "/router/gpu")
    fr = json.loads(h).get("freeing")
    ok(s == 200 and fr and fr.get("op") == "force" and fr.get("elapsed_s", -1) >= 0,
       "T24 freeing visible mid-force on /router/gpu (spinner survives a page refresh)")
    t2.join(20)
    _raw = res2[0][1] if res2 else "<thread never finished>"
    try:
        j = json.loads(_raw)
    except ValueError:
        raise SystemExit("T25 RAW RESPONSE: %r" % _raw[:300])
    ok(j.get("gave_card") is False and j.get("waited_s", 0) >= 3
       and json.loads(req("GET", "/router/gpu")[1]).get("freeing") is None,
       "T25 force gives up after the wait window (4s env), freeing cleared afterwards")

    CF.srv.shutdown()
    s, h = req("POST", "/router/gpu/free", {"force": False})
    ok(s == 503, "T26 holder unreachable -> 503 with error")
    s, h = req("GET", "/router/gpu")
    ok(json.loads(h).get("running") is False, "T27 /router/gpu shows not running after the holder goes down")

    # ---- 设置/配置/MCP/状态代理 ----
    s, h = req("GET", "/router/settings?model=bbb-sc117")
    ok(s == 200 and "defaults" in json.loads(h), "T28 GET /router/settings proxies to the named backend")
    s, h = req("POST", "/router/settings?model=bbb-sc117", {"defaults": {"temperature": 0.7}})
    ok(s == 200 and any(p[0] == "/settings" and '"temperature": 0.7' in p[2] for p in B.posts),
       "T29 POST /router/settings forwards the exact body to the named backend")
    s, h = req("GET", "/router/config?model=aaa-qwen")
    ok(s == 200 and json.loads(h)["keys"][0]["key"] == "idle_unload_s", "T30 GET /router/config proxies")
    s, h = req("GET", "/router/status?model=aaa-qwen")
    ok(s == 200 and json.loads(h).get("who") == "aaa-qwen", "T31 qs model param routes to the right backend")

    # ---- 事件时间线 + 日志流 ----
    s, h = req("GET", "/router/events")
    evs = json.loads(h)["events"]
    kinds = {e["kind"] for e in evs}
    ok(s == 200 and "load" in kinds and "unload" in kinds
       and any("bbb-sc117" in e["text"] for e in evs), "T32 events recorded load/unload transitions")
    s, h = req("GET", "/router/log?n=200")
    ok(s == 200 and any("preferred model" in line for t, line in json.loads(h)["lines"]),
       "T33 log ring streams the router console lines")

    # ---- 萌娘立绘静态素材 ----
    stt, body, loc = raw("GET", "/router/assets/qwen-chan.png")
    ok(stt == 200 and "PNG fake mascot" in body, "T34 mascot asset served from gw-assets/")
    stt, body, loc = raw("GET", "/router/assets/..%2Fstrata-router.py")
    ok(stt == 404, "T35 asset path traversal blocked")
    stt, body, loc = raw("GET", "/router/assets/evil.txt")
    ok(stt == 404, "T36 only whitelisted image names served")
    stt, body, loc = raw("GET", "/router/assets/jbmono-latin.woff2")
    ok(stt == 200 and body[:4] == "wOF2", "T36b the console font ships and serves as a woff2 asset")

    # ---- 引擎档案 info ----
    s, h = req("GET", "/router/metrics?model=aaa-qwen")
    j = json.loads(h)
    ok(s == 200 and j["live"]["state"] == "idle" and "totals" in j and "history" in j,
       "T40 GET /router/metrics proxies the Monitor payload")
    s, h = req("GET", "/router/info")
    j = json.loads(h)
    ok(s == 200 and set(j["models"]) == {"aaa-qwen", "bbb-sc117"}
       and j["models"]["aaa-qwen"].get("max_context") == 524288, "T37 /router/info aggregates health info")

    # ---- ux v7: curated static facts from the model json (works even offline) ----
    cfg = j["models"]["aaa-qwen"].get("cfg") or {}
    ok(cfg.get("quant") == "pack-q9", "T62a cfg quant from --pack basename")
    ok(cfg.get("kv") == "z9z9" and cfg.get("rope") == "lame x2", "T62b cfg kv/rope")
    ok(cfg.get("drafting") == "drafty" and cfg.get("spec") == "4", "T62c drafting + spec")
    ok(cfg.get("idle_unload_s") == 1800 and cfg.get("reasoning_effort") == "medium"
       and (cfg.get("sampling") or {}).get("top_k") == 20, "T62d idle + effort + sampling defaults")
    ok("cfg" in j["models"]["bbb-sc117"], "T62e cfg key present even without extra config")
    ok(set(j["models"]["aaa-qwen"]["cfg"]) == set(j["models"]["bbb-sc117"]["cfg"]),
       "T64 uniform cfg schema — identical keys on every model, never drop-then-missing")

    # ---- ux v9: console lifetime parity with the legacy gateway -------------
    _bk = open(os.path.join(ROOT, "gw", "backends.py"), encoding="utf-8").read()
    _cf = open(os.path.join(ROOT, "gw", "config.py"), encoding="utf-8").read()
    _wj = open(os.path.join(ROOT, "gw", "winjob.py"), encoding="utf-8").read()
    ok("from . import winjob" in _bk and "from serve import winjob" not in _bk,
       "T65a repo-bundled winjob: no dependency on the engine's serve package")
    ok("CreateJobObjectW" in _wj and "SetInformationJobObject" in _wj
       and "AssignProcessToJobObject" in _wj and "KILL_ON_JOB_CLOSE" in _wj,
       "T65b kill-on-close Job Object implemented with ctypes only")
    ok("stdout=subprocess.DEVNULL" not in _bk,
       "T65c backend children keep the console: engine logs stream into the cmd window")
    ok('"STRATA_ROUTER_PORT"' in _cf and "def router_port" in _cf and "return 18075" in _cf
       and _cf.count("18075")>=2 and '"18080"' not in _cf,
       "T66 default router port is 18075 (env > gateway.json > default) — the engine's own 18080 stays out of config")

    # ---- ux v8: auto-generate tags + dossier from the LOADED model ----
    A.loaded = True
    s, h = req("POST", "/router/gendossier", {"model": "aaa-qwen", "lang": "zh"})
    j = json.loads(h)
    L = j.get("langs") or {}
    ok(s == 200 and isinstance(L.get("zh", {}).get("tags"), list) and len(L["zh"]["tags"]) >= 1
       and L["zh"].get("dossier") and L.get("en", {}).get("tags") and L["en"].get("dossier"),
       "T63a gendossier 200 pens both tongues in one click: zh+en tags & dossiers")
    ok(all(ord(c) < 128 for c in (L.get("en", {}).get("dossier") or "x")),
       "T63a2 the English slot actually carries English — not Chinese dragged along")
    s, h = req("POST", "/router/gendossier", {"model": "no-such-model"})
    ok(s == 404, "T63b unknown model -> 404")
    A.loaded = False
    s, h = req("POST", "/router/gendossier", {"model": "aaa-qwen"})
    ok(s == 409, "T63c model not loaded -> 409")
    A.loaded = True

    # ---- 看门狗：闲置自动卸载/驻留转场进事件流 ----
    A.loaded = True
    time.sleep(3.2)
    s, h = req("GET", "/router/events")
    ok(any("became resident" in e["text"] for e in json.loads(h)["events"]), "T38 watchdog notes a resident gain")
    A.loaded = False
    time.sleep(3.2)
    s, h = req("GET", "/router/events")
    ok(any("left the GPU on its own" in e["text"] for e in json.loads(h)["events"]), "T39 watchdog notes an idle unload")
    s, h = req("GET", "/router/events")
    c0 = sum("aaa-qwen became resident" in e["text"] for e in json.loads(h)["events"])
    A.loaded = True
    time.sleep(3.2)
    s, h = req("GET", "/router/events")
    evs1 = json.loads(h)["events"]
    ok(sum("aaa-qwen became resident" in e["text"] for e in evs1) == c0 + 1,
       "T41a watchdog logs a self transition exactly once")
    s, h = req("POST", "/load", {"model": "aaa-qwen"})
    time.sleep(3.2)
    s, h = req("GET", "/router/events")
    evs2 = json.loads(h)["events"]
    ok(s == 200 and any(e["text"].startswith("aaa-qwen loaded via the console") for e in evs2)
       and sum("aaa-qwen became resident" in e["text"] for e in evs2) == c0 + 1,
       "T41b router-caused transitions are not duplicated by the watchdog")
    s, h = req("GET", "/gateway")
    ok(all(p in h for p in ('id="train-src"', 'id="t-save"',
       "prefill_tok_s_mean", "gpu_pcie_rx_mb", "disk_read_mb", "hit_rate",
       "解码速度", "显存专家缓存", "上下文填充", 'id="eng-kv"', "inf-card",
       "尚无请求记录", "requests_kept", "evbtn",
       'data-r="toggle"', "statechip", "Strata 本体", 'id="archsvg"')),
       "T42 monitor parity + card-back training form (no MCP) + merged load toggle + live values chips")
    ok(all(p not in h for p in ("logbox", 'id="drawer-settings"', "moncard", "量化解剖",
       'id="drawer-mcp"', "loadMcp", "mcp-box", "DDR5", 'data-r="unload"',
       'data-r="badge"', "驻在中")),
       "T43 old structures removed (MCP drawer, log, gauge, anatomy, DDR5 typo, split buttons, top badge)")
    src_txt = open(os.path.join(ROOT, "strata-router.py"), encoding="utf-8").read()
    for _m in sorted(os.listdir(os.path.join(ROOT, "gw"))):
        if _m.endswith(".py"):
            src_txt += open(os.path.join(ROOT, "gw", _m), encoding="utf-8").read()
    _capp = open(os.path.join(ROOT, "console", "app.js"), encoding="utf-8").read()
    ok(all(p in h for p in ('id="archsvg"', 'data-sig', "m.n++",
                            "m.t=e.t",
                            'selectModel(loadedNow[0].model'))
       and 'marker-end="url(#aha)"' in _capp and "function archLink" in _capp
       and "pre_res = backend.resident() is True" in src_txt
       and 'elif op == "unload" and pre_res and not now_res' in src_txt,
       "T44 arch straight lines, monitor follows resident model, events merged xN + no-flicker sig, "
       "console events only on real transitions")

    # ---- 视频素材 + 背景开关 + Monitor 行数钉死 ----
    c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=15)
    c.request("GET", "/router/assets/bg-loop.mp4", headers={"Range": "bytes=10-29"})
    r = c.getresponse(); body = r.read()
    etag = r.getheader("ETag")
    ok(r.status == 206 and len(body) == 20
       and r.getheader("Content-Range") == "bytes 10-29/3000"
       and r.getheader("Accept-Ranges") == "bytes"
       and r.getheader("Content-Type") == "video/mp4" and etag,
       "T45 video asset: 206 Range slice + Accept-Ranges + ETag + video/mp4")
    c.request("GET", "/router/assets/bg-loop.mp4", headers={"If-None-Match": etag or ""})
    r = c.getresponse(); r.read()
    ok(r.status == 304, "T46 asset ETag revalidation answers 304")
    c.request("GET", "/router/assets/bg-loop.mp4", headers={"Range": "bytes=-10"})
    r = c.getresponse(); body = r.read(); c.close()
    ok(r.status == 206 and len(body) == 10
       and r.getheader("Content-Range") == "bytes 2990-2999/3000",
       "T47 suffix Range bytes=-10 serves the tail slice")
    s2, h2 = req("GET", "/gateway")
    ok(all(p in h2 for p in ('id="bgstage"', 'id="bgvid"', 'id="bgmask"',
       "router/assets/bg-loop.mp4", 'data-bg="off"', 'data-bg="bg"', 'data-bg="solo"',
       'id="seg-bg"', 'id="vid-sound"', "stratagw.bgmode", "stratagw.bgsound",
       "#bgstage.solo", "#bgstage{position:fixed;inset:0", 'id="ctlbar"')),
       "T48 video bg controls (off/bg/solo + sound) + fixed full-viewport stage in page")
    ok(all(p in h2 for p in ("var TROWS=10", "class=\"phr\"", "min-height:3.4em",
       "min-height:1.5em", "CFGNOTE", "表内显示最近 "))
       and "slice(0,12)" not in h2 and "最近 12 条" not in h2
       and 'colspan="9" style="text-align:center' not in h2,
       "T49 monitor table pinned to 10 rows (placeholders keep height stable; no jump on chip click)")

    # ---- T51 (Phase 11 + T1 truth-up #16): engine endpoint degradation ----
    # v0.2.16 truth: /props and /slots are REAL endpoints (pinned below at
    # T67/T68), so the missing-endpoint mirror gets a genuinely absent probe:
    # the real serve has no /queue* - the stub now mirrors that 404 too.
    s, h = req("GET", "/queue?model=aaa-qwen")
    ok(s == 404 and "no-such-endpoint" in h,
       "T51a endpoint genuinely absent from the engine mirrors as 404 (body from the engine, not the gateway)")
    s2, _h = req("GET", "/router/version")
    ok(s2 == 200, "T51b gateway stays healthy after a proxied 404")

    # ---- T1 truth-up (#16): the stub answers the real v0.2.16 face ----
    s, h = req("GET", "/router/props?model=aaa-qwen")
    try:
        pj = json.loads(h)
    except ValueError:
        pj = {}
    ok(s == 200 and isinstance(pj.get("default_generation_settings"), dict)
       and pj.get("total_slots") == 1 and pj.get("model_alias") == "aaa-qwen"
       and isinstance(pj.get("is_sleeping"), bool)
       and isinstance(pj.get("chat_template"), str) and len(pj["chat_template"]) < 200
       and {"chat_template_caps", "modalities", "models_autoload", "model_path",
            "build_info"} <= set(pj),
       "T67 GET /router/props: 200 llama.cpp-shape subset (stub keeps the template short, not 30 KB)")
    s, h = req("GET", "/router/slots?model=aaa-qwen")
    try:
        sj = json.loads(h)
    except ValueError:
        sj = None
    ok(s == 200 and isinstance(sj, list) and len(sj) == 1
       and set(sj[0]) == {"id", "n_ctx", "is_processing", "n_prompt_tokens"},
       "T68 GET /router/slots: llama.cpp-shape row while the engine holds the model")
    s, h = req("GET", "/router/slots?model=bbb-sc117")
    ok(s == 200 and json.loads(h) == [],
       "T68b /slots on an engine that is not loaded: [] (llama.cpp semantics)")

    s, h = req("GET", "/router/metrics?model=aaa-qwen")
    try:
        mj = json.loads(h)
    except ValueError:
        mj = {}
    cc = mj.get("conversation_cache")
    ok(isinstance(cc, dict) and set(cc) == {
        "enabled", "budget_mib", "slots", "parked", "bytes", "evictions", "parks",
        "restores", "last_event", "last_tokens", "last_at", "refused", "refused_total",
        "last_refused", "requests", "requests_reused", "reused_tokens", "prompt_tokens",
        "last_reused", "last_prompt"},
       "T69 /metrics carries the conversation_cache top-level object with every pinned field")
    ok(isinstance(cc, dict) and isinstance(cc["enabled"], bool)
       and set(cc["refused"]) == {"ram_floor", "budget"},
       "T69b conversation_cache types hold: enabled bool, refused {ram_floor,budget}")
    lv = mj.get("live", {})
    ok(all(k in lv for k in ("state", "queued", "phase", "reused", "tok_s_mean")),
       "T69c /metrics live carries the richer queue fields (state/queued/phase/reused/tok_s_mean)")
    B.cc_mode = "off"
    o = json.loads(req("GET", "/router/metrics?model=bbb-sc117")[1])
    ok(o.get("conversation_cache", {}).get("enabled") is False,
       "T69d cc_mode=off stub: cache present with enabled:false (T4 degraded render)")
    B.cc_mode = "absent"
    o = json.loads(req("GET", "/router/metrics?model=bbb-sc117")[1])
    ok("conversation_cache" not in o,
       "T69e cc_mode=absent stub: the whole key missing (old-engine degrade for T4)")
    B.cc_mode = "on"

    s, h = req("GET", "/api/expert-heat?model=aaa-qwen")
    try:
        hj = json.loads(h)
    except ValueError:
        hj = {}
    HL, HE = 4, 8
    ok(s == 200 and hj.get("configured") is True and hj.get("layers") == HL
       and hj.get("experts") == HE and hj.get("ranked") == HL * HE
       and len(hj.get("rank", [])) == HL * HE
       and hj.get("every_min") == 10 and isinstance(hj.get("saved_at"), (int, float)),
       "T70 GET /api/expert-heat (catch-all passthrough): configured 200, shrunken 4x8 but shape-true")
    rk = hj.get("rank", [])
    ok(len(rk) == HL * HE and all(sorted(rk[l * HE:(l + 1) * HE]) == list(range(HE))
                                  for l in range(HL)),
       "T70b rank[] is row-major layers x experts; every layer block a 0-based within-layer permutation")
    ok(rk[0] == 0 and rk[2 * HE + 3] == 1,
       "T70c known-cell pin: rank[2*8+3]==1 (row-major l*E+e, 0=hottest - design record §9.1)")
    A.heat = "off"    # the endpoint-absent face: like a serve with no profile
    s, h = req("GET", "/api/expert-heat?model=aaa-qwen")
    ok(s == 404,
       "T70d heat off-face switch: unconfigured engine answers 404 on the same route")
    # (#22, T7) the SECOND hidden face: the endpoint exists and answers 200,
    # but the engine reports configured:false - webui experts.js gates its tab
    # on configured:true, and the console section must stay hidden the same way
    # (design record §5 degraded table). stub_common and the sim kit carry the
    # face byte-identically (H10 pin in test_console_ctl).
    A.heat = "false"
    s, h = req("GET", "/api/expert-heat?model=aaa-qwen")
    fj = json.loads(h) if s == 200 else {}
    ok(s == 200 and fj.get("configured") is False and fj.get("rank") == [],
       "T70e configured:false face proxied verbatim: 200 + configured:false + empty rank")
    ok(set(fj) == {"configured", "every_min", "saved_at", "layers", "experts", "ranked", "rank"},
       "T70f the configured:false face keeps the full key set (no invented keys)")
    A.heat = "on"
    s, h = req("GET", "/gateway")
    ok('id="experts-sec"' in h and 'id="heat-body"' in h and "api/expert-heat" in h,
       "T70g the served console carries the hidden heat shell + the catch-all fetch path")

    # ---- T71 (issue #18, T3): the queue face over the wire ----
    # /v1/status via the catch-all: the console's second queue feed. The stub
    # kit speaks the REAL v0.2.16 face (compat-baseline console_routes pin),
    # so the catch-all must mirror it 200, and the queue variants must be
    # switchable: parallel slots present/absent, admission set/unset.
    s, h = req("GET", "/v1/status?model=aaa-qwen")
    try:
        v1j = json.loads(h)
    except ValueError:
        v1j = {}
    ok(s == 200 and isinstance(v1j.get("concurrency"), dict)
       and {"serving", "requested"} <= set(v1j["concurrency"])
       and "in_flight" in (v1j.get("activity") or {})
       and v1j.get("model") == "aaa-qwen",
       "T71a catch-all /v1/status answers the real concurrency+activity face")
    A.par, A.adm = True, True
    mj = json.loads(req("GET", "/router/metrics?model=aaa-qwen")[1])
    lvp = mj.get("live", {})
    ok(isinstance(lvp.get("slots"), list) and lvp.get("slots")
       and {"slot", "state"} <= set(lvp["slots"][0])
       and lvp.get("waiting") is not None and lvp.get("admitting") is not None,
       "T71b parallel variant: live carries slots[]+waiting+admitting (shape per strata-face)")
    ok(lvp.get("admission") == {"total": 9, "ram_floor": 2, "budget": 7},
       "T71c admission variant: live.admission {total,ram_floor,budget} verbatim")
    A.par, A.adm = False, False
    lv0 = json.loads(req("GET", "/router/metrics?model=aaa-qwen")[1])["live"]
    ok("slots" not in lv0 and "waiting" not in lv0 and "admission" not in lv0,
       "T71d default variant: no slots/waiting/admission keys at all (old-engine degrade path)")
    ck = [k["key"] for k in json.loads(req("GET", "/router/config?model=aaa-qwen")[1])["keys"]]
    ok("max_queue" in ck, "T71e run-config exposes max_queue so the cap stat can light up")
    s, h = req("GET", "/gateway")
    ok('id="mon-queue"' in h and "q.slots.empty" in h and "429 admission_full" in h,
       "T71f the served console carries the queue panel shell + cap legend + slot strings")

    # ---- T72 (#20, T5): /mcp rides the existing proxy in three faces -------
    # The MCP card fetches router/mcp?model= through the PROXY_PATHS mapping
    # (zero new gateway routes). The stub speaks every face the card degrades
    # against: mixed servers (full), configured-but-empty, and an old engine
    # that 404s /mcp (mirrored verbatim per T51). tri-state defaults to
    # "empty" — the face this suite has always seen.
    A.mcp_mode = "full"
    s, h = req("GET", "/router/mcp?model=aaa-qwen")
    mj = json.loads(h) if s == 200 else {}
    sv = mj.get("servers") or []
    ok(s == 200 and len(sv) == 3,
       "T72a full face proxied: servers[] carries connected/error/disabled rows")
    ok(bool(sv) and all(k in sv[0] for k in ("name", "transport", "status", "tools")),
       "T72b server entries carry the strata-face field set (name/transport/status/tools)")
    ok(any(x.get("status") == "error" and x.get("error") for x in sv),
       "T72c the errored server carries the engine's own error text verbatim")
    ok(any(isinstance(x.get("tools"), list) and len(x["tools"]) > 8 for x in sv),
       "T72d one server lists more tools than the card's visible cap (10 > 8)")
    ok(mj.get("tools") == 12,
       "T72e the payload's tools total rides the engine number (10+0+2)")
    A.mcp_mode = "empty"
    s, h = req("GET", "/router/mcp?model=aaa-qwen")
    ok(s == 200 and json.loads(h).get("servers") == [],
       "T72f empty face: 200 + servers:[] (the card's mcp.none state)")
    A.mcp_mode = "absent"
    s, h = req("GET", "/router/mcp?model=aaa-qwen")
    ok(s == 404 and "no-such-endpoint" in h,
       "T72g absent face: the old-engine 404 mirrors through (the card's mcp.nodata state)")
    A.mcp_mode = "empty"

    # ---- T50 (Phase 11): /router/version + engine-root resolution ----
    s, h = req("GET", "/router/version")
    try:
        vj = json.loads(h)
    except ValueError:
        vj = {}
    want = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "VERSION"),
                encoding="utf-8").read().strip()
    ok(s == 200 and vj.get("version") == want and "commit" in vj,
       "T50a GET /router/version -> {version==VERSION, commit}")

    # STRATA_HOME redirect: server.py path follows the env; resolver finds it
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.'); import gw.config as c; print(c.server_py())"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
        env=dict(os.environ, STRATA_HOME="/nonexistent-engine"))
    ok("/nonexistent-engine/serve/server.py" in r.stdout,
       "T50b gw.config.server_py() honours STRATA_HOME (and names the legacy path when absent)")
    r2 = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.'); import gw.config as c; "
         "print(c.resolve_python())"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
        env=dict(os.environ, STRATA_HOME="/nonexistent-engine",
                 STRATA_PYTHON="/opt/weird/python"))
    ok("/opt/weird/python" in r2.stdout,
       "T50c resolve_python honours STRATA_PYTHON override")
    # ---- v0.2.16 layout: the serve wrapper, the venv and setup.py moved one
    # level down under terminal/. The ladders must find them there, and an
    # old-layout install must keep resolving at the top level.
    _l16 = tempfile.mkdtemp(prefix="gw-l16-")
    os.makedirs(os.path.join(_l16, "terminal", "serve"))
    with open(os.path.join(_l16, "terminal", "serve", "server.py"), "w") as _fh:
        _fh.write("# serve\n")
    os.makedirs(os.path.join(_l16, "terminal", ".venv", "bin"))
    with open(os.path.join(_l16, "terminal", ".venv", "bin", "python"), "w") as _fh:
        _fh.write("# py\n")
    r16 = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.'); import gw.config as c; "
         "print(c.server_py()); print(c.resolve_python())"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
        env=dict(os.environ, STRATA_HOME=_l16, STRATA_PYTHON=""))
    ok(os.path.join(_l16, "terminal", "serve", "server.py") in r16.stdout
       and os.path.join(_l16, "terminal", ".venv", "bin", "python") in r16.stdout,
       "T50d server_py() and resolve_python() find the v0.2.16 terminal/ layout")
    _l16b = tempfile.mkdtemp(prefix="gw-l16b-")
    os.makedirs(os.path.join(_l16b, "serve"))
    with open(os.path.join(_l16b, "serve", "server.py"), "w") as _fh:
        _fh.write("# legacy serve\n")
    r16b = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.'); import gw.config as c; "
         "print(c.server_py()); print(c.resolve_python())"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
        env=dict(os.environ, STRATA_HOME=_l16b, STRATA_PYTHON=""))
    ok(os.path.join(_l16b, "serve", "server.py") in r16b.stdout
       and "terminal" not in r16b.stdout,
       "T50e an old-layout install still resolves at the top level (no regression)")
    # ---- T26b: a dead engine must confess, not hide behind "unreachable" ----
    # hand-drop a third card whose serve answers /health but whose engine is
    # gone (every POST resets); its config names an engine log with the real
    # reason inside. load must surface THAT line, not a bare connection error.
    _dead_log = os.path.join(ROOT, "ddd-dead-engine.log")
    with open(_dead_log, "w", encoding="utf-8") as f:
        f.write("[strata] 2026-11-08 21:01:03 engine started: strata.exe --serve ...\n"
                "strata-q36: context 524288 cells, prompt chunk 2048, 0.00 GiB of VRAM free\n"
                "strata-q36: not enough VRAM left for the hybrid experts' buffers and slots "
                "(1760 MiB needed, 0 MiB free): use fewer slots, a shorter --max-context\n")
    with open(os.path.join(ROOT, "strata-ddd-dead.json"), "w") as f:
        json.dump({"model_name": "ddd-dead", "port": 18094, "api_key": "",
                   "log": _dead_log}, f)
    got3 = False
    deadline = time.time() + 20
    while time.time() < deadline:
        s, h = req("GET", "/router/backends")
        try:
            got3 = any(b["model"] == "ddd-dead" for b in json.loads(h)["backends"])
        except (ValueError, KeyError):
            got3 = False
        if got3:
            break
        time.sleep(0.5)
    ok(got3, "T26b0 hand-dropped config is picked up by the scan watcher")
    s, h = req("POST", "/load", {"model": "ddd-dead"})
    j = json.loads(h) if s else {}
    msg = (j.get("error") or {}).get("message", "")
    ok(s == 502 and "not enough VRAM" in msg,
       "T26b1 502 carries the engine log's real reason, not just 'unreachable'")
    s, h = req("GET", "/router/events")
    ok(any("not enough VRAM" in e["text"] for e in json.loads(h)["events"]),
       "T26b2 the same reason lands in the live feed")

    # (T27 fit preflight pins live in test_model_admin, whose sim-gateway
    #  section carries STRATA_HOME; the switch router here has no setup.py)

    # ---- T28: the residency clock — countdown, and a way to extend the stay ----
    req("POST", "/load", {"model": "aaa-qwen"})        # make the clock's subject resident
    req("POST", "/v1/chat/completions",
        {"model": "aaa-qwen", "messages": [{"role": "user", "content": "hi"}]})
    s, h = req("GET", "/router/backends")
    row = next(b for b in json.loads(h)["backends"] if b["model"] == "aaa-qwen")
    ok(row.get("loaded") is True and row.get("off_in_s") is not None
       and 0 < row["off_in_s"] <= 1800,
       "T28a a served model shows the engine's idle clock ticking down")
    before = row["off_in_s"]
    time.sleep(3.0)                                  # let the countdown tick measurably
    s, h = req("GET", "/router/backends")
    mid = next(b for b in json.loads(h)["backends"] if b["model"] == "aaa-qwen")["off_in_s"]
    ok(mid < before,
       "T28b1 the countdown really ticks: three seconds of quiet shows in it")
    req("POST", "/v1/chat/completions",
        {"model": "aaa-qwen", "messages": [{"role": "user", "content": "hi"}]})
    s, h = req("GET", "/router/backends")
    row = next(b for b in json.loads(h)["backends"] if b["model"] == "aaa-qwen")
    ok(row["off_in_s"] > mid,
       "T28b fresh inference rewinds the countdown - the card knows what keeps a model awake")
    s, h = req("POST", "/router/poke", {"model": "aaa-qwen"})
    ok(s == 200 and json.loads(h).get("ok") is True,
       "T28c POST /router/poke keeps the resident model awake")
    s, h = req("POST", "/router/poke", {"model": "no-such-model"})
    ok(s == 404,
       "T28d poking a model that was never enlisted: a clean 404, not a guess")

    # ---- T29: the event river starts with a source marker ----
    s, h = req("GET", "/router/events")
    kinds = [e.get("kind") for e in json.loads(h)["events"]]
    ok("boot" in kinds,
       "T29c the river remembers where the gateway woke up")

    # ---- T30: the release whisper — behind, cached, silent when dark ----
    s, h = req("GET", "/router/release")
    d = json.loads(h)
    ok(s == 200 and d.get("reachable") is True and d.get("behind") is True
       and d.get("latest") == "9.9.9" and "releases/tag/v9.9.9" in (d.get("url") or ""),
       "T30a the gateway notices a newer release and hands the console the link")
    h0 = REL.hits
    req("GET", "/router/release"); req("GET", "/router/release")
    ok(REL.hits == h0,
       "T30b the answer is cached: polling the console never hammers GitHub")
    s2, h2 = req("GET", "/router/release")   # (no query backdoors: an SSRF gift
    d = json.loads(h2)                       #  waiting to happen - the probe URL
    ok(d.get("behind") is not None,          #  only ever comes from the env)
       "T30c1 the cached answer keeps serving without a second hit")
    import subprocess as _sp
    r = _sp.run([sys.executable, "-c",
                 "import sys;sys.path.insert(0,'.');"
                 "from gw import release_check as R;"
                 "print(R.check().get('reachable'),R.check().get('behind'))"],
                cwd=ROOT, capture_output=True, text=True, timeout=30,
                env=dict(os.environ, GW_RELEASE_API="http://127.0.0.1:1/nope"))
    ok("False None" in r.stdout,
       "T30c an unreachable GitHub whispers nothing - the banner stays asleep")

    print("ALL PASS")
finally:
    router.terminate(); router.wait(timeout=10)
    shutil.rmtree(ROOT, ignore_errors=True)
