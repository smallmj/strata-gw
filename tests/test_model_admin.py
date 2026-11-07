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

print("ALL PASS")
