#!/usr/bin/env python3
"""test_pet.py — Phase 7: draggable desktop pet + chat window.
P-series asserts the stage/chat DOM, the shipped example pet.png, the
_pet dossier entry round-tripping through POST /router/cards, and the
app.js/css wiring (drag>8px, petpos persistence, loaded-gating, sway).
Stub gateway only. Expect: ALL PASS."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, REPO  # noqa: E402

F = []
def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        F.append(name)

gw = Gateway(["petdemo-model"], [18095])
try:
    def wait_ready():
        for _ in range(60):
            s, _b = gw.req("GET", "/router/backends")
            if s == 200:
                return
            import time; time.sleep(0.5)
    wait_ready()

    # ---- P1/P2: DOM contract on the page ----
    s, page = gw.req("GET", "/gateway")
    ok(s == 200, "P1a /gateway 200")
    for frag in ('id="petstage"', 'id="petchat"', 'id="petimg"', 'id="ptf"', 'id="pc-close"'):
        ok(frag in page, "P1 " + frag + " present")
    ok("router/assets/pet.png" in page, "P2 pet src ships pointing at the example art")

    # ---- P3: the example asset serves ----
    s, raw, hdrs = gw.req_bin("GET", "/router/assets/pet.png")
    ok(s == 200 and raw[:4] == b"\x89PNG", "P3a pet.png served 200 as PNG bytes")
    ok("image/png" in (hdrs.get("Content-Type") or ""), "P3b pet.png Content-Type image/png")
    ok(len(raw) > 400, "P3c served pet.png non-trivial size")

    # ---- P4: _pet dossier persists via the cards endpoint ----
    s, body = gw.req("GET", "/router/cards")
    cards0 = json.loads(body)
    ok("_pet" in cards0 and str(cards0["_pet"].get("art", "")).endswith("pet.png"),
       "P4a cards.json ships a _pet entry with art path")
    s, body = gw.req("POST", "/router/cards", {"model": "_pet", "card": {"art": "router/uploads/pet-alt.png"}})
    ok(s == 200, "P4b POST /router/cards for _pet 200")
    s, body = gw.req("GET", "/router/cards")
    ok(json.loads(body)["_pet"]["art"] == "router/uploads/pet-alt.png",
       "P4c _pet.art round-trips (rewritten value read back)")

    # ---- P5/P6/P7: front-end wiring markers ----
    app = open(os.path.join(REPO, "console", "app.js"), encoding="utf-8").read()
    ok("stratagw.petpos" in app and "STRATA_PET" in app,
       "P5 pet position persisted + prefs hook exported")
    ok(">8" in app or "8)" in app.replace(" ", ""),
       "P6 drag threshold 8px (move vs click)")
    ok('ptf.src' in app and "loaded" in app,
       "P7 chat iframe gated on a loaded backend")
    ok("pc-note" in app and "pc-load" in app,
       "P7b no-resident note reuses the load action")
    css = open(os.path.join(REPO, "console", "style.css"), encoding="utf-8").read()
    ok("#petstage" in css and "position:fixed" in css and "z-index:70" in css,
       "P8 pet stage fixed above the bar")
    ok("@keyframes sway" in css, "P8b idle sway keyframes shipped")
    ok("#petimg" in css[css.index("@media (prefers-reduced-motion"):]
       if "@media (prefers-reduced-motion" in css else False,
       "P8c reduced-motion kills the sway")
    ok("#petchat" in css and "#ptf" in css, "P8d chat panel styled")
finally:
    gw.close()

print("ALL PASS" if not F else "FAILED: " + ", ".join(F))
sys.exit(0 if not F else 1)
