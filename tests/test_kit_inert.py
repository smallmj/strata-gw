#!/usr/bin/env python3
"""test_kit_inert.py - the six inertness pins (T15b, v8 core).

The sim-strata kit is a GENERATOR of throwaway test environments. Only the
generator may enter git; the environments it makes (fake jsons, fake packs,
test gateway.json, firewall rules) live in runtime state and never pollute
main or the product. These pins are permanent: breaking one is a red light,
no task may remove or soften them.

P1 the product never mentions the kit   P2 launchers carry no kit entry
P3 demo ports never become defaults     P4 pretend data is never tracked
P5 a -sim engine paints a demo-mode watermark (live backend pin)
P6 runtime state stays untracked (the real hazard T15b caught)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, ok, REPO  # noqa: E402

KIT = os.path.join(REPO, "tools", "sim-strata")


def _read(f):
    with open(f, encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def _walk(root, exts):
    out = []
    base = os.path.join(REPO, root) if root else REPO
    for dp, ds, fs in os.walk(base):
        if ".git" in dp or "tests" in dp or "tools" in dp or "docs" in dp:
            continue
        ds[:] = [d for d in ds if d not in (".git", "tests", "tools", "docs")]
        for f in fs:
            if f.endswith(exts):
                out.append(os.path.join(dp, f))
    return out


# ---- P1: product code never references the kit ------------------------------
prod = (_walk("gw", (".py",)) + _walk("console", (".js", ".html", ".css"))
        + _walk("launcher", (".cmd", ".sh", ".py"))
        + [os.path.join(REPO, "strata-router.py"), os.path.join(REPO, "strata-gw.cmd")])
hits = [f for f in prod if "sim-strata" in _read(f)]
ok(not hits, "P1 no product file mentions the kit at all")

# ---- P2: launchers carry no kit entry point ---------------------------------
for cmdf in ("strata-gw.cmd", "launcher/strata-gateway.cmd", "launcher/strata-gateway.sh"):
    ok("tools/" not in _read(os.path.join(REPO, cmdf)),
       "P2 %s has zero kit entry (kit runs only by explicit hands)" % cmdf)

# ---- P3: demo ports never leak into product defaults ------------------------
demo_hits = []
for f in (_walk("gw", (".py",)) + _walk("console", tuple())
          + _walk("config-examples", tuple())):
    for port in ("18175", "18288", "18201"):
        if port in _read(f):
            demo_hits.append((f, port))
ok(not demo_hits, "P3 demo ports 18175/18288/18201 live nowhere in the product")

# ---- P4: pretend data is never tracked ---------------------------------------
tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                         text=True).stdout.splitlines()
ok(not [t for t in tracked if "strata-sim" in t]
   and not [t for t in tracked if "tools/sim-strata/packs" in t],
   "P4a no fake configs or fake packs are ever tracked")
r = subprocess.run(["git", "check-ignore", "-q",
                    os.path.join("tools", "sim-strata", "strata-simcore-one-q4sim.json")],
                   cwd=REPO)
ok(r.returncode == 0, "P4b .gitignore covers kit-generated configs")

# ---- P6: runtime state stays untracked (real hazard found in T15b) ----------
r = subprocess.run(["git", "check-ignore", "gateway.json", "router-setup.json"],
                   cwd=REPO, capture_output=True, text=True)
lines = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
ok(r.returncode == 0 and "gateway.json" in lines and "router-setup.json" in lines,
   "P6 gateway.json AND router-setup.json are gitignored (they can hold keys)")
gi = _read(os.path.join(REPO, ".gitignore"))
ok("!config-examples/strata-*.json" in gi,
   "P6c the config-examples exception still stands")

# ---- P5: a -sim engine paints the demo-mode watermark -----------------------
shome = tempfile.mkdtemp(prefix="gw-inert-")
with open(os.path.join(shome, "setup.py"), "w", encoding="utf-8") as f:
    f.write("FAMILIES = {}\nPREVIEW_FAMILIES = {}\nMULTI_FILE_FAMILIES = {}\nMODELS = {}\n")
os.makedirs(os.path.join(shome, "engine"))
build = os.path.join(shome, "engine", "BUILD.json")
with open(build, "w") as f:
    json.dump({"version": "9.9.9-sim"}, f)
gwI = Gateway([], [], extra_env={"STRATA_HOME": shome})
try:
    ready = False
    for _ in range(50):
        if gwI.get("/router/onboard")[0] == 200:
            ready = True
            break
        time.sleep(0.4)
    ok(ready, "P5 pre: onboard gateway up")
    s, h = gwI.get("/router/onboard")
    ob = json.loads(h)
    ok(s == 200 and ob["engine"]["sim"] is True and ob["engine"]["version"] == "9.9.9-sim",
       "P5a -sim version raises the sim flag on the onboarding line")
    with open(build, "w") as f:
        json.dump({"version": "9.9.9"}, f)
    s, h = gwI.get("/router/onboard")
    ob2 = json.loads(h)["engine"]
    ok(ob2["sim"] is False and ob2["warn"] is True,
       "P5b plain 9.9.9 (above the tested ceiling) -> sim false, ceiling warn true")
    with open(build, "w") as f:
        json.dump({"version": "0.0.1"}, f)
    s, h = gwI.get("/router/onboard")
    ob3 = json.loads(h)["engine"]
    ok(ob3["sim"] is False and ob3["warn"] is False,
       "P5c a version under the ceiling keeps both flags false (negative pin)")
finally:
    gwI.close()
    shutil.rmtree(shome, ignore_errors=True)

# ---- P7: the compat contract file is whole ----------------------------------
bl = json.load(open(os.path.join(REPO, "tests", "compat-baseline.json"), encoding="utf-8"))
ok(all(k in bl for k in ("strata_tag", "engine", "setup_cli", "constants",
                        "engine_routes", "model_json_keys"))
   and all(f in bl["setup_cli"] for f in ("--setup", "--family", "--model",
                                          "--context", "--kv"))
   and all(k in bl["constants"] for k in ("FAMILIES", "PREVIEW_FAMILIES",
                                          "MULTI_FILE_FAMILIES", "MODELS_n")),
   "P7 compat-baseline carries all four faces incl. the wizard five flags")
ok(len(bl["engine_routes"]) == 9 and len(bl["setup_cli"]) >= 12,
   "P7b the nine routes and the twelve CLI flags are declared")

app = _read(os.path.join(REPO, "console", "app.js"))
html = _read(os.path.join(REPO, "console", "index.html"))
ok('"-sim"' in app and "demochip" in app and "demochip" in html,
   "P5c the console paints the demo watermark, diff-gated by the version string")
i18n = _read(os.path.join(REPO, "console", "i18n.js"))
ok('demo.tag' in i18n and "演示模式" in i18n and "demo mode" in i18n,
   "P5d the watermark label ships as a zh/en pair")

# ---- P8/P9: canary semantics learned from the v0.2.12 night drift ----------
_can=open(os.path.join(REPO,"scripts","host_compat_canary.py"),encoding="utf-8").read()
ok("n_got >= n_want" in _can and "say(n_want == n_got" not in _can,
   "P8 MODELS_n is a floor test (the model list only grows upstream; an exact match false-alarms every release)")
ok("Invoke-WebRequest" not in _can,
   "P9 the live route check never pokes running engines over HTTP - it reads serve/server.py statically")

# ---- P11 (#16 truth-up): the console-surface route pin is in the three-set --
# The v0.2.16 console bundle rides five more engine routes than the nine that
# were pinned at v0.2.9: /props /slots /mcp /v1/status /api/expert-heat
# (/status was already pinned by engine_routes). The baseline must name them,
# and the canary must be able to READ them in both scan modes - a baseline
# the tripwire cannot check is a wish, not a contract.
ok(all(r in bl.get("console_routes", [])
       for r in ("/props", "/slots", "/mcp", "/v1/status", "/api/expert-heat")),
   "P11a compat-baseline declares console_routes with all five new console-surface routes")
ok("console_routes" in _can and all(
       lit in _can for lit in ('/props', '/slots', '/mcp', '/v1/status', '/api/expert-heat')),
   "P11b the canary scans the five new routes too (static regex + live regex read them)")

# ---- P10: the tripwire must itself be able to READ both host layouts --------
# A fake install is generated straight from tests/compat-baseline.json (all four
# faces), planted once at the top level (legacy) and once under terminal/ (the
# v0.2.16 layout). canary --live has to agree with the baseline in BOTH shapes -
# a tripwire that goes blind on the new layout is worse than no tripwire.
_b10 = json.load(open(os.path.join(REPO, "tests", "compat-baseline.json"), encoding="utf-8"))


def _plant_install(root, sub):
    d = os.path.join(root, sub) if sub else root
    os.makedirs(os.path.join(d, "serve"), exist_ok=True)
    lines = []
    for nm in ("FAMILIES", "PREVIEW_FAMILIES", "MULTI_FILE_FAMILIES"):
        lines.append("%s = {%s}" % (nm, ", ".join(
            '"%s": 1' % k for k in (_b10["constants"].get(nm) or []))))
    n10 = int(_b10["constants"].get("MODELS_n") or 0)
    lines.append("MODELS = {%s}" % ", ".join('"m%03d": 1' % i for i in range(max(n10, 1))))
    for flag in _b10["setup_cli"]:
        lines.append('p.add_argument("%s", help="x")' % flag)
    with open(os.path.join(d, "setup.py"), "w", encoding="utf-8") as fh:
        fh.write("import argparse\np = argparse.ArgumentParser()\n"
                 + "\n".join(lines) + "\n")
    with open(os.path.join(d, "serve", "server.py"), "w", encoding="utf-8") as fh:
        fh.write("ROUTES = [%s]\n" % ", ".join(
            '"%s"' % r for r in list(_b10["engine_routes"]) + list(_b10.get("console_routes", []))))
    vbin = os.path.join(d, ".venv", "bin")
    os.makedirs(vbin, exist_ok=True)
    if not os.path.exists(os.path.join(vbin, "python")):
        os.symlink(sys.executable, os.path.join(vbin, "python"))
    with open(os.path.join(d, "strata-pinned.json"), "w", encoding="utf-8") as fh:
        json.dump({"model_name": "pinned-model", "args": ["--max-context", "8192"]}, fh)


for _sub in ("", "terminal"):
    _tmp10 = tempfile.mkdtemp(prefix="canary-layout-")
    try:
        _plant_install(_tmp10, _sub)
        _r10 = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "host_compat_canary.py"),
                               "--live", "--shome", _tmp10],
                              capture_output=True, text=True, timeout=180)
        _tail10 = ((_r10.stdout or "") + (_r10.stderr or "")).strip().splitlines()
        ok(_r10.returncode == 0,
           "P10 canary --live reads the %s host layout and agrees with the baseline (%s)"
           % (_sub or "legacy", (_tail10[-1] if _tail10 else "no output")))
    finally:
        shutil.rmtree(_tmp10, ignore_errors=True)

print("ALL PASS")

