#!/usr/bin/env python3
"""T22 - find it yourself, or point at it: home auto-probe + manual set."""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, REPO, ok


def plant_full(home):
    kit = os.path.join(REPO, "tools", "sim-strata")
    os.makedirs(home, exist_ok=True)
    shutil.copyfile(os.path.join(kit, "setup.py"), os.path.join(home, "setup.py"))
    for d in ("serve", "engine"):
        shutil.copytree(os.path.join(kit, d), os.path.join(home, d))


def plant_broken(home):
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "setup.py"), "w") as f:
        f.write("# not an engine: no serve, no engine dir\n")


home1 = os.path.join(os.environ.get("TMPDIR", "/tmp"), "probe-full-home")
home2 = os.path.join(os.environ.get("TMPDIR", "/tmp"), "probe-broken-home")
shutil.rmtree(home1, ignore_errors=True)
shutil.rmtree(home2, ignore_errors=True)
plant_full(home1)
plant_broken(home2)

gw = Gateway([], [], extra_env={
    "GW_HOME_CANDIDATES": home1 + ";" + home2,
    "STRATA_PYTHON": sys.executable,
})
try:
    import time
    up = False
    for _ in range(60):
        s, h = gw.get("/router/backends")
        if s == 200:
            up = True
            break
        time.sleep(0.25)
    ok(up, "H0 zero-config gateway boots")

    s, h = gw.get("/router/home")
    h = json.loads(h)
    ok(s == 200 and h.get("source") == "root" and h.get("valid") is False,
       "H1 GET /router/home reports the current home, its source and whether it is a real engine")

    s, p = gw.get("/router/home/probe")
    p = json.loads(p)
    cands = {c["path"]: c for c in (p.get("candidates") or [])}
    ok(s == 200 and cands.get(home1, {}).get("valid") is True
       and cands.get(home2, {}).get("valid") is False
       and p.get("auto") == home1,
       "H2 probe ranks candidates by shape (setup.py + serve/engine), never trusts the folder name")

    s, r = gw.post("/router/home", {"auto": True})
    r = json.loads(r)
    gj = os.path.join(gw.root, "gateway.json")
    ok(s == 200 and r.get("home") == home1 and os.path.isfile(gj)
       and json.load(open(gj)).get("strata_home") == home1,
       "H3 one-click adopt writes an absolute strata_home into gateway.json (atomic, keeps other keys)")

    s, ob = gw.get("/router/onboard")
    ob = json.loads(ob)
    ok(s == 200 and (ob.get("engine") or {}).get("found") is True
       and (ob.get("engine") or {}).get("home") == home1,
       "H4 the adopt takes effect live - onboard sees the engine without a restart (gateway.json hot reload)")

    s, r = gw.post("/router/home", {"path": home2})
    ok(s == 400 and json.load(open(gj)).get("strata_home") == home1,
       "H5 a manual path that is not an engine is refused and the previous home survives")

    s, r = gw.post("/router/home", {"path": home2, "force": False})
    ok(s == 400, "H6 no side door: refusing is refusing")

    s, r = gw.post("/router/home", {"path": home1})
    r = json.loads(r)
    ok(s == 200 and r.get("home") == home1,
       "H7 manual set to a valid engine path works on its own merits")

    # the other gateway.json keys must survive a rewrite
    with open(gj, "w") as f:
        json.dump({"gpu_free": {"urls": ["http://127.0.0.1:1"]}, "strata_home": home2}, f)
    s, r = gw.post("/router/home", {"auto": True})
    d = json.load(open(gj))
    ok(s == 200 and d.get("strata_home") == home1 and "gpu_free" in d,
       "H8 rewriting the home never clobbers unrelated gateway.json keys")
finally:
    gw.close()
    shutil.rmtree(home1, ignore_errors=True)
    shutil.rmtree(home2, ignore_errors=True)
print("ALL PASS")
