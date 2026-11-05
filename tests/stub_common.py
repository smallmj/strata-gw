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


class Stub:
    """Fake lazy backend: /health, /v1/models, POST /load, POST /unload;
    '/' + '/monitor' serve an HTML marker, every other GET a text marker."""
    def __init__(self, name, port):
        self.name, self.port, self.loaded = name, port, False
        self.load_calls, self.unload_calls = 0, 0
        self.shared, self.posts = {}, []
        self.max_context = 524288
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
                                                      "help": "unload after N idle seconds", "kind": "number"}],
                                            "note": "used from the next start"})
                if p == "/mcp":
                    return self._send(200, {"servers": [], "tools": 0})
                if p == "/status":
                    return self._send(200, {"busy": False, "who": outer.name})
                if p == "/metrics":
                    return self._send(200, {
                        "engine": {"model": outer.name, "max_context": outer.max_context,
                                   "version": "0.1.56", "expert_slots": 7711,
                                   "expert_cache_mib": 14451, "kv": "k8v4", "spec": 4},
                        "stub_tag": f"stub:{outer.name}",
                        "live": {"state": "idle", "queued": 0, "phase": None, "prompt_tokens": None,
                                 "prompt_read": None, "prompt_total": None, "generated": None,
                                 "max_tokens": None, "elapsed_s": None, "tok_s": None,
                                 "prefill_tok_s_mean": None},
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


class Gateway:
    """Copy the repo tree (minus junk) into a temp dir, plant strata-*.json
    configs for the given model names, spawn the gateway, wait until ready."""
    _SKIP = {".git", "testdir", "tests", "__pycache__", "strata-router.py.orig"}

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
                json.dump({"model_name": name, "port": port, "api_key": ""}, f)
            self.cfg_paths[name] = p
        os.makedirs(os.path.join(self.root, "gw-assets"), exist_ok=True)
        open(os.path.join(self.root, "gw-assets", "bg-loop.mp4"), "wb").write(b"VFIX" * 750)
        open(os.path.join(self.root, "gw-assets", "qwen-chan.png"), "wb").write(b"\x89PNG fake mascot")
        open(os.path.join(self.root, "gw-assets", "sc117-chan.png"), "wb").write(b"\x89PNG fake mascot")
        env = dict(os.environ, STRATA_ROUTER_PORT=str(ROUTER_PORT), STRATA_ROUTER_ANYHOST="1",
                   STRATA_COMFY_FREE_WAIT="4", STRATA_WATCH_S="2")
        if holder_port:
            env["STRATA_COMFY_URL"] = f"http://127.0.0.1:{holder_port}"
        if extra_env:
            env.update(extra_env)
        self.proc = subprocess.Popen([sys.executable, os.path.join(self.root, "strata-router.py")], env=env)

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
