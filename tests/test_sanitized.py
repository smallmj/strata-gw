#!/usr/bin/env python3
"""test_sanitized.py - Phase 5: the architecture SVG is redesigned and the
page carries no private/machine-specific strings. Run: python3 tests/test_sanitized.py
Expect: ALL PASS. Pure file/static analysis + node eval of one extracted function."""
import json
import os
import re
import subprocess
import sys

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

print("ALL PASS")
