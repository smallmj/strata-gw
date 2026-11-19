#!/usr/bin/env python3
"""test_queue_gate.py - the generation gate: engine generation requests queue
behind a working external generator (running OR pending), go straight through
when it is idle or unreachable, never touch /load or status routes, and fail
open at the ceiling. Usage: python3 tests/test_queue_gate.py -> PASS lines,
ALL PASS, exit 0."""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, Stub, StubHolder, ok  # noqa: E402

MA, MB = "aaa-qwen", "bbb-sc117"
A = Stub(MA, 18095)
B = Stub(MB, 18096)
H = StubHolder(18097)          # the external generator stub
gw = Gateway([MA, MB], [18095, 18096], holder_port=18097,
             extra_env={"GW_QUEUE_POLL_S": "0.3", "GW_QUEUE_MAX_WAIT_S": "6"})
try:
    gw.wait_ready([MA, MB])

    def clear_soon(attr, delay=1.5):
        def run():
            time.sleep(delay)
            setattr(H, attr, [] if attr == "running" else [])
        t = threading.Thread(target=run, daemon=True)
        t.start()

    # Q1 holder idle -> the generation goes straight through
    # (one untimed warm-up first: the very first request rides the cold-load branch)
    gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    H.running, H.pending = [], []
    t0 = time.time()
    s, h = gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    ok(s == 200 and time.time() - t0 < 2.0, "Q1 idle holder: the request is not gated")

    # Q2 a RUNNING job gates the request until it ends
    H.running = [{"prompt_id": "run1"}]
    clear_soon("running", 1.5)
    t0 = time.time()
    s, h = gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    dt = time.time() - t0
    ok(s == 200 and dt >= 1.0, "Q2 running job: the request queued %.1f s then ran" % dt)

    # Q3 a PENDING job gates too (strict no-overlap)
    H.pending = [["pid1", "x"]]
    clear_soon("pending", 1.2)
    t0 = time.time()
    s, h = gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    dt = time.time() - t0
    ok(s == 200 and dt >= 1.0, "Q3 pending job: the request queued %.1f s then ran" % dt)

    # QG1/QG2 (issue #18): the gate's own hold is honest on /router/gpu —
    # present while the gate holds, gone the moment it stops (gw reporting
    # its OWN state is legal per ADR-0001; the engine fields never are).
    H.running = [{"prompt_id": "holdme"}]
    clear_soon("running", 2.0)
    _gt = threading.Thread(target=lambda: gw.post("/v1/chat/completions",
                                                  {"model": MA, "messages": []}),
                           daemon=True)
    _gt.start()
    time.sleep(0.8)
    s, h = gw.get("/router/gpu")
    gj = json.loads(h)
    ok(s == 200 and isinstance(gj.get("gen_gate"), dict)
       and gj["gen_gate"].get("waited_s", -1) >= 0,
       "QG1 while the gate holds, /router/gpu carries gen_gate.waited_s")
    _gt.join(timeout=15)
    gj = json.loads(gw.get("/router/gpu")[1])
    H.running, H.pending = [], []
    ok("gen_gate" not in gj,
       "QG2 no hold, no gen_gate key on /router/gpu (never an idle-gate line)")

    # Q4 non-generation routes are never gated
    H.running = [{"prompt_id": "still"}]
    t0 = time.time()
    s, h = gw.get("/router/backends")
    ok(s == 200 and time.time() - t0 < 2.0, "Q4 status routes pass while the holder works")

    # Q5 the gate switch can be turned off (hot config reload)
    with open(os.path.join(gw.root, "gateway.json"), "w") as f:
        json.dump({"gpu_free": {"urls": ["http://127.0.0.1:18097"], "queue_gate": False}}, f)
    t0 = time.time()
    s, h = gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    ok(s == 200 and time.time() - t0 < 2.0, "Q5 queue_gate false: generation is not gated")

    # Q6 fail-open: a wedged holder cannot wedge a request forever
    with open(os.path.join(gw.root, "gateway.json"), "w") as f:
        json.dump({"gpu_free": {"urls": ["http://127.0.0.1:18097"],
                                "queue_max_wait_s": 2}}, f)
    t0 = time.time()
    s, h = gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    dt = time.time() - t0
    ok(s == 200 and 1.8 <= dt < 5.5, "Q6 wedged holder: gave the request up after %.1f s" % dt)

    # Q7 both queue episodes left gate events on the timeline
    H.running, H.pending = [], []
    s, h = gw.get("/router/events")
    kinds = {e["kind"] for e in json.loads(h)["events"]}
    ok("gate" in kinds, "Q7 queue episodes are visible as gate events")

    # Q8 holder down -> no gate at all (report the backend resident first, like
    # production; the negative cache absorbs the dead-holder probe entirely)
    H.shutdown()
    H = None
    A.loaded = True
    gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    t0 = time.time()
    s, h = gw.post("/v1/chat/completions", {"model": MA, "messages": []})
    dt = time.time() - t0
    ok(s == 200 and dt < 2.0,
       "Q8 holder down: requests are not gated (chat %.1f s)" % dt)

    print("ALL PASS")
finally:
    gw.close()
    A.shutdown()
    B.shutdown()
    if H is not None:
        H.shutdown()
