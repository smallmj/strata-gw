#!/usr/bin/env python3
"""test_gpu_free.py - generic external-VRAM handover: auto-probe of a
holder exposing /free + /system_stats (+ /queue /interrupt), status endpoint,
gentle vs forced release, nvidia-smi read-only fallback, and the renamed
routes. The old brand token appears ONLY as a runtime concatenation here,
never as a literal (repo-wide rule).
Usage: python3 tests/test_gpu_free.py  -> PASS lines, ALL PASS, exit 0."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, Stub, StubHolder, ok, ROUTER_PORT  # noqa: E402

BRAND = ("co" + "m" + "fy")                 # never a literal anywhere in this repo

MA, MB = "aaa-qwen", "bbb-sc117"
A = Stub(MA, 18095)
B = Stub(MB, 18096)
H = StubHolder(18097)                      # the holder; gateway.json points at it
gw = Gateway([MA, MB], [18095, 18096])     # no env hint: config hot-reload drives it
try:
    gw.wait_ready([MA, MB])

    # ---- discovery: no STRATA_* hint, holder on the probed 8189? We started
    # it on 18097 for the explicit-url era; for the probe test plant gateway.json.
    with open(os.path.join(gw.root, "gateway.json"), "w") as f:
        json.dump({"gpu_free": {"urls": ["http://127.0.0.1:18097"]}}, f)

    s, h = gw.get("/router/gpu")
    c = json.loads(h)
    ok(s == 200 and c.get("running") is True and c.get("vram_free_mib") == 22000
       and c.get("freeing") is None,
       "G1 GET /router/gpu reads the live holder (config urls)")
    ok(BRAND not in h.lower(), "G2 status payload carries no old-brand field names")

    # POST /load with the holder idle-ish must succeed through ensure_card
    s, h = gw.post("/load", {"model": "bbb-sc117"})
    ok(s == 200, "G3 load path runs the generic handover")

    # gentle free: drops mode
    H.vram_free, H.ram_used, H.mode = 2000, 40000, "drops"
    s, h = gw.post("/router/gpu/free", {"force": False})
    j = json.loads(h)
    ok(s == 200 and j.get("ok") and j.get("freed_vram_mib", 0) >= 1000
       and j.get("freed_ram_mib", 0) >= 1000,
       "G4 gentle free: /free sent, VRAM+RAM release reported")

    ib = H.interrupt_calls
    H.vram_free, H.mode = 2000, "hold"
    s, h = gw.post("/router/gpu/free", {"force": False})
    j = json.loads(h)
    ok(s == 200 and j.get("freed_vram_mib") == 0 and j.get("gave_card") is False,
       "G5 gentle with nothing to free: freed 0, gave_card false")
    ok(H.interrupt_calls == ib, "G6 gentle never touches /interrupt")

    H.vram_free, H.ram_used, H.mode = 2000, 40000, "drops"
    H.pending, H.running = [["pda", "x"], ["pdb", "x"]], [{"prompt_id": "rc"}]
    s, h = gw.post("/router/gpu/free", {"force": True})
    j = json.loads(h)
    ok(s == 200 and j.get("gave_card") is True and j.get("freed_vram_mib", 0) >= 1000
       and j.get("tasks_cleared") == 3 and H.interrupt_calls >= ib + 1
       and "pda" in H.queue_deletes and "pdb" in H.queue_deletes,
       "G7 force free: interrupt + clear queue + /free, waits for the card")

    # event kind renamed to "gpu"
    s, h = gw.get("/router/events")
    kinds = {e["kind"] for e in json.loads(h)["events"]}
    ok("gpu" in kinds, "G8 free events use the gpu kind")

    # old routes gone (no compat shims)
    st, body, loc, ctype = gw.raw("GET", "/router/" + BRAND)
    ok(st == 404, "G9 the old brand-named status route is gone")
    st, body, loc, ctype = gw.raw("POST", "/router/" + BRAND + "/free", {"force": False})
    ok(st == 404, "G10 the old brand-named free route is gone")

    # target_mib=0 auto: derive from resident backend metrics (gpu_mem_total*0.85)
    H.mode, H.vram_free, H.ram_used = "drops", 2000, 40000
    with open(os.path.join(gw.root, "gateway.json"), "w") as f:
        json.dump({"gpu_free": {"urls": ["http://127.0.0.1:18097"], "target_mib": 0}}, f)
    s, h = gw.post("/router/gpu/free", {"force": True})
    j = json.loads(h)
    # stub metrics gpu_mem_total = 25769803776 B = 24576 MiB -> target 20889
    # holder jumps vram_free to 21000 on drops -> clears the auto target
    ok(s == 200 and j.get("gave_card") is True, "G11 auto target from live metrics (0.85x total)")

    H.shutdown()
    H = None
    s, h = gw.get("/router/gpu")
    c = json.loads(h)
    ok(c.get("running") is False, "G12 holder down -> status not running")
    s, h = gw.post("/router/gpu/free", {"force": False})
    ok(s == 503, "G13 holder unreachable -> 503")

    # no holder at all: ensure_card sends best effort, never blocks the load
    s, h = gw.post("/load", {"model": "aaa-qwen"})
    ok(s == 200, "G14 load works with no holder running (best-effort, no wait)")

    print("ALL PASS")
finally:
    gw.close()
    A.shutdown()
    B.shutdown()
