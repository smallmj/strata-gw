#!/usr/bin/env python3
"""test_deck_geometry.py — the card deck's RENDERED geometry.

The deck is pure CSS, so every other console test (string asserts over style.css)
is blind to it: the third card used to sit 14-20px past #cardwrap{overflow:hidden}
and the phone breakpoint hid the second card behind the main one. This boots a
stub gateway with THREE cards, drives the real page in headless chromium, and
asserts the invariant the CSS comment promises: every visible neighbour stays
inside the wrapper AND shows a real sliver past the card in front of it.

Skips (not fails) when playwright/chromium is missing on this machine.
Expect: ALL PASS."""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stub_common import Gateway, ROUTER_PORT  # noqa: E402

F = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        F.append(name)


WIDTHS = (1440, 1120, 900, 700, 380)      # desktop widths -> the phone breakpoints
MODELS = ["deck-a-7b", "deck-b-13b", "deck-c-32b"]
PORTS = [18117, 18118, 18119]

gw = Gateway(MODELS, PORTS)
try:
    for _ in range(80):
        s, _b = gw.req("GET", "/router/version")
        if s == 200:
            break
        time.sleep(0.25)

    probe = os.path.join(HERE, "deck-geometry.mjs")
    r = subprocess.run(["node", probe, "http://127.0.0.1:%d/" % ROUTER_PORT],
                       capture_output=True, text=True, timeout=180)
    out = (r.stdout or "").strip()
    if out == "NEED-PLAYWRIGHT":
        print("SKIP deck geometry: playwright not installed "
              "(npm i -g playwright && playwright install chromium)")
    else:
        ok(r.returncode == 0 and out.startswith("["),
           "G0 headless probe ran (rc=%d) %s" % (r.returncode, (r.stderr or "")[-140:]))
        rows = json.loads(out) if out.startswith("[") else []
        ok(len(rows) == len(WIDTHS), "G1 measured all %d widths (got %d)" % (len(WIDTHS), len(rows)))
        for row in rows:
            w = row["width"]
            for cls in ("n1", "n2"):
                c = row.get(cls)
                if not c:
                    ok(False, "G2 w=%d %s exists (the deck holds 3 cards)" % (w, cls))
                    continue
                over, sliver = float(c["overWrap"]), float(c["pastOn"])
                ok(over <= 0.5,
                   "G2 w=%-4d %s right edge is inside the wrapper (over=%s)"
                   % (w, cls, c["overWrap"]))
                ok(sliver >= 1.0,
                   "G3 w=%-4d %s keeps a sliver past the main card (sliver=%s)"
                   % (w, cls, c["pastOn"]))
            main_w, wrap_w = int(row["mainWidth"]), float(row["wrapWidth"])
            ok(main_w <= wrap_w - 28,
               "G4 w=%-4d main card keeps its side margin (%d in %s)"
               % (w, main_w, row["wrapWidth"]))
finally:
    gw.close()

print("ALL PASS" if not F else "FAILED: " + ", ".join(F))
sys.exit(1 if F else 0)
