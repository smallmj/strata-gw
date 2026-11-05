#!/usr/bin/env python3
"""test_console_ctl.py — Phase 6: the sticky unified control bar.
K-series asserts the console ships ONE top bar (id="ctlbar") that carries
logo/title, language, theme, video group, external-VRAM bar, version,
GitHub link and the settings popover (API key + desktop-pet controls).
Pure static analysis — no server needed. Expect: ALL PASS."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "console", "index.html"), encoding="utf-8").read()
css = open(os.path.join(ROOT, "console", "style.css"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "console", "app.js"), encoding="utf-8").read()

F = []
def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        F.append(name)

# ---- K1/K2: the bar exists and carries the VRAM strip ----------------------
ok('id="ctlbar"' in html, "K1 sticky control bar id=ctlbar present")
cs = html.find('id="ctlbar"')
ce = html.find("</header>", cs if cs >= 0 else 0)
bar = html[cs:ce] if cs >= 0 and ce > cs else ""
ok('id="gpuhold"' in bar, "K2 #gpuhold lives inside the control bar")

# ---- K3-K5: language, theme, video group all on the bar --------------------
ok('id="langbtn"' in bar, "K3 language toggle #langbtn on the bar")
ok('id="theme"' in bar, "K4 theme toggle #theme on the bar")
ok('id="seg-bg"' in bar and 'id="vid-sound"' in bar,
   "K5 video group (seg-bg + vid-sound) moved onto the bar")

# ---- K6: version + GitHub link --------------------------------------------
ok('id="gwver"' in bar and "v__VERSION__" in bar,
   "K6 version chip uses the __VERSION__ placeholder")
ok('href="__GITHUB_URL__"' in bar, "K6 GitHub anchor uses __GITHUB_URL__")

# ---- K7: settings popover (API key + pet controls) --------------------------
ok('id="setpop"' in html, "K7 settings popover #setpop present")
sp_i = html.find('id="setpop"')
sp = html[sp_i:sp_i + 1600] if sp_i >= 0 else ""
ok('id="key"' in sp and 'id="save"' in sp, "K7b API key input+save inside popover")
ok('id="pet-toggle"' in sp, "K7c desktop-pet toggle in popover")
ok('id="pet-size"' in sp and 'min="80"' in sp and 'max="220"' in sp,
   "K7d pet size slider 80-220 in popover")

# ---- K8: css contract -------------------------------------------------------
ok("#ctlbar" in css and "position:sticky" in css and "backdrop-filter" in css,
   "K8 ctlbar sticky + blur in css")
ok("scroll-margin-top" in css, "K8b section scroll-margin in css")

# ---- K9: app.js wiring ------------------------------------------------------
ok('getElementById("langbtn")' in js, "K9a langbtn wired in app.js")
ok("stratagw.pet" in js and "stratagw.petsize" in js,
   "K9b pet prefs persisted under stratagw.* keys")
ok('getElementById("gwver")' in js and 'fetch("router/info")' in js,
   "K9c version chip pulls engine build from /router/info")
ok('id="setgear"' in html.replace('id="setpop"', 'id="setpop"', 1) or 'id="setgear"' in bar,
   "K9d gear button opens the popover")

# ---- K10: JS parses ---------------------------------------------------------
r = subprocess.run(["node", "--check", os.path.join(ROOT, "console", "app.js")],
                   capture_output=True, text=True)
ok(r.returncode == 0, "K10 app.js parses (node --check)" + ("" if r.returncode == 0 else " :: " + r.stderr[:200]))

print("ALL PASS" if not F else "FAILED: " + ", ".join(F))

i18njs = open(os.path.join(ROOT, "console", "i18n.js"), encoding="utf-8").read()

# ---- K11 (master review): page title is "Strata 网关 / Strata gateway" ----
ok("模型加载台" not in html and "model load console" not in html.lower(),
   "K11a no old tagline in index.html")
ok("<title>Strata 网关</title>" in html, "K11b html title is Strata 网关")
ok('"pg.title": "Strata 网关"' in i18njs and '"pg.title": "Strata gateway"' in i18njs,
   "K11c i18n pg.title zh/en")

# ---- K12: ctlbar buttons all flat at the gwver height (24px) ----
ok("#ctlbar .cbtn,#ctlbar .ghico,#ctlbar .gearbtn,#ctlbar .seg button" in css
   and "height:24px" in css,
   "K12a flat 24px rule for every ctlbar control")

# ---- K13: diagram flow line arcs above the backend cards, never through them ----
ok("M450 186 C 560 196, 640 208, 657 236" not in html,
   "K13a old through-cards curve gone")
ok("C 520 30, 620 24, 668 24" in html, "K13b arc-over-top route in place")

# ---- K14: edit drawer slimmed to nick + palette + art upload ----
for bad in ("ed_nick_zh", "ed_nick_en", "ed_who_zh", "ed_sub_zh", "ed_style_zh",
            "ed_tags_zh", "ed_notes_zh", 'id="ed_art"', 'id="ed_accent"'):
    ok(bad not in html, "K14a form field removed: " + bad)
ok('id="ed_nick"' in html and 'type="color" id="ed_accentc"' in html
   and 'id="ed-swatches"' in html and 'id="ed-artup"' in html,
   "K14b single nick + color input + swatches + upload button")
ok("fe.nick_zh" not in i18njs and "fe.notes_en" not in i18njs,
   "K14c old bilingual form keys purged from word table")

# ---- K15: model cards stack like book pages (p1/p2 behind) ----
ok(".page.p1" in css and ".page.p2" in css, "K15a stacked-behind css exists")
ok('"page p1"' in js and '"page p2"' in js, "K15b setPage assigns depth classes")

# ---- K16: accent is a free color (hex passthrough), not just q/s ----
ok("#[0-9a-fA-F]" in js, "K16a hex accent detection in app.js")

sys.exit(0 if not F else 1)
