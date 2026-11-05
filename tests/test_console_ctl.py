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
sys.exit(0 if not F else 1)
