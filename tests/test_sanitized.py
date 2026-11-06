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
ok('id="archsvg"' in html and "<g id=\"dg-backends\"" not in html,
   "S2 diagram is an empty runtime host (archsvg), no static backend groups baked in")
css = open(os.path.join(ROOT, "console", "style.css"), encoding="utf-8").read()
_js2 = open(os.path.join(ROOT, "console", "app.js"), encoding="utf-8").read()
ok(("linearGradient" in html) or ("linearGradient" in _js2 and "url(#agr)" in css),
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
for probe in ("pg.hero", "pg.lead", "sec.dyn", "mon.th1", "fe.nick",
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

# boot language path: the refresh callback (runs at boot) must apply the stored
# language over the zh-prefilled HTML, not wait for a manual toggle
ok("modelsList=list;\n    applyLang();syncLangBtn();" in js,
   "T8k stored language applied on boot refresh")

# no raw-Chinese user-facing say()/alert() left: every string goes through tt()/t()
# T8l: every CJK double-quoted literal must be tt()-wrapped, a language-button
# label, or confined to a LANG==="zh" branch line (structural EN guarantee)
import io as _io
_bad = []
for _ln in js.splitlines():
    _t = _ln.strip()
    if _t.startswith("//"):
        continue
    _masked = re.sub(r'(?:\btt|\bt)\("[^"]*","[^"]*"\)', "TT()", _t)
    for _m in re.finditer(r'"([^"\n]*)"', _masked):
        if not re.search(r"[\u4e00-\u9fff]", _m.group(1)):
            continue
        if _m.group(1) in ("\u4e2d / EN", "EN / \u4e2d"):
            continue
        if 'LANG==="zh"' in _t:
            continue
        _bad.append(_m.group(1))
ok(not _bad, "T8l no unwrapped Chinese literals on EN code paths: " + str(_bad[:4]))

# T8m: decorative <em> secondary labels hidden under EN (no "Events Events",
# no Chinese em leaking into an English page)
ok('_ems[_ei].style.display=LANG==="en"?"none":""' in js,
   "T8m sec em labels hidden in EN mode")

raw_say = re.findall(r'say\(\s*"(?:[^"]*?[\u4e00-\u9fff][^"]*?)"', js)
raw_alert = re.findall(r'alert\(\s*"(?:[^"]*?[\u4e00-\u9fff][^"]*?)"', js)
ok(not raw_say and not raw_alert,
   "T8j say()/alert() bilingual via tt() (raw zh: %d/%d)" % (len(raw_say), len(raw_alert)))

# every web call survives failures: fetch chains all end in .catch (no white page
# when an old engine build lacks endpoints - the proxy mirrors 404s, JS swallows)
ncatch, nfetch = js.count(".catch("), js.count("fetch(")
ok(nfetch >= 6 and ncatch >= nfetch,
   "S7 all web calls carry .catch (%d catch / %d fetch)" % (ncatch, nfetch))

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

# ---- T10 (Phase 10): asset scrub + official pet sample ----------------------
import struct
import zlib

def _png_read(path):
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, chunks, idat = 8, [], b""
    while pos + 8 <= len(d):
        ln = struct.unpack(">I", d[pos:pos + 4])[0]
        tag = d[pos + 4:pos + 8]
        if tag == b"IDAT":
            idat += d[pos + 8:pos + 8 + ln]
        chunks.append(tag.decode("latin-1"))
        pos += 12 + ln
        if tag == b"IEND":
            break
    w, h, depth, ctype = struct.unpack(">IIBB", d[16:26])
    return w, h, depth, ctype, chunks, idat

metas = {"tEXt", "iTXt", "zTXt", "eXIf", "comT", "chrm", "comment"}
png_clean = True
for name in ("qwen-chan.png", "sc117-chan.png", "pet.png"):
    got = _png_read(os.path.join(ROOT, "gw-assets", name))
    if not got or (set(got[4]) & metas):
        png_clean = False
ok(png_clean, "T10a shipped PNGs carry no text-metadata chunks")

mp4 = open(os.path.join(ROOT, "gw-assets", "bg-loop.mp4"), "rb").read()
ok(b'"class_type"' not in mp4 and b"prompt" not in mp4,
   "T10b bg-loop.mp4 carries no generator workflow JSON")

pv = _png_read(os.path.join(ROOT, "gw-assets", "pet.png"))
ok(pv and 658 <= pv[0] <= 742 and 886 <= pv[1] <= 1016,
   "T10c official pet sample in the 700x964 +/-6%% band (got %sx%s)" % (pv[0], pv[1]) if pv else "T10c unreadable")
# edge ring must be fully transparent (auto-crop left alpha breathing room)
if pv:
    w, h, depth, ctype, chunks, idat = pv
    ok(depth == 8 and ctype == 6, "T10d pet.png is 8-bit RGBA")
    raw = zlib.decompress(idat)
    stride = w * 4
    prev = bytearray(stride)
    o = 0
    edge_ok = True
    for y in range(h):
        f = raw[o]; o += 1
        row = bytearray(raw[o:o + stride]); o += stride
        if f == 1:
            for x in range(4, stride):
                row[x] = (row[x] + row[x - 4]) & 255
        elif f == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                left = row[x - 4] if x >= 4 else 0
                row[x] = (row[x] + (left + prev[x]) // 2) & 255
        elif f == 4:
            for x in range(stride):
                a = row[x - 4] if x >= 4 else 0
                b2 = prev[x]
                c = prev[x - 4] if x >= 4 else 0
                p = a + b2 - c
                pa, pb, pc = abs(p - a), abs(p - b2), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b2 if pb <= pc else c)
                row[x] = (row[x] + pr) & 255
        else:
            edge_ok = False  # unknown filter
        if y == 0 or y == h - 1:
            if any(row[x * 4 + 3] != 0 for x in range(w)):
                edge_ok = False
        if row[3] != 0 or row[stride - 1] != 0:
            edge_ok = False
        prev = row
    ok(edge_ok, "T10e pet sample edge ring fully transparent (RGBA unfiltered scan)")

print("ALL PASS")
