#!/usr/bin/env python3
"""test_model_admin.py - model-admin backend pins (v0.2 Phase A/B/C): the
dual-dir config scan (strata_home wins the trust order), the manual rescan
endpoint, the config watch, the recruit wizard backend and the read-only disk
map. Grows with every Phase A/B/C task; skeleton mirrors tests/test_cards.py.
Usage: python3 tests/test_model_admin.py   -> every assert prints PASS, ends ALL PASS.
"""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, Stub, ok  # noqa: E402

# --- T1a: a config living in the Strata home (where setup.py writes) must be
# discovered even when the gateway ROOT has no copy of it.
shome = tempfile.mkdtemp(prefix="gw-shome-")
with open(os.path.join(shome, "strata-newmodel.json"), "w") as f:
    json.dump({"model_name": "newmodel-t1", "api_key": "k",
               "args": ["--max-context", "8192"]}, f)


def names(g):
    s, h = g.get("/router/backends")
    if s != 200:
        return []
    return sorted(b["model"] for b in json.loads(h).get("backends", []))


A = Stub("qwen", 18095)
gw = Gateway(["qwen"], [18095], extra_env={"STRATA_HOME": shome})
try:
    gw.wait_ready()
    deadline = time.time() + 5
    while time.time() < deadline and "newmodel-t1" not in names(gw):
        time.sleep(0.5)
    ok("newmodel-t1" in names(gw), "T1a strata_home config discovered")
finally:
    gw.close()

# --- T1b: the same model_name in BOTH config homes - the strata_home copy wins
# the trust order, observable through the offline cfg facts (its --max-context
# sentinel comes from the shome file, never the ROOT copy).
with open(os.path.join(shome, "strata-qwen.json"), "w") as f:
    json.dump({"model_name": "qwen", "api_key": "SHADOW",
               "args": ["--max-context", "99991"]}, f)
gw2 = Gateway(["qwen"], [18095], extra_env={"STRATA_HOME": shome})
try:
    gw2.wait_ready()
    s, h = gw2.get("/router/info")
    cfg = (json.loads(h).get("models") or {}).get("qwen", {}).get("cfg") or {}
    ok(cfg.get("max_context") == 99991,
       "T1b same-name config: strata_home copy wins over ROOT")
    # T1c: the shadowed ROOT copy must not double-list the model.
    ns = names(gw2)
    ok(ns == ["newmodel-t1", "qwen"],
       "T1c shadowed copy skipped: exactly one qwen backend")
finally:
    gw2.close()
    A.shutdown()
    shutil.rmtree(shome, ignore_errors=True)

# --- T2a: with zero configs the gateway must stay alive and guide, not die.
shome2 = tempfile.mkdtemp(prefix="gw-shome2-")
gwz = Gateway([], [], extra_env={"STRATA_HOME": shome2})
try:
    bl = None
    deadline = time.time() + 12
    while time.time() < deadline:
        s, h = gwz.get("/router/backends")
        if s == 200:
            bl = json.loads(h)
            break
        time.sleep(0.4)
    ok(bl is not None and bl.get("backends") == [],
       "T2a zero configs: gateway alive with an empty backends list")
    s2, _ = gwz.get("/gateway")
    ok(s2 == 200, "T2b zero configs: the console still serves /gateway")

    # T2c/T2d: plant a config by hand, force the rescan through the endpoint.
    with open(os.path.join(shome2, "strata-late.json"), "w") as f:
        json.dump({"model_name": "late-t2", "api_key": ""}, f)
    s3, h3 = gwz.post("/router/scan")
    ok(s3 == 200 and json.loads(h3) == {"ok": True, "models": 1},
       "T2c POST /router/scan answers {ok:true, models:1}")
    ok("late-t2" in names(gwz), "T2d rescanned model appears in backends")
finally:
    gwz.close()
    shutil.rmtree(shome2, ignore_errors=True)

# --- T2e: the first-backend port lane is an env knob (the sim env needs 1820x).
shome3 = tempfile.mkdtemp(prefix="gw-shome3-")
with open(os.path.join(shome3, "strata-lane.json"), "w") as f:
    json.dump({"model_name": "lane-t2", "api_key": ""}, f)
gw3 = Gateway([], [], extra_env={"STRATA_HOME": shome3,
                                 "STRATA_FIRST_BACKEND_PORT": "18201"})
try:
    gw3.wait_ready()
    ports = {b["model"]: b["port"] for b in
             json.loads(gw3.get("/router/backends")[1]).get("backends", [])}
    ok(ports.get("lane-t2") == 18201,
       "T2e STRATA_FIRST_BACKEND_PORT steers the new backend port")
finally:
    gw3.close()
    shutil.rmtree(shome3, ignore_errors=True)

print("ALL PASS")
