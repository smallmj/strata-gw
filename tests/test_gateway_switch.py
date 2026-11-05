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
ROUTER_SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "strata-router.py")
ROUTER_PORT = 18090

class Stub:
    """假后端: /health、/v1/models、POST /load、POST /unload；"/" 与 "/monitor" 回 HTML 标记，其余 GET 回纯文本标记。"""
    def __init__(self, name, port):
        self.name, self.port, self.loaded = name, port, False
        self.load_calls, self.unload_calls = 0, 0
        self.shared, self.posts = {}, []
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
                                                      "help": "unload after N idle seconds", "kind": "number"}],
                                            "note": "used from the next start"})
                if p == "/mcp":
                    return self._send(200, {"servers": [], "tools": 0})
                if p == "/status":
                    return self._send(200, {"busy": False, "who": outer.name})
                if p == "/metrics":
                    return self._send(200, {
                        "engine": {"model": outer.name, "max_context": 524288, "version": "0.1.56",
                                   "expert_slots": 7711, "expert_cache_mib": 14451, "kv": "k8v4", "spec": 4},
                        "stub_tag": f"stub:{outer.name}",
                        "live": {"state": "idle", "queued": 0, "phase": None, "prompt_tokens": None,
                                 "prompt_read": None, "prompt_total": None, "generated": None,
                                 "max_tokens": None, "elapsed_s": None, "tok_s": None,
                                 "prefill_tok_s_mean": None},
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
                        "time": 123.0})
                if p == "/v1/models":
                    return self._send(200, json.dumps({"object": "list", "data": [
                        {"id": outer.name, "object": "model", "owned_by": "stub",
                         "status": {"value": "loaded" if outer.loaded else "unloaded"}}]}))
                if p in ("/", "/monitor"):
                    return self._send(200, f"<html><body>stub:{outer.name}</body></html>", "text/html; charset=utf-8")
                return self._send(200, f"stub:{outer.name}", "text/plain")
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

CF = HolderStub(18097)
MA = "qwen3.8-flash-next-iq3_s" if VIS else "aaa-qwen"
MB = "sc117-qwen3.8-flash-next-abliterated-iq3_s" if VIS else "bbb-sc117"
A = Stub(MA, 18095)      # 名字排序第一 = 无驻留且无偏好时的默认
B = Stub(MB, 18096)
for name, port in ((MA, 18095), (MB, 18096)):
    with open(os.path.join(ROOT, f"strata-{name}.json"), "w") as f:
        json.dump({"model_name": name, "port": port, "api_key": ""}, f)
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

env = dict(os.environ, STRATA_ROUTER_PORT=str(ROUTER_PORT), STRATA_ROUTER_ANYHOST="1",
           GW_GPU_URLS="http://127.0.0.1:18097",      # live stub holder, idle
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
    ok(s == 200 and "模型加载台" in h
       and 'id="gforce"' in h and "强制让卡" in h and "让卡" in h
       and 'id="sec-settings"' in h and 'id="sec-about"' in h
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

    st, h, loc = raw("GET", "/monitor")
    ok(st == 200 and "stub:bbb-sc117" in h and "strataGatewayWatch" in h,
       "T18 /monitor served with watch while resident")

    s, h = req("POST", "/unload", {"model": "bbb-sc117"})
    time.sleep(3.5)                                    # 等 3s 驻留缓存过期
    st, h, loc = raw("GET", "/monitor")
    ok(st == 302 and loc == "/gateway", "T19 /monitor bounces to gateway after unload")

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
    j = json.loads(res2[0][1])
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

    # ---- 引擎档案 info ----
    s, h = req("GET", "/router/metrics?model=aaa-qwen")
    j = json.loads(h)
    ok(s == 200 and j["live"]["state"] == "idle" and "totals" in j and "history" in j,
       "T40 GET /router/metrics proxies the Monitor payload")
    s, h = req("GET", "/router/info")
    j = json.loads(h)
    ok(s == 200 and set(j["models"]) == {"aaa-qwen", "bbb-sc117"}
       and j["models"]["aaa-qwen"].get("max_context") == 524288, "T37 /router/info aggregates health info")

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
    ok(all(p in h for p in ('id="drawer-sampling"', 'id="drawer-config"',
       "prefill_tok_s_mean", "gpu_pcie_rx_mb", "disk_read_mb", "hit_rate",
       "解码速度", "显存专家缓存", "上下文填充", 'id="eng-kv"', "inf-card",
       "尚无请求记录", "requests_kept", "evbtn",
       'data-r="toggle"', "statechip", "Strata 本体", 'id="dg-backends"')),
       "T42 monitor parity + 2 drawers (no MCP) + merged load toggle + live values chips")
    ok(all(p not in h for p in ("logbox", 'id="drawer-settings"', "moncard", "量化解剖",
       'id="drawer-mcp"', "loadMcp", "mcp-box", "DDR5", 'data-r="unload"',
       'data-r="badge"', "驻在中")),
       "T43 old structures removed (MCP drawer, log, gauge, anatomy, DDR5 typo, split buttons, top badge)")
    src_txt = open(os.path.join(ROOT, "strata-router.py"), encoding="utf-8").read()
    for _m in sorted(os.listdir(os.path.join(ROOT, "gw"))):
        if _m.endswith(".py"):
            src_txt += open(os.path.join(ROOT, "gw", _m), encoding="utf-8").read()
    ok(all(p in h for p in ('marker-end="url(#arM)"', "M166 118L196 118", 'data-sig', "m.n++",
                            "m.t=e.t",
                            "selectModel(loadedNow[0].model"))
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
       "#bgstage.solo", "#bgstage{position:fixed;inset:0", 'class="vidbar"')),
       "T48 video bg controls (off/bg/solo + sound) + fixed full-viewport stage in page")
    ok(all(p in h2 for p in ("var TROWS=10", "class=\"phr\"", "min-height:3.4em",
       "min-height:1.5em", "CFGNOTE", "表内显示最近 "))
       and "slice(0,12)" not in h2 and "最近 12 条" not in h2
       and 'colspan="9" style="text-align:center' not in h2,
       "T49 monitor table pinned to 10 rows (placeholders keep height stable; no jump on chip click)")
    print("ALL PASS")
finally:
    router.terminate(); router.wait(timeout=10)
    shutil.rmtree(ROOT, ignore_errors=True)
