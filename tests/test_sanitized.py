#!/usr/bin/env python3
"""test_sanitized.py - Phase 5: the architecture SVG is redesigned and the
page carries no private/machine-specific strings. Run: python3 tests/test_sanitized.py
Expect: ALL PASS. Pure file/static analysis + node eval of one extracted function."""
import json
import os
import re
import subprocess
import sys
import glob as globmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if len(sys.argv) > 1:
    ROOT = sys.argv[1]

def ok(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)

html = open(os.path.join(ROOT, "console", "index.html"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "console", "app.js"), encoding="utf-8").read()

# S1: no personal ports / private nicknames / hardware model names in the page
for banned in ("18081", "18082", "qwen 后端", "sc117 后端", "RTX", "DDR4",
               "64 GB", "64GB", "55 GB", "dg-ram", "dg-gpu"):
    ok(banned not in html, "S1 index.html free of %r" % banned)

# S2: the dynamic backends group exists, plus the new gradient/flow vocabulary
ok(re.search(r'<g id="dg-backends"[ >]', html) is not None, "S2 #dg-backends group present in the diagram")
css = open(os.path.join(ROOT, "console", "style.css"), encoding="utf-8").read()
ok("linearGradient" in html and ("stroke-dasharray" in html or "stroke-dasharray" in css),
   "S2 gradient stroke + dashed give-card link")
ok("@keyframes flow" in css or "@keyframes flow" in html, "S2 flow keyframes shipped")

# S3: every diagram LABEL is i18n-tagged (the dynamic port text is exempt: it's data, not prose)
svg_start = html.index('<svg class="diagram"')
svg = html[svg_start:html.index("</svg>", svg_start)]
tags = re.findall(r"<text\b[^>]*>", svg)
bad = [t for t in tags if "data-i18n=" not in t and 'id="dg-port"' not in t]
ok(len(tags) >= 10 and not bad, "S3 all %d svg label(s) i18n-tagged (bad=%r)" % (len(tags), bad))
ok("querySelectorAll('[data-i18n]')" in js or 'querySelectorAll("[data-i18n]")' in js,
   "S3 applyLang replaces data-i18n nodes")

# S4: the backends->svg builder is a pure function; node runs it with stub data
m = re.search(r"/\*ARCH-PURE-START\*/(.*?)/\*ARCH-PURE-END\*/", js, re.S)
ok(m is not None and "function dgBackends(" in m.group(1), "S4 pure dgBackends() between ARCH-PURE markers")
if m:
    src = m.group(1)
    script = ("var out=dgBackends(%s);"
              "console.log(JSON.stringify(out));" %
              json.dumps([{"nick": "m%d" % i, "port": 18100 + i} for i in range(5)]))
    r = subprocess.run(["node", "-e", src + "\n" + script],
                       capture_output=True, text=True, timeout=20)
    ok(r.returncode == 0, "S4 node evaluates dgBackends: " + r.stderr[:120])
    cards = json.loads(r.stdout) if r.returncode == 0 else []
    ok(sum(1 for c in cards if c.get("card")) == 4 and
       sum(1 for c in cards if c.get("more")) == 1,
       "S4 5 models -> 4 cards + '+1' overflow badge (max 4)")
    r2 = subprocess.run(["node", "-e", src + "\nconsole.log(JSON.stringify(dgBackends("
                        "JSON.parse(process.argv[1]))));",
                         json.dumps([{"nick": "only", "port": 1}])],
                        capture_output=True, text=True, timeout=20)
    c2 = json.loads(r2.stdout) if r2.returncode == 0 else []
    ok(sum(1 for c in c2 if c.get("card")) == 1, "S4 1 model -> exactly 1 card")
    # ports and nicks must come from the data, never baked literals
    ok(all("18081" not in str(c) for c in cards) and
       re.search(r"model\.port|\.port\b", src) is not None,
       "S4 card text reads model data (no baked ports)")

# S5: old hardware-text backfill JS is gone (moved into monitor kvchips)
ok("dg-ram" not in js and "dg-gpu" not in js, "S5 old dg-ram/dg-gpu backfill removed from app.js")

# ---- T8 (Phase 8): full-page i18n via console/i18n.js + data-i18n attrs ----
ij_path = os.path.join(ROOT, "console", "i18n.js")
ok(os.path.isfile(ij_path), "T8a console/i18n.js exists")
ij = open(ij_path, encoding="utf-8").read()
m = re.search(r"window\.__I18N__\s*=\s*(\{.*\})\s*;?\s*$", ij.strip(), re.S)
ok(m is not None, "T8b i18n.js is a window.__I18N__ JSON assignment")
TBL = json.loads(m.group(1)) if m else {"zh": {}, "en": {}}
ok(set(TBL.get("zh", {})) == set(TBL.get("en", {})),
   "T8c zh/en key sets are exactly equal (%d keys)" % len(TBL.get("zh", {})))
ok(len(TBL.get("zh", {})) >= 60, "T8d word table is page-wide (>=60 keys)")

# every annotated key in the HTML exists in the table
anno = re.findall(r'data-i18n(?:-html|-title|-ph)?="([^"]+)"', html)
missing = sorted({k for k in anno if k not in TBL.get("zh", {})})
ok(anno and not missing, "T8e all %d HTML annotation keys in table%s"
   % (len(anno), ("" if not missing else " missing: " + ",".join(missing))))
ok(len(set(anno)) >= 45, "T8f HTML carries page-wide annotations (>=45 unique keys)")
for probe in ("pg.hero", "pg.lead", "sec.dyn", "mon.th1", "fe.nick_zh",
              "pet.needload", "dg.gw", "set.samptag", "ui.save"):
    ok(probe in TBL.get("zh", {}), "T8g probe key %s present" % probe)

# fold-back: renderer inlines i18n.js and the JSON reaches the page
sys.path.insert(0, ROOT)
import gw.console as _console  # noqa: E402
page = _console.render(18080)
ok("window.__I18N__" in page and '<script src="i18n.js">' not in page,
   "T8h render() folds i18n.js inline into the single page")

# runtime copy must not keep its own duplicate word table
ok("var I18N={" not in js and "window.__I18N__" in js,
   "T8i app.js reads the injected table (no second source of truth)")

# no raw-Chinese user-facing say()/alert() left: every string goes through tt()/t()
raw_say = re.findall(r'say\(\s*"(?:[^"]*?[\u4e00-\u9fff][^"]*?)"', js)
raw_alert = re.findall(r'alert\(\s*"(?:[^"]*?[\u4e00-\u9fff][^"]*?)"', js)
ok(not raw_say and not raw_alert,
   "T8j say()/alert() bilingual via tt() (raw zh: %d/%d)" % (len(raw_say), len(raw_alert)))

# ---- T9 (Phase 9): personalization audit lint ------------------------------
# Token table built by concatenation so the scanner never hits its own source.
def _f(*parts):
    return "".join(parts)

_STRICT_TOKENS = [
    _f("co", "m", "fy"), _f("3", "090"), _f("RT", "X"), "GeForce", _f("DD", "R4"),
    _f("Ya", "RN"), _f("K8", "V4"), _f("IQ3", "_S"), _f("GS", "Q"), _f("512", " ?K"),
    "MoE", _f("n", "-gram"), _f("M", "TP"), _f("sc", "117"),
    _f("qw", "en") + r"(?!\w*example)", _f("Q", "wen"), _f("64", " ?GB"),
    _f("46", ".85"), _f("14", ".4"), _f("54", ".8"), _f("55", ".1 GB"), _f("55", " GB"),
    _f("两", "档"), _f("三", "档"), _f("互相", "让卡"), _f("酒馆", "RP内嵌"),
    _f("1808", "1"), _f("1808", "2"), _f("205", "00"), _f("strata", ".cmd"),
    _f("GATEWAY", "_HTML"), _f("a0021", "b99"), _f("D", r":\\"), _f("C", r":\\Users"),
]
_LEAK_TOKENS = [_f("a0021", "b99"), r"[CD]:\\", _f("/home/", "smallmj")]
_STRICT_PAT = re.compile("|".join(_STRICT_TOKENS))
_LEAK_PAT = re.compile("|".join(_LEAK_TOKENS))
_BRAND_PAT = re.compile(_f("co", "m", "fy"), re.I)

def _scan(path, pat):
    out = []
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return out
    for i, ln in enumerate(text.splitlines(), 1):
        m = pat.search(ln)
        if m:
            out.append("%s:%d:%s" % (os.path.relpath(path, ROOT), i, m.group(0)))
    return out

strict_files = []
for sub in ("console", "gw", "launcher", "config-examples"):
    d = os.path.join(ROOT, sub)
    if os.path.isdir(d):
        strict_files += [f for f in sorted(globmod.glob(os.path.join(d, "*"))) if os.path.isfile(f)]
entry = os.path.join(ROOT, "strata-router.py")
if os.path.isfile(entry):
    strict_files.append(entry)
viol = []
for f in strict_files:
    viol += _scan(f, _STRICT_PAT)
ok(not viol, "T9a STRICT token scan clean (%d hits)%s"
   % (len(viol), "" if not viol else " :: " + "; ".join(viol[:6])))

doc_files = [os.path.join(ROOT, n) for n in ("README.md", "AGENTS.md", "LICENSE", "cards", "cards.json")
             if os.path.isfile(os.path.join(ROOT, n))]
viol2 = []
for f in doc_files:
    viol2 += _scan(f, _LEAK_PAT)
ok(not viol2, "T9b leak scan (docs + shipped cards) clean (%d)%s"
   % (len(viol2), "" if not viol2 else " :: " + "; ".join(viol2[:6])))

# ALL layer: every tracked text file, brand token only (concatenated pattern)
tracked = subprocess.run(["git", "-C", ROOT, "ls-files"],
                         capture_output=True, text=True, timeout=20).stdout.split()
viol3 = []
for rel in tracked:
    if rel.endswith((".png", ".mp4", ".jpg", ".jpeg", ".webp", ".woff2")):
        continue
    viol3 += _scan(os.path.join(ROOT, rel), _BRAND_PAT)
ok(not viol3, "T9c brand-token scan over ALL tracked text files clean (%d)%s"
   % (len(viol3), "" if not viol3 else " :: " + "; ".join(viol3[:6])))

ok(os.path.isfile(os.path.join(ROOT, "VERSION"))
   and open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip(),
   "T9d VERSION file present and non-empty")
cfgs = globmod.glob(os.path.join(ROOT, "config-examples", "*.json"))
bad_keys = []
for f in cfgs:
    try:
        d = json.load(open(f, encoding="utf-8-sig"))
    except ValueError:
        bad_keys.append(os.path.basename(f) + ":unparseable")
        continue
    if d.get("api_key"):
        bad_keys.append(os.path.basename(f))
ok(not bad_keys, "T9e config-examples ship empty api_key (%s)" % (",".join(bad_keys) or "none/vacuous"))

print("ALL PASS")
