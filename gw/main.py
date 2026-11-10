"""main.py - startup wiring: scan configs, spawn lazy backends, start the
watchdog and the HTTP server; stop everything cleanly on exit."""
from __future__ import annotations

import os
import sys
import threading
from http.server import ThreadingHTTPServer

from . import backends
from . import config
from . import events
from . import routes
from . import sweep


def cleanup() -> None:
    """Stop the backend children. The winjob job is the real guarantee (it fires
    however this process ends); this just makes an ordinary exit tidier."""
    for b in list(backends.BACKENDS.values()):
        p = b.proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass


def main() -> None:
    sys.stdout = events.Tee(sys.stdout)
    # legacy semantics, restored (sweep.py): reap the old router/wrappers/engines
    # BEFORE anything is adopted - a restart then truly restarts, engines are our
    # own children (their logs stream into this window) and the VRAM card comes
    # back clean. Inert on non-Windows and when STRATA_SWEEP=0.
    sweep.sweep_boot()
    if os.name != "nt" and not os.environ.get("STRATA_ROUTER_ANYHOST"):
        print(f"[router] note: designed for the Strata box (Windows); running on "
              f"{sys.platform}", flush=True)
    found = backends.scan_configs()
    backends.BACKENDS.clear()
    backends.BACKENDS.update(found)
    backends._FP["sig"] = backends.fingerprint()
    if not backends.BACKENDS:
        print(f"[router] no strata-*.json found in {backends.scan_dirs()} - console "
              "will guide the first recruit (控制台将引导招募第一位特工)", flush=True)

    def on_close(signum, frame):                # the console window's X button
        cleanup()
        os._exit(0)

    if os.name == "nt":
        import signal
        try:
            signal.signal(signal.SIGBREAK, on_close)
        except (ValueError, OSError):
            pass
    for b in backends.BACKENDS.values():
        if not b.alive():
            b.spawn()
    threading.Thread(target=events._watchdog, daemon=True).start()
    threading.Thread(target=backends.watch_scan, daemon=True).start()
    config.ROUTER_PORT = config.router_port()
    httpd = ThreadingHTTPServer(("0.0.0.0", config.ROUTER_PORT), routes.Handler)
    httpd.daemon_threads = True
    names = ", ".join(f"{b.name}(:{b.port})" for b in sorted(backends.BACKENDS.values(), key=lambda x: x.name))
    print(f"[router] ready on :{config.ROUTER_PORT}  models: {names or '(none yet)'}", flush=True)
    from . import events as _ev
    _ev.revent("boot", "gateway woke up on :%s" % config.ROUTER_PORT)
    db = backends.default_backend()
    if db is not None:
        print(f"[router] default model: {db.name}", flush=True)
    print("[router] Ctrl+C or close this window to stop the gateway and the engines", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
