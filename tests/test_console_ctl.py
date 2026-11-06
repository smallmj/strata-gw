#!/usr/bin/env python3
"""test_console_ctl.py — Phase 6: the sticky unified control bar.
K-series asserts the console ships ONE top bar (id="ctlbar") that carries
logo/title, language, theme, video group, external-VRAM bar, version,
GitHub link and the settings popover (API key + desktop-pet controls).
Pure static analysis — no server needed. Expect: ALL PASS."""
import os
import subprocess
import re
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
_sp = html.find('id="setpop"')
ce = min(html.find("</header>", cs if cs >= 0 else 0),
         _sp if _sp >= 0 else 1 << 30)
bar = html[cs:ce] if cs >= 0 and ce > cs else ""
ok('id="gpuhold"' in bar, "K2 #gpuhold lives inside the control bar")

# ---- K3-K5: the bar stays short — lang + video hide inside the gear -------
ok('id="langbtn"' in html and 'id="langbtn"' not in bar,
   "K3 language toggle hidden inside the gear popover, not the bar")
ok('id="theme"' in bar, "K4 theme toggle #theme on the bar")
ok('id="seg-bg"' in html and 'id="vid-sound"' in html and 'id="seg-bg"' not in bar,
   "K5 video group inside the gear popover")

# ---- K6: version + GitHub link --------------------------------------------
ok('id="gwver"' in bar and "v__VERSION__" in bar,
   "K6 version chip uses the __VERSION__ placeholder")
ok('href="__GITHUB_URL__"' in html and 'href="__GITHUB_URL__"' not in bar,
   "K6 GitHub anchor moved to the footer, bar stays slim")

# ---- K7: settings popover keeps pet controls; the API key moved to the bar ----
ok('id="setpop"' in html, "K7 settings popover #setpop present")
sp_i = html.find('id="setpop"')
sp = html[sp_i:sp_i + 2600] if sp_i >= 0 else ""
ok('id="key"' in sp and 'id="save"' in sp and 'id="key"' not in bar,
   "K7b token input+save live inside the gear popover")
ok(all(x in sp for x in ('id="key"','id="save"','id="langbtn"','id="seg-bg"','id="vid-sound"')),
   "K7e token + language + video all reachable from one gear")
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
ok("height:28px" in css and "white-space:nowrap" in css and "height:64px" in css,
   "K12b 28px chip scale + nowrap + fixed 64px acts row")
ok("M19.14,12.94" in html, "K12c proper settings gear (notched teeth path)")
ok("M12 8.5a3.5 3.5" not in html, "K12d the old blob gear is gone")

# ---- K13 (ux v8): architecture svg is data-driven, never hardcoded --------
ok("function archBox" in js and "function archLink" in js and "tw(title,12)" in js,
   "K13a box widths measured from title/subtitle text (CJK 1em, latin 0.58em)")
ok("LASTINFO" in js and "LASTGPU" in js and "renderArch(backends)" in js,
   "K13b arch reads live /router/info + VRAM snapshot, capped backend list")
ok("M450 186 C 560 196" not in html and "C 520 30, 620 24, 668 24" not in html,
   "K13c hardcoded diagram curves fully gone")
ok('id="archsvg"' in html and not re.search(r'<rect[^>]*class="dgn"', html),
   "K13d empty svg host only — boxes are painted at runtime")

# ---- K14: edit drawer slimmed to nick + palette + art upload ----
for bad in ("ed_nick_zh", "ed_nick_en", "ed_who_zh", "ed_sub_zh", "ed_style_zh",
            "ed_tags_zh", "ed_notes_zh", 'id="ed_art"', 'id="ed_accent"'):
    ok(bad not in html, "K14a form field removed: " + bad)
ok('id="ed_nick"' in html and 'type="color" id="ed_accentc"' in html
   and 'id="ed-swatches"' in html and 'id="ed-artup"' in html,
   "K14b single nick + color input + swatches + upload button")
ok("fe.nick_zh" not in i18njs and "fe.notes_en" not in i18njs,
   "K14c old bilingual form keys purged from word table")

# ---- K15 (ux v8): stacked cascade — on / n1 / n2, each deeper layer shows a
# WIDER strip, max three cards per screen, deeper ones enter as you flip ------
ok(".page.n1" in css and ".page.n2" in css and "transition:transform" in css,
   "K15a cascade layers on/n1/n2 css")
ok('"page on"' in js and '"page n1"' in js and '"page n2"' in js
   and '"page gone-r"' in js and '"page gone-l"' in js,
   "K15b setPage uses the cascade classes")
ok("translateX(40px)" in css and "translateX(98px)" in css,
   "K15c each deeper layer steps out one more strip")
ok("margin:0 70px" in css and "pointer-events:none}" in css and "pointer-events:auto;" in css,
   "K15i symmetric peek gutters keep the side strips clickable")
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
ok('data-r="back"' in js and 'id="t-close"' in html, "K18d card back + resume button in the bottom row")
ok('collectSampling' in js and 'collectConfig' in js and '已保存' in js,
   "K18e one save for both zones + saved toast")
ok('.cback' in css and 'rotateY(180deg)' in css and 'backface-visibility' in css,
   "K18f flip css present")

# ---- K19 (ux v7): api key pinned to the control bar; monitor guides the missing key ----
ok('id="keychip"' in bar and '<input id="key"' not in bar,
   "K19a slim token status chip (not an input) on the bar")
ok('data-i18n-title="ui.keychipnote"' in bar and '"ui.keychipnote"' in i18njs,
   "K19a2 chip tooltip tells the user the token lives in the gear")
ok('id="mon-keycta"' in html and 'mon.keycta' in i18njs, "K19b monitor key CTA + i18n key")
ok('"页脚' not in js and "footer api key" not in js, "K19c stale footer-key wording gone")
ok('mon-keycta' in js and js.count("pollMetrics()")>=3, "K19d CTA wired + key save re-polls")
ok(".keyrow" in css and "flash" in css, "K19e popover key row css with focus flash")

# ---- K20 (ux v7): the desk pet shows by default (opt out via its menu or the gear) ----
ok('_p===null?true' in js, "K20a pet defaults ON when never toggled")
ok('catch(e){petOn=true}' in js, "K20b pet defaults ON even when storage is blocked")

# ---- K21 (ux v7): cardHTML must close its page div — pages that nest inside each
# other inherit ancestor transforms and the peek strips land off-screen ----
ok("</div></div></div>';" in js, "K21 cardHTML closes page div (no page nesting)")

# ---- K22 (master review v7): taller cards so full portraits show, comfortable back
# face: min-height floor, wider art column, contain + blurred fill backdrop, acts pinned ----
ok("min-height:660px" in css, "K22a card height floor 660px")
ok("grid-template-columns:330px minmax(0,1fr)" in css, "K22b art column widened to 330px")
ok("object-fit:contain" in css, "K22c portrait fully visible (contain, not cover)")
ok('class="artfill"' in js and ".artfill" in css, "K22d blurred backdrop fills letterbox area")
ok(".acts{margin-top:auto" in css or "margin-top:auto" in css, "K22e action row pinned to card bottom")

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
ok('.notes' not in css and 'class="notes"' not in js,
   "K17g card note micro-list retired in v9 (merged into the operative bio)")
ok('tt("开工"' in js and 'tt("下班"' in js and 'tt("特训"' in js and
   'tt("销卡"' in js and '"set.closebtn": "回岗"' in i18njs,
   "K25a buttons speak like operatives (开工/下班/特训/销卡/回岗)")
ok('cfg.reasoning_effort!=null?cfg.reasoning_effort:tt("default"' in js,
   "K25c unset reasoning renders as 'default', never a dash")
ok('#t-close{margin-left:auto' in css and 'getElementById("t-close")' in js,
   "K25d resume button sinks into the drill action row, bottom right")
ok('setGwConn' in js and 'id="gwbanner"' in html and 'e instanceof TypeError' in js,
   "K25e dead gateway shows a retrying banner, never a raw 'Failed to fetch'")
ok('if(entry.card){var c=entry.card;' in js and 'archBox(474,y,"be",c.nick,subs)' in js,
   "K25f renderArch unpacks dgBackends {card:...} wrapper — titles never 'undefined'")
ok('"STRATA_ROUTER_PORT", "18075"' in open(os.path.join(ROOT,"gw","config.py"),encoding="utf-8").read(),
   "K25g open-source default port is 18075 — legacy 18080 untouched (master iron rule)")
ok("grid-template-columns:1fr 1fr" in css, "K17h two-column rows on wide screens")

# ---- K24 (ux v8): training page = drawers for every section + tag/bio edit
# + model-driven auto-generation gated on "model loaded" + art moved here ----
for _i in ('id="sect-tags"','id="sect-dossier"','id="sect-portrait"','id="sect-sampling"'):
    ok(_i in html and 'class="drw"' in html, "K24a drawer section present: " + _i)
ok('id="ed_tags"' in html and 'id="ed_lore"' in html and 'id="gen-meta"' in html
   and 'id="gen-hint"' in html, "K24b editable tags + bio + auto-generate button + hint")
ok("populateTrain" in js and "refreshGenGate" in js and '"router/gendossier"' in js
   and "collectCard" in js, "K24c train drawer fills from card, gen calls the gateway, save persists card meta")
ok("details.drw" in css and "[open]" in css, "K24d drawers collapse/expand via css")
ok('data-r="train"' in js and 'id="uploadart"' not in js,
   "K24e portrait tools left the card front — they live in the drawer now")

# ---- K26 (master review ux v10): action strip rebuilt — drill + clock-in on the
# left as one style family, status chip + timer ring on the right; fixed height;
# every card equalized so the rows never float up; save renamed; burn confirms;
# events above about; deck centered with symmetric peeks ----
_a = js.find('<div class="acts">'); _tr = js.find('data-r="train"')
_tg = js.find('data-r="toggle"'); _gr = js.find('class="actr"')
ok(_a > 0 and _a < _tr < _tg < _gr,
   "K26a acts order: drill+clock-in group left, status+ring group right")
ok('.actr{margin-left:auto' in css and '.ring{display:none' in css,
   "K26b right group pinned by .actr; ring no longer self-margined")
ok("height:64px" in css and "height:40px" in css and "min-height:56px" not in css,
   "K26c fixed 64px action strip with unified 40px controls")
ok('ps[j].style.height=mx+"px"' in js, "K26d cards equalized to deck max height")
ok('id="t-close"' in html and 'getElementById("t-close")' in js,
   "K26e resume wired in the drill page bottom row")
ok("back-close" not in js and "back-close" not in css and "back-close" not in html,
   "K26f the floating sticky resume button is gone entirely")
ok('"set.saveall": "保存"' in i18njs and '"set.saveall": "Save"' in i18njs
   and 'id="t-save" data-i18n="set.saveall">保存<' in html,
   "K26g file-it renamed to plain 保存/Save (it is a save, not a risk action)")
ok('confirm(tt("销卡' in js and "再点一次确认" not in js,
   "K26h burn card confirms through a dialog spelling out the consequence")
ok(html.find('id="sec-monitor"') < html.find('id="sec-dyn"') < html.find('id="sec-about"'),
   "K26i events moved up, about sits at the bottom")
ok("max-width:76ch" not in css and "max-width:74ch" not in css,
   "K26j hero/lead no longer width-capped below the other sections")
ok("margin:0 70px" in css and "translateX(40px)" in css and "translateX(98px)" in css,
   "K26k deck centered: symmetric 70px gutters, layered peeks kept")

# ---- K27 (flicker annihilation): 2s polling must not repaint anything unless
# the content actually changed; rebuilds are signature-gated, DOM writes are
# diff-gated, banner + fx canvas never strobe under model load ----
ok('if(dl._h!==h){dl._h=h;dl.innerHTML=h;return true}' in js,
   "K27a live spec rows rewritten only when changed")
ok('g.getAttribute("data-sig")===asig' in js and 'g.setAttribute("data-sig",asig)' in js,
   "K27b architecture svg rebuilt only on data/language change")
ok('if(mt._h!==mh){mt._h=mh;mt.innerHTML=mh}' in js,
   "K27c monitor tile grid rewritten only on change")
ok('if(tb._h!==rh){tb._h=rh;tb.innerHTML=rh}' in js,
   "K27d request table rewritten only on change")
ok('if(chip._c!==ccls){chip._c=ccls;chip.className=ccls}' in js
   and 'chip.className="";det.textContent=""' not in js,
   "K27e monitor chip class never wiped and re-added — transition strobe killed")
ok("LANG!==appliedLang" in js and "appliedLang=LANG" in js,
   "K27f full i18n sweep runs on language change, not every poll")
ok("okrun>=2" in js, "K27g gateway banner clears only after two clean polls — never flaps")
ok("now-lastFrame<FRAME" in js and "document.hidden" in js,
   "K27h fx canvas capped ~30fps and paused when the tab is hidden")
ok("function setTxt" in js, "K27i text writes diff-gated through one helper")

# ---- K28 (master review v10b): pet chat must be clearable; the top VRAM chip
# speaks about THIS card with honest numbers, bar = real free VRAM ----
ok('id="pc-new"' in html and 'getElementById("pc-new")' in js and
   'chatMsgs=[];renderChatLog()' in js,
   "K28a new-chat button clears the pet chat log")
ok('"pet.newchat"' in i18njs and 'data-i18n-title="pet.newchat"' in html,
   "K28b new-chat tooltip localized")
ok('"gpu.name": "显存占用"' in i18njs and '"gpu.name": "VRAM use"' in i18njs
   and '>外部显存</span>' not in html,
   "K28c top-bar label is 显存占用 — the ambiguous 外部显存 wording retires from the bar")
ok('tt("未运行"' not in js
   and 'bar.style.width="100%";return}' not in js
   and 'LASTGPU=c.running?{free:free,total:total}:null;' in js,
   "K28d no fake full bar when the holder is off: real smi numbers drive it; arch keeps holder-only data")
ok('data-i18n-title="gpu.holdtit"' in html and '"gpu.holdtit"' in i18njs,
   "K28e the strip explains in its tooltip what the bar actually measures")

# ---- K29 (master review v10.1): drill-page cosmetics + lexicon sweep ----
_ti=html.find('id="sect-tags"'); _de=html.find("</details>", _ti)
ok(_ti>0 and 'id="gen-meta"' in html and html.index('id="gen-meta"')>_de
   and html.index('id="gen-meta"') < html.index('id="t-save"'),
   "K29a auto-generate left the tags drawer — it sits on the action row, ahead of Save")
ok(html.index('id="gen-hint"') > _de, "K29b the gen hint travels with its button")
ok('.poprow{display:flex' in css and '#ed-artname{' in css,
   "K29c portrait row is a real flex row — the filename no longer crowds the buttons")
ok('rows="8"' in html and "min-height:170px" in css,
   "K29d the bio textarea shows an 80-150-char dossier without hiding the tail")
ok("先点卡片上的载入" not in js and "先载入再点" not in js,
   "K29e operative lexicon: auto-generate hints never fall back to 载入")

# ---- K30 (master's bug hunt): 409 conflation triaged honestly + adopt-confirm ----
rg=open(os.path.join(ROOT,"gw","routes.py"),encoding="utf-8").read()
bk=open(os.path.join(ROOT,"gw","backends.py"),encoding="utf-8").read()
ok("model not resident" in rg and "engine isn" in rg
   and "self._json(503," in rg and "self._json(502," in rg and "self._json(409," in rg,
   "K30a the generate route tells three truths apart: off-post 409, engine silent 503, no answer 502")
ok("time.sleep(1.2)" in rg, "K30b a silent probe earns one patient re-probe before 503 — engines flap mid-task")
ok("if self.resident() is not True:" not in bk,
   "K30c residency is judged once, at the route — no second hidden gate inside the backend")
ok("rj[0]===503" in js and "rj[0]===502" in js,
   "K30d each truth gets its own words client-side, and the button re-arms for a retry")
ok("confirm(tt(" in js and "tg.value=tgsv" in js and "lo.value=dos" in js,
   "K30e the generated profile waits for the user\u0027s OK before touching the fields — Cancel keeps them as-is")

sys.exit(0 if not F else 1)
