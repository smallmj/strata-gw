# protocol snapshot: Strata v0.2.16 / engine 0.1.62 (pinned 2026-11-19)
"""sim-strata serve/server.py - the FAKE engine, spoken to by the gateway.

The gateway spawns exactly the real command line:
    python serve/server.py --engine strata --config <cfg.json> \
        --host 0.0.0.0 --port N --api-key K --lazy
This handler mirrors tests/stub_common.py's Stub protocol (health / models /
load / unload / metrics / settings / config / status) so the gateway cannot
tell it from a stub - except every reply is canned and nothing computes.
v0.2.16 truth-up (#16): the face matches the real serve - /props /slots answer
their llama.cpp-style shapes, /api/expert-heat exists in its two variants,
/metrics carries conversation_cache and the richer live fields, there is NO
fake /monitor page (the real serve 404s it), and unknown paths 404.
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

# truth-up switches (#16, mirrors tests/stub_common.py): the degraded faces
# T3/T4/T7 render against. CCACHE=on|off|absent drives /metrics
# conversation_cache; HEAT=on|false|off drives /api/expert-heat (off = 404,
# exactly like a real serve with no expert profile configured; false = 200
# with configured:false and an empty rank - the SECOND hidden face, #22); MCP=
# full|empty|absent drives /mcp for the T5 card (empty is the face an
# unconfigured serve answers; absent = 404, an old engine without the route).
CCACHE_MODE = os.environ.get("SIM_STRATA_CCACHE", "on")
HEAT_MODE = os.environ.get("SIM_STRATA_HEAT", "on")
MCP_MODE = os.environ.get("SIM_STRATA_MCP", "empty")
HEAT_LAYERS, HEAT_EXPERTS = 4, 8    # kit-shrunken (real box: 48x512), shape-true


def _conv_cache(mode):
    """v0.2.16 /metrics top-level conversation_cache (strata-face field set):
    every field present, values fake but types real."""
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
    one. Values fake, shape real. Byte-identical face to tests/stub_common.py;
    absent is handled by the route (404), not by this factory."""
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
            # tri-state switch (T5): SIM_STRATA_MCP=full answers the mixed
            # servers face; =absent 404s like an old engine without the route.
            if MCP_MODE == "absent":
                return self._send(404, {"error": "no-such-endpoint: " + p})
            return self._send(200, _mcp_payload(MCP_MODE))
        if p == "/metrics":
            t = time.time() % 600.0
            wave = (math.sin(t / 60.0 * 2 * math.pi) + 1) / 2
            _m = {
                "engine": {"model": STATE["name"], "max_context": STATE["max_context"],
                           "version": STATE["version"], "expert_slots": 4096,
                           "expert_cache_mib": 512, "kv": "k8v4", "spec": 4,
                           **_facts_engine()},
                "sim_tag": "sim-strata",
                # queue variants EXEMPT from the kit (review #5): live.parallel
                # and live.admission are stub-only switches (T71) — the kit
                # speaks the v0.2.16 single face (strata-face live table has
                # no admission object at all; parallel is off-single-slot).
                # The panel's variant faces are pinned at the stub seam instead.
                "live": {"state": "idle" if not STATE["loaded"] else "ready",
                         "queued": 0, "phase": None, "prompt_tokens": None,
                         "prompt_read": None, "prompt_total": None,
                         "generated": None, "max_tokens": None, "elapsed_s": None,
                         "tok_s": None, "reused": 0, "tok_s_mean": None,
                         "prefill_tok_s_mean": None},
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
                "time": time.time()}
            if CCACHE_MODE != "absent":
                _m["conversation_cache"] = _conv_cache(CCACHE_MODE)
            return self._send(200, _m)
        if p == "/v1/models":
            return self._send(200, json.dumps({"object": "list", "data": [
                {"id": STATE["name"], "object": "model", "owned_by": "sim-strata",
                 "status": {"value": "loaded" if STATE["loaded"] else "unloaded"}}]}))
        if p == "/props":
            # llama.cpp-style /props (v0.2.16 face): real shape,
            # kit keeps only what the console renders - no 30 KB template.
            return self._send(200, {
                "default_generation_settings": {"max_tokens": 8192, "temperature": 1.0,
                                                "top_p": 0.95, "top_k": 20},
                "total_slots": 1, "model_alias": STATE["name"],
                "chat_template": "<short kit template, not the real 30 KB text>",
                "chat_template_caps": {"thinking": True, "tools": True},
                "modalities": ["text"], "models_autoload": [],
                "is_sleeping": not STATE["loaded"],
                "model_path": "/kit/models/" + STATE["name"] + ".gguf",
                "build_info": {"version": STATE["version"]}})
        if p == "/slots":
            # llama.cpp-style /slots: [] when the model is not loaded.
            if not STATE["loaded"]:
                return self._send(200, [])
            return self._send(200, [{"id": 0, "n_ctx": 8192, "is_processing": False,
                                     "n_prompt_tokens": 0}])
        if p == "/v1/status":
            # real v0.2.16 face (#18 pin: the queue panel's second feed) —
            # same shape the serve docs name, honest subset for the kit.
            return self._send(200, {"service": "strata", "model": STATE["name"],
                                    "loaded": STATE["loaded"], "auto_load": True,
                                    "structured_output": True, "engine": STATE["version"],
                                    "uptime_s": 123.0, "cache_max_tokens": 8192,
                                    "context": {"n_ctx": STATE["max_context"]},
                                    "concurrency": {"serving": 1, "requested": 1},
                                    "dialects": ["chat"], "vision": True,
                                    "image_generation": True,
                                    "activity": {"in_flight": 0},
                                    "last_timings": {}, "vram": {}, "machine": {}})
        if p == "/api/expert-heat":
            # tri-state switch (#16 + #22): SIM_STRATA_HEAT=off -> 404 (no
            # profile configured); false -> 200 configured:false empty rank;
            # anything else -> the grid face. Mirrors tests/stub_common.py.
            if HEAT_MODE == "off":
                return self._send(404, {"error": "no expert profile configured"})
            return self._send(200, _heat_payload(HEAT_MODE != "false"))
        if p == "/":
            return self._send(200, "<html><body>sim engine on :%d</body></html>"
                              % STATE["port"], "text/html; charset=utf-8")
        # v0.2.16 truth (#16): the real serve 404s every unknown path - it has
        # NO /monitor (the old kit page was a lie), no /queue, no /experts.
        return self._send(404, {"error": "no-such-endpoint: " + p})

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
