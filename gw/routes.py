"""routes.py - the HTTP surface: API aggregation, console page, static assets,
proxies to the resident backend, and the load/unload orchestration."""
from __future__ import annotations

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import unquote

from . import backends
from . import cards
from . import config
from . import console
from . import events
from . import gpu_free

WATCH_JS = ('<script>/*strataGatewayWatch*/'
            '(function(){var n=0;'
            'setInterval(function(){'
            'fetch("/router/backends").then(function(r){return r.json()}).then(function(d){'
            'var any=(d.backends||[]).some(function(b){return b.loaded});'
            'if(!any){n++}else{n=0}'
            'if(n>=2){location.replace("/gateway")}'
            '}).catch(function(){})'
            '},2000);})();</script>')


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

    def _json(self, status: int, obj, headers: dict | None = None) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), headers=headers)

    def _forward_raw(self, backend: backends.Backend, method: str, path_qs: str, body: bytes,
                     extra_timeout: float = 900.0) -> int:
        """Stream the backend's answer through, byte for byte."""
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
        if self._auth():
            headers["Authorization"] = self._auth()
        req = urlrequest.Request(backend.base + path_qs, data=body if body else None,
                                 headers=headers, method=method)
        try:
            resp = config.OPENER.open(req, timeout=extra_timeout)
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

    def _forward_html(self, backend: backends.Backend, path_qs: str) -> None:
        """GET a webUI HTML page, buffer it, inject the unload-watcher before </body>
        (marker check guards double injection), answer with a corrected length."""
        headers = {"Content-Type": self.headers.get("Content-Type", "text/html")}
        if self._auth():
            headers["Authorization"] = self._auth()
        req = urlrequest.Request(backend.base + path_qs, headers=headers, method="GET")
        try:
            resp = config.OPENER.open(req, timeout=15)
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

    def _serve_file(self, name: str, sub: str) -> None:
        """Shared static serving: Range + ETag so a <video> streams properly and
        revalidation after a file swap is a 304 instead of a re-download."""
        p = os.path.join(config.ROOT, sub, name)
        try:
            size = os.path.getsize(p)
            etag = '"%s-%x-%x"' % (name, size, int(os.path.getmtime(p)))
        except OSError:
            return self._json(404, {"error": {"message": "no such file"}})
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
            return self._json(404, {"error": {"message": "no such file"}})
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")   # refreshed files show up right away
        self.send_header("ETag", etag)
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (lo, hi, size))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (ConnectionResetError, BrokenPipeError):
            pass

    # ---- routing -------------------------------------------------------
    def _models_all(self) -> None:
        out = []
        for b in sorted(backends.BACKENDS.values(), key=lambda x: x.name):
            try:
                req = urlrequest.Request(f"{b.base}/v1/models",
                                         headers={"Authorization": self._auth()} if self._auth() else {})
                with config.OPENER.open(req, timeout=8) as r:
                    out.extend(json.loads(r.read() or b"{}").get("data") or [])
            except HTTPError as e:
                if e.code in (401, 403):          # the backend is up and wants the key: pass it on
                    body = e.read()
                    return self._send(e.code, body)
                b.spawn()                         # down: (re)start it, it lists itself when up
            except (URLError, OSError, ValueError):
                b.spawn()                         # down: (re)start it, it lists itself when up
        self._json(200, {"object": "list", "data": out,
                         "router": {"service": "strata-router", "port": config.ROUTER_PORT}})

    def _health_all(self) -> None:
        blist = []
        for b in sorted(backends.BACKENDS.values(), key=lambda x: x.name):
            alive = b.alive()
            if not alive:
                b.spawn()
            blist.append({"model": b.name, "port": b.port, "alive": alive,
                          "loaded": b.resident() if alive else None,
                          "busy": backends.busy_info(b.name)})
        self._json(200, {"status": "ok", "service": "strata-router", "port": config.ROUTER_PORT,
                         "backends": blist})

    def _prepare_load(self, target: backends.Backend) -> None:
        """The target is not resident: free the machine for it, then wait for its
        API (a freshly spawned lazy backend binds within seconds or so)."""
        if not target.alive():
            target.spawn()
            if not target.wait_alive(config.LOAD_WAIT_S):
                raise RuntimeError(f"backend {target.name} did not come up on :{target.port}")
        if target.resident() is not True:            # None (fresh spawn) counts as "about to load"
            for b in sorted(backends.BACKENDS.values(), key=lambda x: x.name):
                if b is not target and b.alive():
                    b.unload()
            if not gpu_free.ensure_card():
                raise gpu_free.CardNotFree("the external holder still holds the GPU "
                                           "(a generation task may still be running)")

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
            body = console.render(config.ROUTER_PORT).encode("utf-8")
            return self._send(200, body, "text/html; charset=utf-8",
                             headers={"Cache-Control": "no-cache"})
        if method == "GET" and path == "/router/backends":
            return self._health_all()
        if method == "GET" and path == "/router/gpu":
            return self._json(200, gpu_free.gpu_stats())
        if method == "GET" and path == "/router/events":
            return self._json(200, {"events": [{"t": t, "kind": k, "text": x}
                                               for t, k, x in reversed(list(events.EVENTS))]})
        if method == "GET" and path == "/router/log":
            n = 200
            m2 = re.search(r"(?:^|&)n=([0-9]+)", qs)
            if m2:
                n = max(0, min(500, int(m2.group(1))))
            return self._json(200, {"lines": [[t, line] for t, line in list(events.LOG)[-n:]]})
        if method == "GET" and path == "/router/version":
            return self._json(200, {"version": console.version(),
                                      "commit": console.git_commit()})
        if method == "GET" and path == "/router/info":
            return self._json(200, backends.router_info())
        if method == "GET" and path == "/router/cards":
            return self._json(200, cards.load_cards())
        if method == "DELETE" and path.startswith("/router/cards/"):
            st, obj = cards.delete_card(unquote(path[len("/router/cards/"):]))
            return self._json(st, obj)
        if method == "GET" and path.startswith("/router/assets/"):
            # Static art + loop video for the console (gw-assets/).
            name = unquote(path[len("/router/assets/"):])
            if not config.ASSET_NAME.match(name):
                return self._json(404, {"error": {"message": "no such asset"}})
            return self._serve_file(name, "gw-assets")
        if method == "GET" and path.startswith("/router/uploads/"):
            # User-uploaded art: same serving pipeline, its own name whitelist.
            name = unquote(path[len("/router/uploads/"):])
            if not cards.UPLOAD_NAME.match(name):
                return self._json(404, {"error": {"message": "no such upload"}})
            return self._serve_file(name, os.path.join("gw-assets", "uploads"))
        if method == "DELETE" and path.startswith("/router/uploads/"):
            name = unquote(path[len("/router/uploads/"):])
            if not cards.UPLOAD_NAME.match(name):
                return self._json(404, {"error": {"message": "no such upload"}})
            try:
                os.remove(os.path.join(config.ROOT, "gw-assets", "uploads", name))
                return self._json(200, {"ok": True, "deleted": name})
            except OSError:
                return self._json(404, {"error": {"message": "no such upload"}})
        if method == "GET" and path in ("/", "/monitor"):
            if not backends.any_resident():
                self.send_response(302)
                self.send_header("Location", "/gateway")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._forward_html(backends.pick_backend(None), self.path)
        if method == "POST" and path == "/router/upload":
            ctype_hdr = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype_hdr:
                return self._json(415, {"error": {"message": "multipart/form-data required"}})
            cl = int(self.headers.get("Content-Length", "0") or 0)
            if cl > cards.MAX_UPLOAD + 8192:
                return self._json(413, {"error": {"message": "too large (max 5 MB)"}})
            raw = self._read_body()
            parsed = cards.parse_multipart(raw, ctype_hdr)
            if parsed is None:
                return self._json(415, {"error": {"message": "no file part in the form"}})
            st, obj = cards.handle_upload(*parsed)
            return self._json(st, obj)
        body = self._read_body() if method == "POST" else b""
        if method == "POST" and path == "/router/gpu/free":
            force = False
            if body:
                try:
                    jj = json.loads(body)
                    force = bool(isinstance(jj, dict) and jj.get("force"))
                except ValueError:
                    pass
            res = gpu_free.free_console(force)
            if res is None:
                return self._json(503, {"error": {"message": "external VRAM holder unreachable (not running?)"}})
            return self._json(200, res)
        if method == "POST" and path == "/router/gendossier":
            try:
                jj = json.loads(body) if body else {}
            except ValueError:
                jj = {}
            if not isinstance(jj, dict):
                jj = {}
            name = str(jj.get("model") or "")
            b = next((x for x in backends.BACKENDS.values() if x.name == name), None)
            if b is None:
                return self._json(404, {"error": {"message": "unknown model"}})
            # three truths, not one catch-all 409: an engine mid-task flaps its
            # /v1/models probe — that deserves "try again", not "clock it in".
            r = b.resident()
            if r is None:
                time.sleep(1.2)
                r = b.resident()
            # master's rule: one resident operative is enough — the one on duty
            # ghost-writes the dossier of a card whose model is off post.
            author, subject = b, None
            if r is not True:
                author = next((x for x in backends.BACKENDS.values()
                               if x is not b and x.alive() and x.resident() is True), None)
                if author is None:
                    if r is None:
                        return self._json(503, {"error": {"message": "engine isn't answering the models probe (busy?) — retry shortly"}})
                    return self._json(409, {"error": {"message": "no operative is resident — clock any card in first"}})
                subject = b
            g = author.gendossier(str(jj.get("lang") or "zh"), subject=subject)
            if g is None:
                return self._json(502, {"error": {"message": "engine returned no self-description — try again"}})
            return self._json(200, g)
        if method == "POST" and path == "/router/cards":
            try:
                jj = json.loads(body) if body else {}
            except ValueError:
                jj = {}
            if not isinstance(jj, dict):
                jj = {}
            st, obj = cards.merge_card(str(jj.get("model") or ""), jj.get("card") or {})
            return self._json(st, obj)
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
        backend = backends.pick_backend(model)
        if backend is None:
            return self._json(503, {"error": {"message": "no strata-*.json configs found"}})
        if path.startswith("/router/"):
            if method in ("GET", "POST") and path in config.PROXY_PATHS:
                return self._forward_raw(backend, method, path[len("/router"):], body)
            return self._json(404, {"error": {"message": "unknown router endpoint"}})
        if method == "POST" and path in config.GEN_PATHS:
            pre_res = backend.resident()
            backends.set_busy(backend.name, "load")   # a harness-triggered cold load shows
            try:                                     # on the console too, ring and all
                try:
                    self._prepare_load(backend)
                except gpu_free.CardNotFree as e:
                    return self._json(503, {"error": {"message": str(e) + "; let the task finish, press the console "
                                                      "\u8ba9\u5361 (give-card) button, or retry"}},
                                      headers={"Retry-After": "15"})
                except RuntimeError as e:
                    return self._json(502, {"error": {"message": str(e)}})
                if pre_res is not True:
                    events.revent("load", f"{backend.name} cold-loaded for a harness request")
                    events.note_intentional(backend.name)
                for attempt in range(6):          # the other model's unload may still be in flight
                    status = self._forward_raw(backend, method, self.path, body)
                    if status != 503 or attempt == 5:
                        return
                    if backend.resident() is not True:
                        for b in sorted(backends.BACKENDS.values(), key=lambda x: x.name):
                            if b is not backend and b.alive():
                                b.unload()
                        gpu_free.poke(gpu_free.settings())  # already waited once; just re-poke
                        time.sleep(5.0)
                    else:
                        return
                return
            finally:
                backends.clear_busy(backend.name)
        if method == "POST" and path in ("/load", "/unload"):
            op = "load" if path == "/load" else "unload"
            backends.set_busy(backend.name, op)   # visible on /router/backends until done
            pre_res = backend.resident() is True  # bridge re-pokes /unload while nothing is
            t0 = time.time()                      # resident: only a real move deserves an event
            try:
                if op == "load":
                    try:
                        self._prepare_load(backend)   # spawn 目标 + 卸其它模型 + 等外部服务放卡
                    except gpu_free.CardNotFree as e:
                        events.revent("error", f"{backend.name} load blocked: the external holder kept the card")
                        return self._json(503, {"error": {"message": str(e)}},
                                          headers={"Retry-After": "15"})
                    except RuntimeError as e:
                        events.revent("error", f"{backend.name} load blocked: {e}")
                        return self._json(502, {"error": {"message": str(e)}})
                backends.set_preferred(backend.name)
                backends.invalidate_resident()
                status = self._forward_raw(backend, method, self.path, body)
                events.note_intentional(backend.name)
                if status < 400:
                    now_res = backend.resident()
                    backends.cache_resident(backend, now_res)
                    if op == "load" and not pre_res and now_res:
                        events.revent("load", f"{backend.name} loaded via the console in {int(time.time() - t0)} s")
                    elif op == "unload" and pre_res and not now_res:
                        events.revent("unload", f"{backend.name} unloaded via the console")
                return status
            finally:
                backends.clear_busy(backend.name)
        return self._forward_raw(backend, method, self.path, body)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    def do_OPTIONS(self):
        self._route("OPTIONS")
