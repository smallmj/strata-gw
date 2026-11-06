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

# ---- K7: settings popover keeps pet controls; the API key moved to the bar ----
ok('id="setpop"' in html, "K7 settings popover #setpop present")
sp_i = html.find('id="setpop"')
sp = html[sp_i:sp_i + 1600] if sp_i >= 0 else ""
ok('id="key"' in bar and 'id="save"' in bar and 'id="key"' not in sp,
   "K7b API key input+save live on the bar, not in the popover")
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

# ---- K12 (ux v7): control scale 28px chips CJK-safe + a REAL settings gear ----
ok("height:24px" not in css, "K12a the 24px cages are gone")
ok("height:28px" in css and "white-space:nowrap" in css and "min-height:56px" in css,
   "K12b 28px chip scale + nowrap + flowing acts row")
ok("M19.14,12.94" in html, "K12c proper settings gear (notched teeth path)")
ok("M12 8.5a3.5 3.5" not in html, "K12d the old blob gear is gone")

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

# ---- K15 (ux v7): one opaque card in view, neighbours peek 44px, slide on switch ----
ok(".page.pr" in css and ".page.pl" in css and "transition:transform" in css,
   "K15a deck peek + slide css")
ok('"page pr"' in js and '"page pl"' in js and '"page p1"' not in js,
   "K15b setPage uses pr/pl")
ok("translateX(calc(100% - 44px))" in css and "translateX(calc(-100% + 44px))" in css,
   "K15c slide geometry peeks 44px")
ok(".pagesw" not in css and 'class="pagesw"' not in html, "K15d ghost-page stacking retired")
ok("--cardbg" in css and "var(--cardbg)" in css, "K15e opaque card background token")
ok("#cards" in css and "transition:height" in css and "deckHeight" in js,
   "K15f height-stable deck container")

# ---- K18 (ux v7): training flips the card; the standalone tuning desk is gone ----
ok('data-r="train"' in js and 'id="train-src"' in html and 'id="t-save"' in html
   and 'id="t-clear"' in html, "K18a train button + shared form holder")
ok('id="sec-settings"' not in html and 'seg-models' not in html and 'buildSeg' not in js,
   "K18b standalone tuning desk retired")
ok('openTrain' in js and 'closeTrain' in js and 'flipped' in js, "K18c flip plumbing")
ok('data-r="back"' in js and 'back-close' in js, "K18d card back exists")
ok('collectSampling' in js and 'collectConfig' in js and '已保存' in js,
   "K18e one save for both zones + saved toast")
ok('.cback' in css and 'rotateY(180deg)' in css and 'backface-visibility' in css,
   "K18f flip css present")

# ---- K19 (ux v7): api key pinned to the control bar; monitor guides the missing key ----
ok('class="keybox"' in html and html.index('class="keybox"') < html.index("</header>"),
   "K19a key box inside the sticky control bar")
ok('id="mon-keycta"' in html and 'mon.keycta' in i18njs, "K19b monitor key CTA + i18n key")
ok('"页脚' not in js and "footer api key" not in js, "K19c stale footer-key wording gone")
ok('mon-keycta' in js and js.count("pollMetrics()")>=3, "K19d CTA wired + key save re-polls")
ok(".keybox" in css and "flash" in css, "K19e keybox css with focus flash")

# ---- K20 (ux v7): the desk pet shows by default (opt out via its menu or the gear) ----
ok('_p===null?true' in js, "K20a pet defaults ON when never toggled")
ok('catch(e){petOn=true}' in js, "K20b pet defaults ON even when storage is blocked")

# ---- K16: accent is a free color (hex passthrough), not just q/s ----
ok("#[0-9a-fA-F]" in js, "K16a hex accent detection in app.js")

# ---- K17 (ux v7): dossier headline + denser four-group live rows, nothing clipped ----
ok('class="dtitle"' in js and 'class="dnick"' in js and 'class="dsub"' in js,
   "K17a headline hierarchy dtitle/dnick/dsub")
ok('"特工信息","DOSSIER"' in js, "K17b dossier headline via tt()")
for needle in ("info.cfg", "cfg.quant", "cfg.max_context", "cfg.kv", "cfg.rope",
               "cfg.drafting", "cfg.idle_unload_s", "cfg.reasoning_effort", "cfg.sampling"):
    ok(needle in js, "K17c row source wired: " + needle)
ok(".dhead" in css and ".dtitle" in css and ".dnick" in css and ".dsub" in css,
   "K17d headline css present")
ok("height:58px" not in css, "K17e tags fixed-height cage gone")
ok("height:3.32em" not in css and "-webkit-line-clamp:3" in css, "K17f prose flows 3 lines")
ok(css.count("height:1.6em") == 0 and ".notes li{font-size:.76rem;color:var(--muted);line-height:1.6;position:relative;padding-left:.25rem}" in css,
   "K17g note rows flow freely")
ok("grid-template-columns:1fr 1fr" in css, "K17h two-column rows on wide screens")

sys.exit(0 if not F else 1)
