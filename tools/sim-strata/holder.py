# protocol snapshot: Strata v0.2.11 / engine 0.1.57 (pinned 2026-11-07)
"""sim-strata holder.py - the FAKE image service (demo stand-in for a
generator that owns the GPU). Mirrors tests/stub_common.py's StubHolder
protocol (/system_stats + /free + /queue + /interrupt) so gw/gpu_free.py
speaks to it exactly like to a live image-service holder - numbers move,
nothing renders. Default port 18288 (demo range, never a production port).
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

M = 1048576
TOTAL = 24576          # MiB pretend VRAM
BUSY_FREE = 22000      # before a free
REL_FREE = 24200       # after /free: the card looks empty
RELEASE_S = 30.0       # stays empty this long...
RETAKE_S = 60.0        # ...then climbs back fully by then

st = {"freed_at": None, "queue_pending": [["pid1", "x"], ["pid2", "x"]],
      "queue_running": [{"prompt_id": "run1"}], "free_calls": 0,
      "interrupt_calls": 0}


def _vram_free():
    if st["freed_at"] is None:
        return BUSY_FREE
    dt = time.time() - st["freed_at"]
    if dt < RELEASE_S:
        return REL_FREE
    if dt > RETAKE_S:
        st["freed_at"] = None
        return BUSY_FREE
    k = (dt - RELEASE_S) / (RETAKE_S - RELEASE_S)
    return int(REL_FREE - (REL_FREE - BUSY_FREE) * k)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        self._raw(code, json.dumps(obj), "application/json")

    def _raw(self, code, text, ctype):
        b = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/system_stats":
            return self._send(200, {
                "system": {"ram_total": 65536 * M, "ram_used": 40000 * M},
                "devices": [{"name": "cuda:0", "type": "cuda", "index": 0,
                             "vram_total": TOTAL * M, "vram_free": _vram_free() * M}]})
        if p == "/queue":
            return self._send(200, {"queue_pending": st["queue_pending"],
                                    "queue_running": st["queue_running"]})
        if p == "/":
            return self._raw(200, "sim image service (holder) - nothing renders",
                             "text/plain")
        return self._send(404, {"error": "nope"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n)
        p = self.path.split("?")[0]
        if p == "/free":
            st["free_calls"] += 1
            st["freed_at"] = time.time()
            return self._send(200, {})
        if p == "/interrupt":
            st["interrupt_calls"] += 1
            st["queue_running"] = []
            st["freed_at"] = time.time()
            return self._send(200, {})
        if p == "/queue":
            try:
                dele = (json.loads(body.decode() or b"{}") or {}).get("delete") or []
            except ValueError:
                dele = []
            st["queue_pending"] = [row for row in st["queue_pending"]
                                   if row[0] not in dele]
            return self._send(200, {})
        return self._send(404, {})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18288
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print("sim image service (holder) serving :%d - pretend VRAM only" % port,
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
