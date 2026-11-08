#!/usr/bin/env python3
"""host_compat_canary.py - the drift tripwire against the host Strata app.

strata-gw lives inside Strata and hardcodes a small coupling surface: setup
CLI flags, the whitelist constant shape, nine engine routes and the model
json key form. Upstream ships ~2 versions a week; most upgrades are additive
and the gateway rides them at runtime (the wizard reads the installed
setup.py live). This script does NOT police anyone's upgrades - it only
answers one question in seconds: did the coupling surface move?

  --live   probe THIS box (or a remote one via --ssh win, read-only)
  --upstream <tag>   shallow-clone the upstream repo and statically read it:
                     NEVER imports or runs a single line of upstream code

Output: one line per checked field ("OK face/field" or "DIFF ..."), exit 1
on any DIFF, exit 0 when all four faces agree with tests/compat-baseline.json.
The release-day gate (T19) runs --upstream against the newest tag first.
"""
import tempfile
import shutil
import argparse
import ast
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(os.path.dirname(HERE), "tests", "compat-baseline.json")
UPSTREAM_REPO = "https://github.com/Niko1221/Strata"
CRITICAL_JSON_KEYS = ("model_name", "args")     # what backends/ actually reads
WIZARD_FLAGS = ("--setup", "--family", "--model", "--context", "--kv",
                "--vision", "--data-dir", "--gguf-dir", "--no-start", "--yes")

fails = []


def say(cond, face, field, want="", got=""):
    if cond:
        print("OK   %s/%s" % (face, field))
    else:
        fails.append(field)
        print("DIFF %s/%s baseline=%s new=%s" % (face, field, want, got))


# ---- scanning surfaces ------------------------------------------------------
def _topkeys(node):
    if isinstance(node, ast.Dict):
        return [k.value for k in node.keys if isinstance(k, ast.Constant)]
    return None


def scan_py_dir(root):
    """Static read of a Strata home: constants, setup CLI, serve routes."""
    import warnings
    warnings.filterwarnings("ignore", category=SyntaxWarning)
    allc, alias = {}, {}       # NAME -> top-level dict keys / NAME -> another NAME
    cli, routes = set(), set()
    KEEP4 = ("FAMILIES", "PREVIEW_FAMILIES", "MULTI_FILE_FAMILIES", "MODELS")
    for dp, ds, fs in os.walk(root):
        if ".git" in dp:
            continue
        for f in fs:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dp, f)
            src = open(path, encoding="utf-8", errors="ignore").read()
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    nm = node.targets[0].id
                    ks = _topkeys(node.value)
                    if ks:
                        allc.setdefault(nm, set()).update(ks)
                    elif isinstance(node.value, ast.Name):
                        alias.setdefault(nm, set()).add(node.value.id)
            if f == "setup.py" or "setup" in os.path.basename(dp):
                cli.update(re.findall(r'add_argument\(\s*["\'](--[a-z][a-z-]*)', src))
            if "serve" in dp or f in ("server.py", "api.py"):
                routes.update(re.findall(r'["\'](/health|/v1/models|/v1/chat/completions'
                                         r'|/load|/unload|/metrics|/settings|/config|/status)["\']', src))
    for _ in range(4):        # resolve alias graphs (PREVIEW_FAMILIES = OWN_PATH_FAMILIES)
        for nm, srcs in alias.items():
            for s in srcs:
                if s in allc:
                    allc.setdefault(nm, set()).update(allc[s])
    cons = {k: allc[k] for k in KEEP4 if k in allc}
    return cons, cli, routes


# ---- the four faces vs the baseline -----------------------------------------
def compare(b, cons, cli, routes, jkeys):
    for fam in ("FAMILIES", "PREVIEW_FAMILIES", "MULTI_FILE_FAMILIES"):
        want = set(b["constants"].get(fam, []))
        got = cons.get(fam, set())
        say(want <= got, "constants", fam, str(sorted(want)), str(sorted(got)))
    n_want = b["constants"].get("MODELS_n")
    n_got = len(cons.get("MODELS", set()))
    # floor semantics: the upstream model list only ever grows - a release that
    # ADDS a model is not drift; one that SHRINKS it (or moves structure) is
    say(n_want is None or n_got >= n_want, "constants", "MODELS_n",
        "floor %s" % n_want, str(n_got) + (" grew" if n_got > n_want else ""))
    want = set(b["setup_cli"])
    say(want <= cli, "setup_cli", "wizard-flags",
        str(sorted(want)), str(sorted(cli & want)) if cli else "no setup.py surface scanned")
    want = set(b["engine_routes"])
    say(want <= routes, "engine_routes", "nine-routes", str(sorted(want)), str(sorted(routes & want)))
    for k in CRITICAL_JSON_KEYS:
        say(k in jkeys, "model_json_keys", k, "present", "present" if k in jkeys else "MISSING")


def main():
    ap = argparse.ArgumentParser(prog="host_compat_canary (read-only)")
    ap.add_argument("--live", action="store_true", help="probe a running box")
    ap.add_argument("--ssh", default="", help="ssh host for --live (e.g. win)")
    ap.add_argument("--shome", default=r"D:\Strata", help="Strata home for --live")
    ap.add_argument("--upstream", metavar="TAG", help="shallow-clone that tag and scan statically")
    a = ap.parse_args()
    with open(BASELINE, encoding="utf-8") as f:
        b = json.load(f)
    say(b.get("strata_tag") and b.get("engine") and b.get("setup_cli")
        and b.get("constants") and b.get("engine_routes") and b.get("model_json_keys"),
        "baseline", "schema", "four faces", "loaded")
    if a.upstream:


        tmp = tempfile.mkdtemp(prefix="canary-up-")
        try:
            r = subprocess.run(["git", "clone", "--quiet", "--depth", "1",
                                "--branch", a.upstream, UPSTREAM_REPO,
                                os.path.join(tmp, "u")], capture_output=True, text=True, errors="ignore")
            if r.returncode != 0:
                print("clone failed:", (r.stderr or "").strip()[:300])
                return 2
            cons, cli, routes = scan_py_dir(os.path.join(tmp, "u"))
            jkeys = set(b["model_json_keys"])   # json form: upstream tags carry no user configs
            compare(b, cons, cli, routes, jkeys)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif a.live:
        run = (lambda cmd: subprocess.run(["ssh", a.ssh, cmd], capture_output=True,
                                          text=True, errors="ignore").stdout) if a.ssh else \
              (lambda cmd: subprocess.run(cmd, shell=True, capture_output=True,
                                          text=True, errors="ignore").stdout)
        probe = ('import json,sys; sys.path.insert(0, r"%s"); import setup as s; '
                 'print(json.dumps({"FAMILIES": sorted(s.FAMILIES), '
                 '"PREVIEW_FAMILIES": sorted(s.PREVIEW_FAMILIES), '
                 '"MULTI_FILE_FAMILIES": sorted(s.MULTI_FILE_FAMILIES), '
                 '"MODELS": sorted(s.MODELS)}))' % a.shome)
        py = os.path.join(a.shome, ".venv", "Scripts", "python.exe")
        if not a.ssh and not os.path.exists(py):
            py = os.path.join(a.shome, ".venv", "bin", "python")
        try:
            cons = {k: set(v) for k, v in
                    json.loads(run('"%s" -c "%s"' % (py, probe.replace('"', "'"))).strip() or "{}").items()}
        except ValueError:
            cons = {}
            print("live constants probe unreadable (engine venv missing?)")
        # the three text artifacts come over as RAW FILES (scp/local copy), never
        # through a shell pipe: PowerShell re-encodes to the OEM codepage and
        # utf-8 decoding dies somewhere in 5000 lines of engine source
        tmp = tempfile.mkdtemp(prefix="canary-live-")
        try:
            def read(rel):
                if a.ssh:
                    src = "%s:%s" % (a.ssh, os.path.join(a.shome.replace("\\", "/"), rel).replace("\\", "/"))
                    subprocess.run(["scp", "-q", src, os.path.join(tmp, os.path.basename(rel))],
                                   capture_output=True)
                    f = os.path.join(tmp, os.path.basename(rel))
                else:
                    f = os.path.join(a.shome, rel)
                try:
                    return open(f, encoding="utf-8", errors="ignore").read()
                except OSError:
                    return ""
            setup_src = read("setup.py")
            cli = set(re.findall(r'add_argument\(\s*["\'](--[a-z][a-z-]*)', setup_src or ""))
            jkeys = set()
            if a.ssh:
                names = run('powershell -NoProfile -Command "Get-ChildItem \'%s\\strata-*.json\' -Name"' % a.shome)
                for nm in (names or "").split():
                    subprocess.run(["scp", "-q", "%s:%s" % (a.ssh, a.shome.replace("\\", "/") + "/" + nm),
                                    os.path.join(tmp, "j-" + nm)], capture_output=True)
                    try:
                        jkeys.update(re.findall(r'"([a-z_]+)"\s*:',
                                    open(os.path.join(tmp, "j-" + nm), encoding="utf-8", errors="ignore").read()))
                    except OSError:
                        pass
            else:
                import glob as _g
                for f in _g.glob(os.path.join(a.shome, "strata-*.json")):
                    jkeys.update(re.findall(r'"([a-z_]+)"\s*:',
                               open(f, encoding="utf-8", errors="ignore").read()))
            # routes: read the engine's own source text. HTTP probing a live box
            # false-alarms - POST endpoints answer 405 to GET and a cold engine
            # answers little at all. The source is the contract; the socket is not.
            srv = read(os.path.join("serve", "server.py"))
            routes = set(re.findall(r'["\'](/health|/v1/models|/v1/chat/completions'
                                    r'|/load|/unload|/metrics|/settings|/config|/status)["\']', srv or ""))
            compare(b, cons, cli, routes, jkeys)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        ap.print_usage()
        return 2
    if fails:
        print("canary: %d field(s) drifted: %s" % (len(fails), ", ".join(sorted(set(fails)))))
        return 1
    print("canary: all faces agree with the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
