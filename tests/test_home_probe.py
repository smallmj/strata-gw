#!/usr/bin/env python3
"""T22/T23 - find it yourself, or point at it; and the gateway's own port.
Home probes trust shape; the port is saved for the next boot, with the
resolution order env > gateway.json > default pinned at function level."""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, REPO, ROUTER_PORT as gw_port, ok


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


home1 = os.path.join(tempfile.gettempdir(), "probe-full-home")
home2 = os.path.join(tempfile.gettempdir(), "probe-broken-home")
shutil.rmtree(home1, ignore_errors=True)
shutil.rmtree(home2, ignore_errors=True)
plant_full(home1)
plant_broken(home2)

gw = Gateway([], [], extra_env={
    "GW_HOME_CANDIDATES": home1 + ";" + home2,
    "STRATA_PYTHON": sys.executable,
})
try:
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

    # ---- T23: the router port is a knob too --------------------------------
    s, h = gw.get("/router/port")
    d = json.loads(h)
    ok(s == 200 and d.get("current") == gw_port and d.get("env_pinned") is True,
       "H9 GET /router/port reports the live port and that env pins it (harness always sets STRATA_ROUTER_PORT)")

    s, r = gw.post("/router/port", {"port": 18299})
    d = json.loads(r)
    g2 = json.load(open(gj))
    ok(s == 200 and g2.get("router_port") == 18299 and d.get("restart_needed") is True,
       "H10 saving a port writes gateway.json and honestly flags it needs a restart")

    bad = 0
    for bp in (999, 70000, "abc"):
        s, _ = gw.post("/router/port", {"port": bp})
        if s == 400:
            bad += 1
    ok(bad == 3 and json.load(open(gj)).get("router_port") == 18299,
       "H11 ports below 1024, above 65535 and non-numbers are all refused without touching the file")

    # env trumping survives a restart: the saved port waits its turn
    gw.restart()
    okr = False
    for _ in range(60):
        s, _ = gw.get("/router/backends")
        if s == 200:
            okr = True
            break
        time.sleep(0.25)
    s, h = gw.get("/router/port")
    d = json.loads(h)
    ok(okr and d.get("current") == gw_port and d.get("saved") == 18299,
       "H12 after a restart the env port still wins over gateway.json - saved waits its turn, nothing breaks")
finally:
    gw.close()
    shutil.rmtree(home1, ignore_errors=True)
    shutil.rmtree(home2, ignore_errors=True)

# ---- H14: the full-process closed loop - a saved port with NO env override.
# The socket genuinely moves: boot reads gateway.json and binds there.
import subprocess
import socket
import urllib.request
TREE_SKIP = {".git", "testdir", "tests", "__pycache__", "strata-router.py.orig"}
LOOP_PORT = 18093
root = tempfile.mkdtemp(prefix="portloop-")
for item in sorted(os.listdir(REPO)):
    if item in TREE_SKIP:
        continue
    src = os.path.join(REPO, item)
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(root, item), ignore=shutil.ignore_patterns("__pycache__"))
    else:
        shutil.copy(src, os.path.join(root, item))
with open(os.path.join(root, "gateway.json"), "w") as f:
    json.dump({"router_port": LOOP_PORT}, f)
env = dict(os.environ)
env.pop("STRATA_ROUTER_PORT", None)          # the whole point: no env, file decides
env["STRATA_ROUTER_ANYHOST"] = "1"
proc = None
try:
    proc = subprocess.Popen([sys.executable, os.path.join(root, "strata-router.py")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = None
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/router/port" % LOOP_PORT, timeout=1) as rr:
                got = json.load(rr)
                break
        except Exception:
            time.sleep(0.5)
    old_dead = False
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/router/port" % gw_port, timeout=1)
    except Exception:
        old_dead = True
    ok(got is not None and got.get("current") == LOOP_PORT and got.get("saved") == LOOP_PORT
       and got.get("env_pinned") is False,
       "H14a saved port, no env: the gateway really binds gateway.json's port on boot")
    ok(old_dead, "H14b and nothing is listening on the harness port - the socket moved for real")
finally:
    if proc:
        proc.kill()
        proc.wait()
    shutil.rmtree(root, ignore_errors=True)

# pure-function pin of the resolution order
sys.path.insert(0, REPO)
import gw.config as _cfg
_fake = tempfile.mkdtemp(prefix="gw-port-")
_real_root = _cfg.ROOT
_real_env = os.environ.get("STRATA_ROUTER_PORT")
_cfg.ROOT = _fake
try:
    with open(os.path.join(_fake, "gateway.json"), "w") as f:
        json.dump({"router_port": 23456}, f)
    os.environ.pop("STRATA_ROUTER_PORT", None)
    saved_only = _cfg.router_port()
    os.environ["STRATA_ROUTER_PORT"] = "34567"
    env_wins = _cfg.router_port()
    os.environ.pop("STRATA_ROUTER_PORT", None)
    os.remove(os.path.join(_fake, "gateway.json"))
    default_port = _cfg.router_port()
finally:
    _cfg.ROOT = _real_root
    if _real_env is not None:
        os.environ["STRATA_ROUTER_PORT"] = _real_env
    shutil.rmtree(_fake, ignore_errors=True)
ok(saved_only == 23456 and env_wins == 34567 and default_port == 18075,
   "H13 port resolution order is env > gateway.json > 18075 (function-level pin)")

print("ALL PASS")
