"""events.py - the console log ring, the transition timeline and the watchdog."""
from __future__ import annotations

import time
from collections import deque

from . import config

LOG: deque = deque(maxlen=500)         # (epoch, line) for /router/log
EVENTS: deque = deque(maxlen=120)     # (epoch, kind, text) for the console timeline
_intent: dict = {}                     # name -> epoch: a transition the router caused


class Tee:
    """Mirror every print() into an in-memory ring so /router/log can stream the
    gateway console to the web page. Backend subprocesses write to the shared
    console through their own OS handles, not through us: they stay out of this
    ring - it is the router's own voice."""
    def __init__(self, stream) -> None:
        self.stream, self.partial = stream, ""

    def write(self, s):
        self.stream.write(s)
        self.partial += s
        while "\n" in self.partial:
            line, self.partial = self.partial.split("\n", 1)
            if line.strip():
                LOG.append((time.time(), line))
        return len(s)

    def flush(self):
        self.stream.flush()


def revent(kind: str, text: str) -> None:
    EVENTS.append((time.time(), kind, text))


def note_intentional(name: str) -> None:
    _intent[name] = time.time()


def _watchdog() -> None:
    """Record state moves the router did NOT cause - the engine's own idle timer,
    or the image-generation bridge unloading it - on the timeline. Moves we made
    in the last 10 s are already logged, so they are skipped here."""
    from . import backends
    last: dict[str, bool] = {}
    while True:
        time.sleep(config.WATCH_S)
        try:
            for b in list(backends.BACKENDS.values()):
                r = b.alive() and b.resident() is True
                prev = last.get(b.name, False)
                if prev and not r and time.time() - _intent.get(b.name, 0.0) > 10.0:
                    revent("unload", f"{b.name} left the GPU on its own (idle timer or the generation bridge)")
                elif r and not prev and time.time() - _intent.get(b.name, 0.0) > 10.0:
                    revent("load", f"{b.name} became resident")
                last[b.name] = r
        except Exception:
            pass
