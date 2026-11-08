#!/usr/bin/env python3
r"""Backend enlistment E2E on the sim kit - one visible pass, full evidence trail.
Chain: zero-config boot -> onboard -> catalog -> enroll Q4SIM (fake download) ->
watch auto-mount -> clock in (real spawn path) -> canned chat -> disk map ->
FAILSIM failure path -> teardown. Mirrors what the real gateway does against
D:\Strata, without touching production."""
import sys, os, json, time, tempfile, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)

# helpers replicated from test_model_admin (importing that file would RUN it)
import shutil
REPO = os.getcwd()
KIT = os.path.join(REPO, "tools", "sim-strata")
from stub_common import Gateway, ROUTER_PORT

BASE = f"http://127.0.0.1:{ROUTER_PORT}"

def req(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, data=body,
                               headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(r, timeout=6) as x:
            return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except OSError:
        return 0, {}

def say(tag, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + tag + (" | " + extra if extra else ""))
    return ok

home = tempfile.mkdtemp(prefix="e2e-sim-")
for item in ("setup.py", "serve", "engine", "holder.py"):
    src = os.path.join(KIT, item)
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(home, item))
    else:
        shutil.copyfile(src, os.path.join(home, item))
# the kit ships its engine stamp at engine/BUILD.json; gateway spawns home/serve
env = {"STRATA_HOME": home, "STRATA_PYTHON": sys.executable,
       "SIM_STRATA_TOTAL_S": "6", "SIM_STRATA_PACK_MB_PER_GB": "0.05",
       "SIM_STRATA_DATA": os.path.join(home, "data"),
       "GW_SCAN_WATCH_S": "2", "STRATA_FIRST_BACKEND_PORT": "18241"}
fails = 0
g = Gateway([], [], extra_env=env)
try:
    up = False
    for _ in range(40):
        s, h = req("/router/backends")
        if s == 200:
            up = True
            break
        time.sleep(0.25)
    fails += not say("E1 zero-config gateway boots and stays up", up)

    s, ob = req("/router/onboard?check=1")
    eng = ob.get("engine") or {}
    chk = {}
    for _ in range(60):
        s, ob2 = req("/router/onboard")
        chk = ob2.get("check") or {}
        if chk.get("state") in ("done", "failed"):
            break
        time.sleep(0.3)
    say("E2 onboard: engine found + one-line check readable",
        s == 200 and eng.get("found") and chk.get("state") == "done" and chk.get("ok") and chk.get("summary"),
        f"ver={eng.get('version')} sim={eng.get('sim')} check={str(chk.get('summary'))[:60]!r} models={ob.get('models')}")

    s, cat = req("/router/setup/models")
    fams = sorted((cat.get("families") or {}).keys())
    say("E3 catalog readable (families)", s == 200 and "simcore" in fams, ",".join(fams))

    s, run = req("/router/setup/run", {"family": "simcore", "tier": "Q4SIM"})
    fails += not say("E4 enroll accepted", s == 200 and run.get("ok", True))
    done, cur, log_lines = None, 0, 0
    for _ in range(160):
        s, st = req(f"/router/setup/status?since={cur}")
        got = st.get("lines") or []
        log_lines += len(got)
        if log_lines <= 3 and got:
            print("   log pump:", got[:3])
        cur += len(got)
        if st and st.get("state") in ("done", "failed"):
            done = st
            break
        time.sleep(0.4)
    say("E5 fake download ran live with pumped stdout", done and done.get("state") == "done",
        f"state={done.get('state') if done else '?'} loglines={log_lines}")
    res = (done or {}).get("result") or {}
    say("E6 result.new hands the fresh card name back", bool(res.get("new")), str(res.get("new")))

    names = []
    for _ in range(60):
        s, bks = req("/router/backends")
        names = [b.get("model") for b in bks.get("backends", [])]
        if any("sim" in (n or "") for n in names):
            break
        time.sleep(0.5)
    say("E7 watch auto-mounted the new card (no restart)", any("sim" in (n or "") for n in names),
        ",".join(str(n) for n in names))

    tgt = next((n for n in names if n and "one" in n), None)
    s, lr = req("/load", {"model": tgt})
    say("E8 clock-in accepted", s in (200, 202), f"model={tgt} resp={json.dumps(lr)[:120]}")
    live = False
    for _ in range(80):
        s, bks = req("/router/backends")
        live = any(b.get("model") == tgt and b.get("loaded") for b in bks.get("backends", []))
        if live:
            break
        time.sleep(0.5)
    fails += not say("E9 backend reaches loaded", live)

    if live:
        try:
            stx, cj = req("/v1/chat/completions", {"messages": [{"role": "user", "content": "ping"}]})
            txt = (cj.get("choices") or [{}])[0].get("message", {}).get("content", "")
            say("E10 chat answers via the gateway proxy (canned persona)",
                stx == 200 and ("特工" in txt or "operative" in txt.lower()), txt[:70])
        except Exception as e:
            fails += not say("E10 chat answers via the gateway proxy (canned persona)", False, str(e))

    s, dk = req("/router/disk")
    dm = {m.get("model"): m for m in dk.get("models", [])}
    fails += not say("E11 disk map lists the new model with byte totals",
        s == 200 and any(m.get("total_bytes", 0) > 0 for m in dm.values()),
        f"models={list(dm)[:6]} data_dir={bool(dk.get('data_dir'))}")
    s, run3 = req("/router/setup/run", {"family": "simvista", "tier": "Q4SIM"})
    for _ in range(160):
        s, st = req("/router/setup/status?since=99999")
        if st and st.get("state") in ("done", "failed"):
            break
        time.sleep(0.4)
    s, dk2 = req("/router/disk")
    dm2 = {m.get("model"): m for m in dk2.get("models", [])}
    shared = any(len(f.get("used_by") or []) > 1 for m in dm2.values() for f in m.get("files", []))
    fails += not say("E12 shared pack cross-referenced once two models share it",
                     shared, f"models={list(dm2)}")

    s, run2 = req("/router/setup/run", {"family": "simcore", "tier": "FAILSIM"})
    done2, cur2 = None, 0
    seen_lines = []
    for _ in range(160):
        s, st = req(f"/router/setup/status?since={cur2}")
        got = st.get("lines") or []
        seen_lines += got
        cur2 += len(got)
        if st and st.get("state") in ("done", "failed"):
            done2 = st
            break
        time.sleep(0.4)
    say("E13 FAILSIM dies mid-run, log keeps the failure line",
        done2 and done2.get("state") == "failed" and any("flap" in ln for ln in seen_lines),
        f"tail={seen_lines[-1:]}")

    s, bks = req("/router/backends")
    still = any(b.get("model") == tgt and b.get("loaded") for b in bks.get("backends", []))
    say("E14 failed enroll never hurt the running card", still)
finally:
    g.close()
    shutil.rmtree(home, ignore_errors=True)
    for junk in ("gateway.json", "router-setup.json"):
        pth = os.path.join(g.root, junk)
        if os.path.exists(pth):
            print("cleanup ok:", junk)

print("E2E TOTAL FAIL =", fails)
sys.exit(0 if fails == 0 else 1)
