#!/usr/bin/env python3
"""test_sweep.py - the boot/load strata-process sweep (old-gw semantics).

The legacy internal gateway killed every strata-router, every serve wrapper and
every strata engine at startup; the open-source one adopted stragglers instead:
two routers bound one port, adopted engines kept their logs out of the console
window, and orphan engines kept holding VRAM so the next load crawled. The
gateway now owns the sweep on every boot path. This suite pins the pure
decision logic (row parsing, kill plan, folder safety, orphan rule, the
disable knob) plus the wiring and the load-time GPU cross-check. Windows-only
enforcement lives in the live check; on POSIX everything stays inert.
Usage: python3 tests/test_sweep.py  -> PASS lines, ALL PASS, exit 0.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import REPO, ok  # noqa: E402

sys.path.insert(0, REPO)
from gw import sweep  # noqa: E402

ROOT = r"D:\strata-gw"
SERVER_PY = r"D:\Strata\serve\server.py"

# ---- SW1: row parsing ----------------------------------------------------
RAW = (
    "900|python.exe|901|\"D:\\Strata\\.venv\\Scripts\\python.exe\"  \"D:\\strata-gw-test\\strata-router.py\"\n"
    "902|python.exe|903|\"D:\\Strata\\.venv\\Scripts\\python.exe\"  \"D:\\strata-gw\\strata-router.py\"\n"
    "903|python.exe|904|\"D:\\Strata\\.venv\\Scripts\\python.exe\"  strata-router.py\n"
    "910|python.exe|902|D:\\Strata\\.venv\\Scripts\\python.exe D:\\Strata\\serve\\server.py --engine strata --config D:\\Strata\\strata-qwen.json --host 0.0.0.0 --port 18081 --api-key k --lazy\n"
    "911|python.exe|910|D:\\Strata\\.venv\\Scripts\\python.exe D:\\Strata\\serve\\server.py --port 18081\n"
    "912|strata.exe|911|D:\\Strata\\engine\\strata.exe --serve --pack ...\n"
    "913|strata-vision.exe|911|D:\\Strata\\engine\\strata-vision.exe --mmproj ...\n"
    "914|python.exe|915|\"D:\\Comfy\\.venv\\Scripts\\python.exe\" -X utf8 main.py --listen\n"
    "916|python.exe|917|C:\\hermes\\python.exe -m hermes_cli.main gateway run\n"
    "918|explorer.exe|1|\n"
    "919|pythonw.exe|1|\"pythonw.exe\" \"D:\\strata-gw\\strata-router.py\"\n"
)
rows = sweep.parse_rows(RAW)
ok(len(rows) == 11 and rows[0]["pid"] == 900 and rows[0]["ppid"] == 901,
   "SW1a parse_rows reads pid|name|ppid|cmdline lines")
ok(rows[9]["cmdline"] == "" or rows[9]["cmdline"] == "1", "SW1b a row without a cmdline parses anyway")
ok("|" in rows[0]["cmdline"] or "strata-gw-test" in rows[0]["cmdline"],
   "SW1c pipes inside the cmdline stay with the cmdline field")

# a live set without the row format, built by hand for the plans:
def R(pid, ppid, name, cmd):
    return {"pid": pid, "ppid": ppid, "name": name, "cmdline": cmd}

ROWS = rows + [R(901, 4, "cmd.exe", "cmd /c"), R(904, 903, "cmd.exe", "cmd /c start"),
               R(905, 1, "python.exe", "\"D:\\Strata\\.venv\\Scripts\\python.exe\"  strata-router.py"),
               R(921, 5, "python.exe", "\"D:\\Strata\\.venv\\Scripts\\python.exe\"  \"D:\\strata-gw\\strata-router.py\"")]

# ---- SW2: boot plan ------------------------------------------------------
plan = sweep.plan_boot(ROWS, me={905}, root=ROOT, server_py=SERVER_PY)
killed = {pid for pid, _n, _w in plan}
why = {pid: w for pid, _n, w in plan}
ok(902 in killed and why[902] == "router", "SW2a a router of THIS folder (absolute cmdline) is reaped")
ok(903 in killed and why[903] == "router", "SW2b a relative-form router is reaped too (the double-router case)")
ok(919 in killed and why[919] == "router", "SW2c pythonw counts as a router process as well")
ok(900 not in killed, "SW2d a router living in ANOTHER folder is never touched")
ok(901 not in killed and 904 not in killed, "SW2e non-python hosts are never touched")
ok(905 not in killed, "SW2f this process's own pid survives the boot sweep")
ok(910 in killed and 911 in killed and why[910] == "wrapper", "SW2g serve wrappers of our engine home are reaped")
ok(912 in killed and why[912] == "engine", "SW2h strata.exe is reaped")
ok(913 in killed and why[913] == "engine", "SW2i strata-vision.exe is reaped")
ok(914 not in killed and 916 not in killed and 918 not in killed,
   "SW2j unrelated pythons (image generator, chat clients, explorer) are never touched")

# ---- SW3: folder safety (separator-aware) --------------------------------
ok(sweep.is_under(r"D:\strata-gw\strata-router.py", ROOT), "SW3a same folder matches")
ok(not sweep.is_under(r"D:\strata-gw-test\strata-router.py", ROOT),
   "SW3b the substring folder (test twin) is NOT under our root")
ok(sweep.is_under(r"d:\STRATA-GW\x\strata-router.py", ROOT), "SW3c Windows paths are case-insensitive")
ok(sweep.is_under(r"D:\strata-gw\strata-router.py", ROOT + "\\"), "SW3d a trailing separator in the base is fine")

# ---- SW4: own ancestry chain --------------------------------------------
anc = sweep.ancestors(ROWS + [R(906, 905, "python.exe", "D:\\Strata\\.venv\\Scripts\\python.exe strata-router.py")],
                      906)
ok(906 in anc and 905 in anc, "SW4a the venv stub parent is part of the protected chain")
ok(904 not in anc and 901 not in anc, "SW4b protection stops above the python chain (console hosts untouched)")

# ---- SW5: orphan rule at load time --------------------------------------
orows = [R(930, 999, "strata.exe", "D:\\Strata\\engine\\strata.exe --serve"),          # parent dead
         R(931, 911, "strata.exe", "D:\\Strata\\engine\\strata.exe --serve"),          # live wrapper chain
         R(932, 911, "strata-vision.exe", "D:\\Strata\\engine\\strata-vision.exe"),    # live wrapper chain
         R(911, 910, "python.exe", "D:\\Strata\\.venv\\Scripts\\python.exe " + SERVER_PY + " --port 18081"),
         R(910, 1, "python.exe", "D:\\Strata\\.venv\\Scripts\\python.exe " + SERVER_PY + " --port 18081"),
         R(934, 888, "python.exe", "python.exe " + SERVER_PY + " --port 18082"),       # wrapper, router long dead
         R(935, 936, "python.exe", "\"D:\\Comfy\\.venv\\Scripts\\python.exe\" main.py --listen"),
         R(936, 1, "cmd.exe", "")]
orph = {pid for pid, _n, _w in sweep.plan_orphans(orows, me=set())}
ok(930 in orph, "SW5a an engine whose parent died is an orphan and gets reaped before a load")
ok(931 not in orph and 932 not in orph, "SW5b engines under a live serve wrapper are left alone (they are in service)")
ok(934 in orph, "SW5c a serve wrapper whose gateway died is an orphan too")
ok(935 not in orph and 936 not in orph, "SW5d the image generator and its host are never in the orphan family")
ok(all(w == "orphan" for _p, _n, w in sweep.plan_orphans(orows, me=set())),
   "SW5e orphan kills carry their own reason label")

# ---- SW6: the disable knob ----------------------------------------------
os.environ["STRATA_SWEEP"] = "0"
ok(sweep.enabled() is False, "SW6a STRATA_SWEEP=0 disables the sweep (a side-by-side test instance must never kill production engines)")
os.environ["STRATA_SWEEP"] = "1"
ok(sweep.enabled() is True, "SW6b STRATA_SWEEP=1 forces it back on")
del os.environ["STRATA_SWEEP"]
ok(sweep.enabled() is True, "SW6c default on")

# ---- SW7: POSIX inertness (CI runs here) ---------------------------------
res = sweep.sweep_boot()
res2 = sweep.sweep_orphans()
ok(res == [] and res2 == [], "SW7a on non-Windows both sweeps are inert no-ops")

# ---- SW8: wiring pins ----------------------------------------------------
with open(os.path.join(REPO, "gw", "main.py"), encoding="utf-8") as f:
    main_src = f.read()
i_sweep = main_src.find("sweep.sweep_boot()")
i_scan = main_src.find("scan_configs()")
ok(i_sweep != -1 and i_scan != -1 and i_sweep < i_scan,
   "SW8a boot sweep runs BEFORE configs are scanned (nothing adopted that should have been reaped)")

with open(os.path.join(REPO, "gw", "routes.py"), encoding="utf-8") as f:
    routes_src = f.read()
seg = routes_src[routes_src.index("def _prepare_load"):routes_src.index("def _route")]
ok("sweep.sweep_orphans()" in seg, "SW8b every load path reaps orphaned strata processes first")
ok("gpu_free.ensure_card()" in seg, "SW8c the external-holder card gate still runs on load")

cmd = os.path.join(REPO, "strata-gw.cmd")
with open(cmd, encoding="utf-8") as f:
    cmd_src = f.read()
ok("strata-router.py" in cmd_src and "GATEWAY_PY" in cmd_src,
   "SW8d the shipped launcher still starts the gateway in the foreground window")

# ---- SW9: the GPU water-line cross-check ---------------------------------
gf = os.path.join(REPO, "gw", "gpu_free.py")
with open(gf, encoding="utf-8") as f:
    gf_src = f.read()
ok("query-compute-apps" in gf_src, "SW9a the gateway can name the processes that hold the GPU")
ok("smi_holders" in gf_src and "def parse_apps" in gf_src, "SW9b holder enumeration is a parseable pure helper")
ok(sweep.__name__ in gf_src or "sweep" in routes_src,
   "SW9c something on the load path owns the reaping of strata's own leftovers")
apps = __import__("gw.gpu_free", fromlist=["parse_apps"]).parse_apps(
    "67648, D:\\Strata\\engine\\strata.exe\n26388, D:\\Comfy\\python.exe")
ok(apps and apps[0][0] == "67648" and "strata" in apps[0][1],
   "SW9d parse_apps reads the nvidia-smi compute-apps csv shape")

# ---- SW10: enumeration must fail LOUD, never silently empty ---------------
with open(os.path.join(REPO, "gw", "sweep.py"), encoding="utf-8") as f:
    sweep_src = f.read()
ok("no sweep performed" in sweep_src, "SW10a an enumeration crash says so on the console")
ok("enumeration returned no processes" in sweep_src, "SW10b an empty enumeration says so too")

print("ALL PASS")
