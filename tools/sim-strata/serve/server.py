# protocol snapshot: Strata v0.2.12 / engine 0.1.58 (pinned 2026-11-08)
"""sim-strata serve/server.py - the FAKE engine, spoken to by the gateway.

The gateway spawns exactly the real command line:
    python serve/server.py --engine strata --config <cfg.json> \
        --host 0.0.0.0 --port N --api-key K --lazy
This handler mirrors tests/stub_common.py's Stub protocol (health / models /
load / unload / metrics / settings / config / status) so the gateway cannot
tell it from a stub - except every reply is canned and nothing computes.
"""
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = {"loaded": False, "name": "sim-model", "max_context": 131072,
         "version": "0.0.0-sim", "port": 0}


def _version():
    try:
        with open(os.path.join(os.path.dirname(HERE), "engine", "BUILD.json"),
                  encoding="utf-8") as f:
            return str(json.load(f).get("version") or "0.0.0-sim")
    except (OSError, ValueError):
        return "0.0.0-sim"


def _canned(prompt):
    p = (prompt or "").lower()
    if "self-report" in p:
        return json.dumps({"tags": ["demo", "sim-environment", "no-real-inference"],
                           "dossier": "Test operative: a pretend model from the "
                                      "sim-strata kit. No weights, no GPU - every "
                                      "line it speaks is canned on purpose."})
    if "translate" in p:
        return "Translated (canned): this sentence came from the sim kit, " \
               "not from any real model."
    if "third-person" in p:
        return "Ghost-written bio (canned): the operative on duty describes " \
               "itself in the third person, pretending to think."
    return "Test operative on post: this is a canned reply from the sim kit, " \
           "no real inference happened."


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/health":
            return self._send(200, {"status": "ok", "max_context": STATE["max_context"],
                                    "model": STATE["name"], "images": True,
                                    "api_key": False, "loaded": STATE["loaded"],
                                    "service": "strata"})
        if p == "/settings":
            return self._send(200, {"shared": {}, "defaults": {}})
        if p == "/config":
            return self._send(200, {"file": "sim.json", "keys": [],
                                    "note": "sim engine: no tunables"})
        if p == "/status":
            return self._send(200, {"busy": False, "who": STATE["name"]})
        if p == "/mcp":
            return self._send(200, {"servers": [], "tools": 0})
        if p == "/metrics":
            t = time.time() % 600.0
            wave = (math.sin(t / 60.0 * 2 * math.pi) + 1) / 2
            return self._send(200, {
                "engine": {"model": STATE["name"], "max_context": STATE["max_context"],
                           "version": STATE["version"], "expert_slots": 4096,
                           "expert_cache_mib": 512, "kv": "k8v4", "spec": 4},
                "sim_tag": "sim-strata",
                "live": {"state": "idle" if not STATE["loaded"] else "ready",
                         "queued": 0, "phase": None, "prompt_tokens": None,
                         "prompt_read": None, "prompt_total": None,
                         "generated": None, "max_tokens": None, "elapsed_s": None,
                         "tok_s": None, "prefill_tok_s_mean": None},
                "requests": [], "requests_kept": 0,
                "totals": {"requests": 0, "prompt_tokens": 0, "reused": 0,
                           "output_tokens": 0, "prompt_ms": 0.0, "decode_ms": 0.0,
                           "since": 100.0, "drafts_offered": 0, "drafts_accepted": 0},
                "hardware": {"gpu_util": int(20 + 30 * wave),
                             "gpu_mem_used": int(6e9 + 4e9 * wave),
                             "gpu_mem_total": int(24 * 2**30),
                             "gpu_temp": 60 + int(6 * wave), "gpu_power": 120.0 + 80 * wave,
                             "cpu": 12.0 + 10 * wave, "ram_used": int(20e9 + 5e9 * wave),
                             "ram_total": int(32e9)},
                "hardware_static": {"gpu_name": "SimGPU (fake)", "gpu_count": 1,
                                    "cpu_name": "sim host", "cores": 8, "threads": 16},
                "history": {"tok_s": [], "gpu_util": [20, 40],
                            "gpu_mem_used": [int(6e9), int(9e9)],
                            "gpu_temp": [60, 65], "gpu_power": [120, 180]},
                "time": time.time()})
        if p == "/v1/models":
            return self._send(200, json.dumps({"object": "list", "data": [
                {"id": STATE["name"], "object": "model", "owned_by": "sim-strata",
                 "status": {"value": "loaded" if STATE["loaded"] else "unloaded"}}]}))
        if p in ("/", "/monitor"):
            return self._send(200, "<html><body>sim engine on :%d</body></html>"
                              % STATE["port"], "text/html; charset=utf-8")
        if p in ("/props", "/slots"):
            return self._send(404, {"error": "endpoint not in this engine build"})
        return self._send(200, "sim engine", "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n)
        p = self.path.split("?")[0]
        if p == "/v1/chat/completions":
            prompt = ""
            try:
                d = json.loads(body.decode() or b"{}")
                for msg in reversed(d.get("messages") or []):
                    if msg.get("role") in ("user", "system"):
                        prompt = str(msg.get("content") or "")
                        break
            except ValueError:
                pass
            return self._send(200, json.dumps(
                {"choices": [{"message": {"content": _canned(prompt)}}]}))
        if p == "/load":
            STATE["loaded"] = True
            return self._send(200, json.dumps({"status": "loaded", "echo": body.decode()}))
        if p == "/unload":
            STATE["loaded"] = False
            return self._send(200, json.dumps({"status": "unloaded"}))
        if p in ("/settings", "/config"):
            return self._send(200, {"ok": True})
        return self._send(200, "{}")


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="sim-strata serve")
    ap.add_argument("--engine"); ap.add_argument("--config")
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--api-key"); ap.add_argument("--lazy", action="store_true")
    a = ap.parse_args()
    STATE["version"] = _version()
    STATE["port"] = a.port
    if a.config:
        try:
            with open(a.config, encoding="utf-8") as f:
                cfg = json.load(f)
            STATE["name"] = str(cfg.get("model_name") or STATE["name"])
            args = cfg.get("args") or []
            for i, x in enumerate(args):
                if x == "--max-context" and i + 1 < len(args):
                    STATE["max_context"] = int(args[i + 1])
        except (OSError, ValueError):
            pass
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print("sim engine serving :%d as %s (fake, no inference)" % (a.port, STATE["name"]),
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
