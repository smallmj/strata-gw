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


def up(g, timeout=12):
    """Zero-config gateways answer with an EMPTY backends list, so
    wait_ready() (which demands a non-empty one) is useless there: poll the
    endpoint for liveness only."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s, _ = g.get("/router/backends")
        if s == 200:
            return True
        time.sleep(0.4)
    return False


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

# --- T3: a hand-edited config lands or vanishes on its own - the watch picks
# it up without any restart and without hitting POST /router/scan.
shome4 = tempfile.mkdtemp(prefix="gw-shome4-")
gw4 = Gateway([], [], extra_env={"STRATA_HOME": shome4, "GW_SCAN_WATCH_S": "2"})
try:
    deadline = time.time() + 12
    s = 0
    while time.time() < deadline:
        s, _ = gw4.get("/router/backends")
        if s == 200:
            break
        time.sleep(0.4)
    ok(s == 200, "T3a zero-config gateway up for the watch test")
    with open(os.path.join(shome4, "strata-watch.json"), "w") as f:
        json.dump({"model_name": "watch-t3", "api_key": ""}, f)
    deadline = time.time() + 6
    while time.time() < deadline and "watch-t3" not in names(gw4):
        time.sleep(0.4)
    ok("watch-t3" in names(gw4), "T3b new config auto-picked without a restart")
    os.remove(os.path.join(shome4, "strata-watch.json"))
    deadline = time.time() + 6
    while time.time() < deadline and "watch-t3" in names(gw4):
        time.sleep(0.4)
    ok("watch-t3" not in names(gw4), "T3c removed config auto-dropped without a restart")
finally:
    gw4.close()
    shutil.rmtree(shome4, ignore_errors=True)

# --- T4: the recruit list is read live from the installed setup.py's own
# constants (probe runs with the install's python; fixtures point STRATA_PYTHON
# at this interpreter since the fake setup.py is constants-only).
shome5 = tempfile.mkdtemp(prefix="gw-shome5-")
with open(os.path.join(shome5, "setup.py"), "w", encoding="utf-8") as f:
    f.write(
        "FAMILIES = {'famx': {'title': 'Fam X One', 'by': 'tst', 'about': 'a demo family', "
        "'name': 'famx-one', 'tag': '', 'vision': True}}\n"
        "PREVIEW_FAMILIES = {'fampv': {'title': 'Fam PV', 'by': 'tst', 'about': 'preview', "
        "'name': 'fampv', 'tag': 'pv'}}\n"
        "MULTI_FILE_FAMILIES = {'mfx': {'title': 'Multi X', 'by': 'tst', 'about': 'multi', "
        "'name': 'mfx', 'models': {'BIG': {'about': 'big tier', 'ram_gb': 32, 'label': 'BIG'}}}}\n"
        "MODELS = {'T9_A': {'about': 'tier a', 'download_gb': 4.0, 'ram_gb': 8, "
        "'arena_gb': 2, 'families': ['famx']}}\n")
gw5 = Gateway([], [], extra_env={"STRATA_HOME": shome5, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gw5), "T4 pre: zero-config gateway with setup.py up")
    s, h = gw5.get("/router/setup/models")
    cat = json.loads(h) if s == 200 else {}
    ok(s == 200 and cat.get("families", {}).get("famx", {}).get("title") == "Fam X One"
       and cat.get("tiers", {}).get("T9_A", {}).get("download_gb") == 4.0,
       "T4a GET /router/setup/models reads the installed list")
    tiers = (cat.get("families", {}).get("mfx") or {}).get("tiers") or {}
    ok(tiers.get("BIG", {}).get("ram_gb") == 32,
       "T4b multi-file family carries its own tiers")
finally:
    gw5.close()

# T4c: no setup.py under the home -> 503 with a guide message.
shome6 = tempfile.mkdtemp(prefix="gw-shome6-")
gw6 = Gateway([], [], extra_env={"STRATA_HOME": shome6, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gw6), "T4c pre: zero-config gateway without setup.py up")
    s, h = gw6.get("/router/setup/models")
    msg = (json.loads(h).get("error") or {}).get("message", "") if s else ""
    ok(s == 503 and "setup" in msg.lower(),
       "T4c missing setup.py -> 503, message points at it")
finally:
    gw6.close()
    shutil.rmtree(shome5, ignore_errors=True)
    shutil.rmtree(shome6, ignore_errors=True)

# --- T5: the recruit run drives the installed setup.py non-interactively,
# streams its stdout into the status log ring, keeps run history for
# 重新入册, lands the one-key policy and creates the placeholder card.
# FAKE_SETUP mirrors the real install tool in the one way the gateway relies
# on: constants live at import time, the CLI only runs under __main__ (the
# real setup.py is side-effect-free to import - probed on the live box).
FAKE_SETUP = r'''
import argparse, json, os, sys, time
FAMILIES = {"faux": {"title": "Faux One", "by": "tst", "about": "fake family",
                     "name": "faux-one", "tag": "", "vision": True}}
PREVIEW_FAMILIES = {}
MULTI_FILE_FAMILIES = {}
MODELS = {"T9_X": {"about": "x tier", "download_gb": 1.0, "ram_gb": 4, "arena_gb": 1,
                   "families": ["faux"]},
          "T9_Z": {"about": "z tier", "download_gb": 2.0, "ram_gb": 4, "arena_gb": 1,
                   "families": ["faux"]},
          "T9_Y": {"about": "other-fam tier", "download_gb": 1.0, "ram_gb": 4, "arena_gb": 1,
                   "families": ["otherfam"]},
          "TFAIL": {"about": "mid-run failure demo", "download_gb": 1.0, "ram_gb": 4,
                    "arena_gb": 1, "families": ["faux"]}}


def _main():
    ap = argparse.ArgumentParser(prog="fake setup")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--family"); ap.add_argument("--model")
    ap.add_argument("--context", type=int)
    ap.add_argument("--kv"); ap.add_argument("--vision")
    ap.add_argument("--gguf-dir", dest="gguf_dir"); ap.add_argument("--data-dir", dest="data_dir")
    ap.add_argument("--no-start", action="store_true"); ap.add_argument("--yes", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "args_dump.json"), "w") as f:
        json.dump(sys.argv[1:], f)
    if a.check:
        print("fake pc check: ok", flush=True); sys.exit(0)
    if not a.setup or not a.family or not a.model:
        sys.exit(2)
    for i in range(3):
        print("faux: fetching %s %d/3" % (a.model, i + 1), flush=True)
        time.sleep(0.2)
    if a.model == "TFAIL":
        print("faux: link flapped, giving up", flush=True)
        sys.exit(3)
    fname = FAMILIES[a.family]["name"]
    tier = a.model.lower()
    cfg = {"model_name": fname + "-" + tier,
           "args": ["--pack", os.path.join(here, "packs", tier),
                    "--max-context", str(a.context or 131072)]}
    with open(os.path.join(here, "strata-" + fname + "-" + tier + ".json"), "w") as f:
        json.dump(cfg, f)
    print("faux: config written", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    _main()
'''


def wait_done(g, timeout=25):
    st = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        s, h = g.get("/router/setup/status?since=0")
        st = json.loads(h)
        if st.get("state") in ("done", "failed"):
            return st
        time.sleep(0.3)
    return st


shome7 = tempfile.mkdtemp(prefix="gw-shome7-")
with open(os.path.join(shome7, "setup.py"), "w", encoding="utf-8") as f:
    f.write(FAKE_SETUP)
gwA = Gateway([], [], extra_env={"STRATA_HOME": shome7, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gwA), "T5 pre: fake-install gateway up")
    s, h = gwA.post("/router/setup/run",
                    {"family": "faux", "tier": "T9_X", "context": 131072})
    ok(s == 200 and json.loads(h).get("started") is True, "T5a run accepted {started:true}")
    s2, _ = gwA.post("/router/setup/run", {"family": "faux", "tier": "T9_Z"})
    ok(s2 == 409, "T5a2 concurrent run while running -> 409")
    st = wait_done(gwA)
    ok(st and st.get("state") == "done" and st.get("code") == 0
       and any("faux: fetching" in x for x in (st.get("lines") or [])),
       "T5a3 status streams fake progress; done code=0")
    ok((st.get("result") or {}).get("new") == ["faux-one-t9_x"],
       "T5a4 result.new feeds the card-flip animation")
    ok("faux-one-t9_x" in names(gwA), "T5a5 done forces rescan: model in backends")
    s4, h4 = gwA.get("/router/cards")
    ok("faux-one-t9_x" in json.dumps(json.loads(h4)),
       "T5a6 placeholder card created, nick=model name")

    # T5b: one-key policy. Nothing was installed before -> a fresh 32-hex
    # token lands in the new config AND in gateway.json default_api_key;
    # the next run reuses it.
    cfgj = json.load(open(os.path.join(shome7, "strata-faux-one-t9_x.json")))
    tok = cfgj.get("api_key") or ""
    ok(len(tok) == 32 and all(c in "0123456789abcdef" for c in tok),
       "T5b1 fresh recruit without prior key -> 32-hex token")
    gj = json.load(open(os.path.join(gwA.root, "gateway.json")))
    ok(gj.get("default_api_key") == tok, "T5b2 gateway.json keeps the shared default")
    s5, _ = gwA.post("/router/setup/run", {"family": "faux", "tier": "T9_Z"})
    ok(s5 == 200, "T5b3 second run starts")
    st2 = wait_done(gwA)
    cfgz = json.load(open(os.path.join(shome7, "strata-faux-one-t9_z.json")))
    ok(st2 and st2.get("state") == "done" and cfgz.get("api_key") == tok,
       "T5b4 second run reuses the default key (one key per gateway)")
finally:
    gwA.close()

# T5b-pre: an installed config with a key -> the new recruit shares it.
shome8 = tempfile.mkdtemp(prefix="gw-shome8-")
with open(os.path.join(shome8, "setup.py"), "w", encoding="utf-8") as f:
    f.write(FAKE_SETUP)
with open(os.path.join(shome8, "strata-installed-x.json"), "w") as f:
    json.dump({"model_name": "installed-x", "api_key": "SAMEKEY"}, f)
gwB = Gateway([], [], extra_env={"STRATA_HOME": shome8, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gwB), "T5b pre: gateway with a pre-installed keyed config up")
    s, _ = gwB.post("/router/setup/run", {"family": "faux", "tier": "T9_X"})
    st = wait_done(gwB)
    cfgb = json.load(open(os.path.join(shome8, "strata-faux-one-t9_x.json")))
    ok(s == 200 and st and st.get("state") == "done" and cfgb.get("api_key") == "SAMEKEY",
       "T5b5 installed model's key is reused for the recruit")
finally:
    gwB.close()

# T5c: parameter pass-through + input validation (400s start no subprocess).
shome9 = tempfile.mkdtemp(prefix="gw-shome9-")
with open(os.path.join(shome9, "setup.py"), "w", encoding="utf-8") as f:
    f.write(FAKE_SETUP)
gwC = Gateway([], [], extra_env={"STRATA_HOME": shome9, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gwC), "T5c pre: gateway up")
    s, _ = gwC.post("/router/setup/run",
                    {"family": "faux", "tier": "T9_X", "gguf_dir": "/nonexistent-zz-dir"})
    ok(s == 400, "T5c1 missing gguf_dir -> 400 (gateway checks existence)")
    s, _ = gwC.post("/router/setup/run", {"family": "faux", "tier": "T9_Y"})
    ok(s == 400, "T5c2 tier from another family -> 400")
    s, _ = gwC.post("/router/setup/run", {"family": "bad fam!", "tier": "T9_X"})
    ok(s == 400, "T5c3 illegal family slug -> 400")
    s, _ = gwC.post("/router/setup/run",
                    {"family": "faux", "tier": "T9_X", "vision": "no",
                     "gguf_dir": shome9, "data_dir": shome9 + "/data", "kv": "int8"})
    st = wait_done(gwC)
    dump = json.load(open(os.path.join(shome9, "args_dump.json")))

    def has(flag, val):
        return flag in dump and dump[dump.index(flag) + 1] == str(val)

    ok(s == 200 and st and st.get("state") == "done"
       and has("--vision", "no") and has("--gguf-dir", shome9)
       and has("--data-dir", shome9 + "/data") and has("--kv", "int8")
       and "--no-start" in dump and "--yes" in dump,
       "T5c4 full params reach setup.py (--no-start --yes always)")

    # T5d: history persists; failed run recorded; after a gateway restart the
    # status endpoint answers from history (badge survives restarts).
    hist = json.load(open(os.path.join(gwC.root, "router-setup.json")))
    ok(hist[-1]["state"] == "done" and hist[-1]["params"]["tier"] == "T9_X",
       "T5d1 ROOT/router-setup.json keeps the finished run")
    s, _ = gwC.post("/router/setup/run", {"family": "faux", "tier": "TFAIL"})
    stf = wait_done(gwC)
    ok(stf and stf.get("state") == "failed" and stf.get("code") == 3,
       "T5d2 failing setup -> state failed, exit code kept")
    gwC.restart()
    ok(up(gwC), "T5d3 gateway restarted on the same root")
    s, h = gwC.get("/router/setup/status?since=999999")
    hj = json.loads(h)
    ok(s == 200 and hj.get("from_history") is True and hj.get("state") == "failed"
       and (hj.get("params") or {}).get("tier") == "TFAIL",
       "T5d4 status after restart reads history: 重新入册 badge data survives")
finally:
    gwC.close()
    shutil.rmtree(shome7, ignore_errors=True)
    shutil.rmtree(shome8, ignore_errors=True)
    shutil.rmtree(shome9, ignore_errors=True)

# --- T6: the onboarding checklist line - engine presence + BUILD.json version,
# the model count, and the one-sentence PC check from setup.py --check.
shomeA = tempfile.mkdtemp(prefix="gw-shomeA-")   # no setup.py: engine missing
gwD = Gateway([], [], extra_env={"STRATA_HOME": shomeA, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gwD), "T6 pre: gateway up")
    s, h = gwD.get("/router/onboard")
    ob = json.loads(h) if s == 200 else {}
    ok(s == 200 and (ob.get("engine") or {}).get("found") is False,
       "T6a no setup.py -> engine not found on the checklist")
    ok(ob.get("models") == 0, "T6b model count line answers")
finally:
    gwD.close()

shomeB = tempfile.mkdtemp(prefix="gw-shomeB-")
with open(os.path.join(shomeB, "setup.py"), "w", encoding="utf-8") as f:
    f.write(FAKE_SETUP)
os.makedirs(os.path.join(shomeB, "engine"))
with open(os.path.join(shomeB, "engine", "BUILD.json"), "w") as f:
    json.dump({"version": "9.9.9"}, f)
gwE = Gateway([], [], extra_env={"STRATA_HOME": shomeB, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gwE), "T6 pre2: fake-install gateway up")
    s, h = gwE.get("/router/onboard")
    ob = json.loads(h)
    ok(ob["engine"]["found"] is True and ob["engine"].get("version") == "9.9.9",
       "T6c engine found, version straight from BUILD.json under the home")
    s, h = gwE.get("/router/onboard?check=1")
    ob1 = json.loads(h)
    ok(s == 200 and (ob1.get("check") or {}).get("state") == "running",
       "T6d ?check=1 kicks the PC check off (running)")
    ob2 = None
    deadline = time.time() + 15
    while time.time() < deadline:
        s, h = gwE.get("/router/onboard")
        ob2 = json.loads(h)
        if (ob2.get("check") or {}).get("state") in ("done", "failed"):
            break
        time.sleep(0.4)
    ck = (ob2 or {}).get("check") or {}
    ok(ck.get("state") == "done" and ck.get("ok") is True
       and "fake pc check" in (ck.get("summary") or ""),
       "T6e check done: summary = last non-empty line of setup --check")
finally:
    gwE.close()
    shutil.rmtree(shomeA, ignore_errors=True)
    shutil.rmtree(shomeB, ignore_errors=True)

# --- T8: read-only disk map (网关零删除: the gateway shows the way, it never
# deletes). Fixture: two models share one pack dir, one model has a private
# file, one model dangles a removed path.
shomeC = tempfile.mkdtemp(prefix="gw-shomeC-")
pack = os.path.join(shomeC, "packs", "shared")
os.makedirs(os.path.join(pack, "sub"))
with open(os.path.join(pack, "a.bin"), "w") as f:
    f.write("x" * 1024)
with open(os.path.join(pack, "sub", "b.bin"), "w") as f:
    f.write("y" * 2048)
solo = os.path.join(shomeC, "solo.bin")
with open(solo, "w") as f:
    f.write("z" * 4096)
for nm, args in (("disk-a", ["--pack", pack]),
                 ("disk-b", ["--pack", pack, "--model-path", solo]),
                 ("disk-c", ["--pack", os.path.join(shomeC, "gone")])):
    with open(os.path.join(shomeC, "strata-" + nm + ".json"), "w") as f:
        json.dump({"model_name": nm, "api_key": "", "args": args}, f)
gwF = Gateway([], [], extra_env={"STRATA_HOME": shomeC, "STRATA_PYTHON": sys.executable})
try:
    ok(up(gwF), "T8 pre: disk fixture gateway up")
    s, h = gwF.get("/router/disk")
    d = json.loads(h) if s == 200 else {}
    ma = {m["model"]: m for m in d.get("models") or []}
    ok(s == 200 and sorted(ma) == ["disk-a", "disk-b", "disk-c"],
       "T8a GET /router/disk answers read-only per model")
    fa = (ma.get("disk-a", {}).get("files") or [{}])[0]
    ok(fa.get("path") == os.path.realpath(pack) and fa.get("dir") is True
       and fa.get("bytes") == 3072 and sorted(fa.get("used_by") or []) == ["disk-a", "disk-b"],
       "T8b shared pack dir: recursive size + used_by names both models")
    fbs = [x for x in ma.get("disk-b", {}).get("files") or []
           if x.get("path") == os.path.realpath(solo)]
    ok(len(fbs) == 1 and fbs[0].get("bytes") == 4096
       and fbs[0].get("used_by") == ["disk-b"],
       "T8c exclusive file: owner only")
    fc = (ma.get("disk-c", {}).get("files") or [{}])[0]
    ok(fc.get("missing") is True and fc.get("path") == os.path.realpath(os.path.join(shomeC, "gone")),
       "T8d dangling reference path still listed, marked missing")
    ok(ma.get("disk-a", {}).get("total_bytes") == 3072, "T8e per-model totals sum the files")
    ok(d.get("data_dir") is None and d.get("data_total_bytes") is None,
       "T8f no data dir in sight -> nulls, no globbing")
    ddir = os.path.join(shomeC, "datahome")
    os.makedirs(ddir)
    with open(os.path.join(ddir, "f.bin"), "w") as f:
        f.write("q" * 512)
    with open(os.path.join(gwF.root, "gateway.json"), "w") as f:
        json.dump({"strata_data_dir": ddir}, f)
    s, h = gwF.get("/router/disk")
    d2 = json.loads(h)
    ok(d2.get("data_dir") == os.path.realpath(ddir) and d2.get("data_total_bytes") == 512,
       "T8g gateway.json strata_data_dir overrides, total reads hot")
finally:
    gwF.close()
    shutil.rmtree(shomeC, ignore_errors=True)

# ---- K-SIM: the sim-strata kit defends itself (T14) ------------------------
import subprocess
import urllib.request
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(REPO, "tools", "sim-strata")
_r = subprocess.run([sys.executable, os.path.join(KIT, "setup.py"), "--check"],
                    capture_output=True, text=True)
_lines = (_r.stdout or "").strip().splitlines()
ok(_r.returncode == 0 and _lines and _lines[-1].startswith("SIM PC check"),
   "K-SIM1 kit setup --check exits 0 with the SIM PC check line")


def _kget(url, data=None):
    req = urllib.request.Request(url, data=data) if data is not None else url
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, r.read().decode()


_ps = subprocess.Popen([sys.executable, os.path.join(KIT, "serve", "server.py"),
                        "--engine", "strata", "--config", "/nonexistent.json",
                        "--host", "127.0.0.1", "--port", "18097",
                        "--api-key", "x", "--lazy"])
_ph = subprocess.Popen([sys.executable, os.path.join(KIT, "holder.py"), "18098"])
try:
    kup = False
    for _ in range(30):
        try:
            s, h = _kget("http://127.0.0.1:18097/health")
            kup = s == 200
            if kup:
                break
        except OSError:
            time.sleep(0.2)
    ok(kup and json.loads(h).get("service") == "strata" and not json.loads(h).get("loaded"),
       "K-SIM2 kit serve answers /health like the Stub protocol (idle first)")
    _kget("http://127.0.0.1:18097/load", b"{}")
    ok(json.loads(_kget("http://127.0.0.1:18097/health")[1]).get("loaded"),
       "K-SIM3 kit serve goes loaded after POST /load")
    s, h = _kget("http://127.0.0.1:18098/system_stats")
    v1 = json.loads(h)["devices"][0]["vram_free"]
    _kget("http://127.0.0.1:18098/free", b"{}")
    s, h = _kget("http://127.0.0.1:18098/system_stats")
    v2 = json.loads(h)["devices"][0]["vram_free"]
    ok(s == 200 and v2 > v1,
       "K-SIM4 kit holder frees pretend VRAM after /free (gpu_free shape)")
finally:
    _ps.terminate()
    _ph.terminate()

print("ALL PASS")
