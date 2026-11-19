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

    # QG3 (review fix #3, red first): TWO requests hold the gate at once —
    # the gateway answers over ThreadingHTTPServer, so two wait_gen_queue
    # loops interleave. The /router/gpu gen_gate key is the gate's state,
    # not one request's: it must follow the LAST holder out. A single-value
    # t0 let the first loop's finally erase the still-held gate (the panel
    # lied: "gate gone" while a request still waits). Long poll interval +
    # staggered arrival = the leave window is wide and deterministic:
    # req1's next poll is ~2.5 s after it entered, req2's ~1.0 s later.
    with open(os.path.join(gw.root, "gateway.json"), "w") as f:
        json.dump({"gpu_free": {"urls": ["http://127.0.0.1:18097"],
                                "queue_poll_s": 2.5, "queue_max_wait_s": 30}}, f)
    H.running, H.pending = [{"prompt_id": "two1"}], []
    _q1 = []
    _qt1 = threading.Thread(target=lambda: _q1.append(
        gw.post("/v1/chat/completions", {"model": MA, "messages": []})), daemon=True)
    _qt1.start()
    time.sleep(1.0)
    _q2 = []
    _qt2 = threading.Thread(target=lambda: _q2.append(
        gw.post("/v1/chat/completions", {"model": MA, "messages": []})), daemon=True)
    _qt2.start()
    time.sleep(1.0)                     # both loops are inside the gate
    gj = json.loads(gw.get("/router/gpu")[1])
    ok(isinstance(gj.get("gen_gate"), dict),
       "QG3a two holds, one gate: gen_gate present while both wait")
    H.running = []                      # holder goes idle; each loop leaves on its own poll
    _qt1.join(timeout=15)               # req1 is through (next poll ~2.5 s after entry)
    gj = json.loads(gw.get("/router/gpu")[1])
    ok(isinstance(gj.get("gen_gate"), dict) and gj["gen_gate"].get("waited_s", -1) >= 0,
       "QG3b first hold left while the second still waits: gen_gate STILL honest")
    _qt2.join(timeout=15)
    gj = json.loads(gw.get("/router/gpu")[1])
    ok("gen_gate" not in gj,
       "QG3c last hold left: gen_gate gone (the counter must not stick)")
    ok(len(_q1) == 1 and len(_q2) == 1 and _q1[0][0] == 200 and _q2[0][0] == 200,
       "QG3d both gated requests completed normally (payload shape untouched)")

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
