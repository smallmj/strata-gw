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
import tempfile

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
ok('href="__GITHUB_URL__"' in bar and 'id="bar-gh"' in bar and 'target="_blank"' in bar,
   "K6 the GitHub mark rides the bar itself now (master's S5 call) — an icon, not a drawer")

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
_cf18=open(os.path.join(ROOT,"gw","config.py"),encoding="utf-8").read()
ok('"STRATA_ROUTER_PORT"' in _cf18 and "def router_port" in _cf18 and "return 18075" in _cf18
   and _cf18.count("18075")>=2 and '"18080"' not in _cf18,
   "K25g open-source default port is 18075 (env > gateway.json > default) — legacy 18080 never in config (master iron rule)")
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
ok('askDlg(tt("销卡"' in js and "再点一次确认" not in js,
   "K26h burn card confirms through a page-styled dialog spelling out the consequence")
ok(html.find('id="sec-monitor"') < html.find('id="sec-dyn"') < html.find('id="sec-about"'),
   "K26i events moved up, about sits at the bottom")
ok("max-width:76ch" not in css and "max-width:74ch" not in css,
   "K26j hero/lead no longer width-capped below the other sections")
ok("margin:0 70px" in css and "translateX(40px)" in css and "translateX(98px)" in css,
   "K26k deck centered: symmetric 70px gutters, layered peeks kept")

# ---- K27 (flicker annihilation): 2s polling must not repaint anything unless
# the content actually changed; rebuilds are signature-gated, DOM writes are
# diff-gated, banner + fx canvas never strobe under model load ----
ok('if(dl._h!==h){dl._h=h;dl.innerHTML=h;' in js,
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
ok("no operative is resident" in rg and "engine isn" in rg
   and "self._json(503," in rg and "self._json(502," in rg and "self._json(409," in rg,
   "K30a the generate route tells three truths apart: off-post 409, engine silent 503, no answer 502")
ok("time.sleep(1.2)" in rg, "K30b a silent probe earns one patient re-probe before 503 — engines flap mid-task")
ok("if self.resident() is not True:" not in bk,
   "K30c residency is judged once, at the route — no second hidden gate inside the backend")
ok("rj[0]===503" in js and "rj[0]===502" in js,
   "K30d each truth gets its own words client-side, and the button re-arms for a retry")
ok('askDlg(tt("自述出炉"' in js and "tg.value=(cur.tags||[]).join" in js and "lo.value=cur.dossier" in js,
   "K30e the generated profile waits for the user\u0027s OK before touching the fields — Cancel keeps them as-is")

# ---- K31 (master, 2026-11-07 round 2): operative-flavored prompts, ghost-writer, styled dialog, theme sweep, launcher ----
_cmdp=os.path.join(ROOT,"strata-gw.cmd")
ok(os.path.isfile(_cmdp), "K31a the repo ships strata-gw.cmd — the launcher everyone keeps re-inventing")
_ct=open(_cmdp,encoding="utf-8",errors="replace").read()
ok("taskkill /F /T" in _ct and "Get-NetTCPConnection" in _ct and "(Get-Location).Path" in _ct,
   "K31b the launcher sweeps its own old process tree (tree-kill via taskkill) and frees the port before starting — scoped to its own folder, a router living elsewhere never bleeds")
ok("特工" in bk and "GEN_PROMPT_OTHER" in bk and "{subject}" in bk,
   "K31c both prompts speak operative: a self-report, and a ghost-write brief for an off-post colleague")
ok("[:6]" in bk and "dossier[:lim]" in bk,
   "K31d six tags at most, and the bio is clamped to what the card's three display lines can hold")
ok("x.alive()" in rg and "no operative is resident" in rg,
   "K31e generation needs only ONE resident operative on the deck — any card's button then writes that card's bio")
ok("function askDlg" in js and 'id="gw-dlg"' in html and "confirm(tt(" not in js,
   "K31f every confirmation runs through one page-styled dialog — zero native browser popups left")
ok('askDlg(tt("自述出炉"' in js and "saveTrain" in js and "直接写入卡片" in js,
   "K31g the self-portrait dialog writes into the card on the spot when confirmed — tweak-first and discard are the other two doors")
ok("anyLive" in js and "由值班同事代笔" in js,
   "K31h the gate lights up whenever anyone is on post, and the hint says who will hold the pen")
ok("accent-color:var(--ac,var(--q))" in css and "scrollbar-color" in css
   and "background:linear-gradient(135deg,var(--ac,var(--q))" in css,
   "K31i sliders, the drill-page scrollbar and the primary buttons all follow the palette the user picked in the tag drawer")

# ---- K32 (master repro 2026-11-07: 502 on BOTH cards — the thinker ate the whole budget) ----
ok('"enable_thinking": False' in bk and '"reasoning_effort": "none"' in bk,
   "K32a the self-report ask tells the engine to skip the soliloquy — both switches, engines disagree on which they honor")
ok('"max_tokens": 650' in bk, "K32b the budget outgrew 420 — a thinking model spent it all on thinking and died at finish=length")
ok('msg.get("content") or msg.get("reasoning_content")' in bk,
   "K32c if the engine monologues anyway, the parser still digs the JSON out of the reasoning")

# ---- K33 (master 2026-11-07): one click, both tongues ----
ok("author.translate_en(g1)" in rg and 'langs["zh"]' in rg,
   "K33a master's order of 2026-11-07: pass two translates the Chinese report — English is born from Chinese, not a second muse")
ok("GEN_TRANSLATE" in bk and "Translate the following Chinese operative report" in bk,
   "K33f the English pass carries a translation brief, not a fresh self-report prompt")
ok('g2 = author.gendossier("en", subject=subject)' in rg,
   "K33g if the Chinese pass alone falls over, the author still tries English on its own — one empty slot is better than a 502")
ok("genPend" in js and "t[other]=genPend.tags[other]" in js and "l[other]=genPend.lore[other]" in js,
   "K33b saving merges the language nobody edited from the generation — the English view stops showing Chinese")
ok("t.zh=o.slice()" in js and "t.en=o.slice()" in js,
   "K33c legacy flat tags seed both slots before the merge, so old cards never lose content")
ok('tt("中文标签："' in js and 'tt("英文档案：","English bio: ")' in js,
   "K33d the confirm dialog shows all four sections, labeled in the UI's language")

ok("rj[1].tags?{zh:{tags:rj[1].tags" in js,
   "K33e a half-updated pairing (new page, old backend) still renders the legacy single-tongue reply instead of blanks")

# ---- K34 (UI refresh S1): the token layer — font, status ladder, light palette ----
ok('@font-face' in css and 'jbmono-latin.woff2' in css,
   "K34a a local @font-face carries the numeric font — no CDN, the box stays offline")
ok('https://' not in css and 'http://' not in css,
   "K34b negative pin: the stylesheet references no remote source")
ok('--font-num' in css and css.count('var(--font-num)') >= 6,
   "K34c the numeric typeface ships as a token and feeds the data elements")
ok(all(t in css for t in ('--warn:', '--na:')) and 'var(--warn)' in css and 'var(--na)' in css,
   "K34d the status ladder has four rungs (--ok/--warn/--err/--na) and they are consumed")
_l = css.find('html[data-theme=light]{')
_lb = css[_l:css.find('}', _l)] if _l >= 0 else ""
ok(_l >= 0 and all(t in _lb for t in ('--q:', '--s:', '--ok:', '--warn:', '--err:', '--muted:', '--line:')),
   "K34e light is a standalone palette — brand, status and neutrals re-inked, not an inversion")
ok(':focus-visible' in css, "K34f visible keyboard focus exists on the page")
ok('html[data-theme=light] .cfback{' in css,
   "K34g the card's flipped back re-inks for light instead of keeping a hardcoded dark skin")
_font = os.path.join(ROOT, "gw-assets", "jbmono-latin.woff2")
with open(_font, "rb") as _ff:
    _magic = _ff.read(4)
ok(_magic == b"wOF2",
   "K34h the shipped font blob is a real woff2 — served locally, no download step exists to fail")
ok(os.path.isfile(os.path.join(ROOT, "gw-assets", "LICENSE-JetBrainsMono.txt")),
   "K34i the OFL license ships beside the font")

# ---- K35 (UI refresh S2): component layer — bands, honest empties, bar truth ----
ok('class="mband"' in js and '.mband{' in css,
   "K35a the twelve tiles are read in named semantic bands, not one soup")
ok('class="t-empty"' in js and '.t-empty' in css,
   "K35b an empty request table says so — fake dash rows no longer mime a breakage")
_g = html[html.find('id="gpuhold"'):]
_g = _g[:_g.find('</div>')]
ok('id="gfree"' not in _g and 'id="gforce"' not in _g and 'id="gpubtns"' in html,
   "K35c the top bar pill only reads out; the yield-VRAM actions stand outside it")
_k5d = re.search(r"#gpuhold \.bar i\{([^}]*)\}", css)
ok(_k5d and "width:0" in _k5d.group(1),
   "K35d the VRAM pill bar opens empty — a detecting state must not look like a full card")
ok('class="tick"' in js and '.pbar .tick' in css,
   "K35e the RAM rail carries its hot-level tick where the number only said it")
ok('pbar none' in js and '.pbar.none' in css,
   "K35f waiting-for-data rails read as hatched grey, never as colored full")
_i18 = open(os.path.join(ROOT, "console", "i18n.js"), encoding="utf-8").read()
ok("KV 复用 tok" in _i18 and "生成 tok" in _i18 and "gen tok" in _i18 and "reused tok" in _i18,
   "K35g the request table headers carry their units in both tongues")

# ---- K36 (UI refresh S3): health summary strip — one verdict, flagged items,
# freshness. The twelve tiles answer "what"; this answers "should I worry". ----
ok('id="mon-health"' in html and 'role="status"' in js,
   "K36a an at-a-glance health verdict sits under the monitor state bar, announced politely")
ok("HTEMP=90" in js and "HRAM=95" in js and "HPOW=95" in js,
   "K36b the worry thresholds (degC / RAM % / power % of cap) are named constants, not buried magic")
_hb = re.search(r"\.hbadge\.h-ok\{([^}]*)\}", css)
_hw = re.search(r"\.hbadge\.h-warn\{([^}]*)\}", css)
_ha = re.search(r"\.hbadge\.h-alarm\{([^}]*)\}", css)
ok(_hb and _hw and _ha and "var(--ok)" in _hb.group(1) and "var(--warn)" in _hw.group(1)
   and "var(--err)" in _ha.group(1) and "#mon-health" in css,
   "K36c the badge rides the same status ladder as everything else (ok/warn/alarm)")
ok(_i18.count('"mon.h.tit"') == 2,
   "K36d the strip explains its own thresholds in both tongues via one i18n title")
ok("h._v!==vs" in js and "ag._t!==at" in js,
   "K36e the verdict re-inks only when it changes; the ageing text is a lone textContent tick, never a repaint")
ok("MONTS=Date.now()" in js and "Math.round((Date.now()-MONTS)/1000)" in js,
   "K36f freshness is measured from the last good /metrics tick, never assumed")

# ---- K37 (UI refresh S4): the three small honesty cuts — copyable endpoint,
# the idle policy's edit door beside its read-out, and "—" that says which no. ----
ok('id="set-pcopy"' in html and 'cpText("http://127.0.0.1:"' in js,
   "K37a the settings port row hands over the OpenAI base_url in one click")
ok('execCommand("copy")' in js and "navigator.clipboard" in js,
   "K37b copy works on plain-LAN http too — clipboard API first, execCommand keeps the fall")
ok('data-act="copyport"' in js and 'data-act="cfgjump"' in js,
   "K37c the card spec lines carry their own doors: copy the port, edit the idle policy")
ok('class="sdim"' in js and "没在看" in js,
   "K37d a live figure not being watched admits 没在看 — the lone dash no longer shrugs")
ok(".crow.hl" in css and ".sdim" in css,
   "K37e the jump lands visibly (highlighted row) and the not-watched note reads calm")
ok("CFGFLASH" in js and 'closest(".crow")' in js and 'scrollIntoView({behavior:"smooth",block:"center"})' in js,
   "K37f cfgjump opens the config drawer and lands the eye on the ROW that owns the key (scroll + timed highlight; focus attempted but not asserted)")
ok(js.count("paintHomePort();wireSetHomePort()") == 2,
   "K37g the ⚙ gear itself wires the port/home controls — the panel was dead when opened that way")

# ---- K38 (master's S5 note): the monitor reads as two tidy two-group rows,
# not a soup of ragged bands; groups are divided, narrow screens stack. ----
ok('class="mrow"' in js and 'class="mdiv"' in js and 'class="mgrp"' in js,
   "K38a the twelve tiles assemble as rows of two labelled groups with a divider between")
ok('i+=2' in js and 'repeat(var(--c)' in css and '.mdiv{' in css,
   "K38b group widths follow their tile count; the divider is a real 1px line, not margin folklore")
ok('BANDS=[\n  {label:tt("推理速度","inference")' in js and '"主机","host"),keys:["cpu","ram","disk"]}' in js,
   "K38c inference rides beside host, GPU & VRAM beside the expert cache — the pairings master asked for")
ok(".mrow{flex-wrap:wrap" in css or ".mrow{flex-direction:column" in css,
   "K38d on narrow screens the two groups stack instead of squinting into slivers")

# ---- K39 (master's S5 note): settings drawers — one shape language, honest
# compact prose, and the one-line GitHub drawer retires to a top-bar icon. ----
ok('id="bar-gh"' in html and 'id="set-git"' not in html,
   "K39a the GitHub drawer retires; the mark rides the top bar's tail where eyes already sweep")
_seg = re.search(r"\n\.seg\{([^}]*)\}", css)
_tbtn = re.search(r"\n\.tbtn,\.verchip\{([^}]*)\}", css)
ok(_seg and "999px" not in _seg.group(1) and "var(--r-" in _seg.group(1)
   and _tbtn and "99px" not in _tbtn.group(1) and "var(--r-" in _tbtn.group(1),
   "K39b one radius language across the drawers — pills and rectangles stop competing")
ok('#setpop input[type=text]' in css or '#setpop .poprow input' in css,
   "K39c every field in the drawers wears the house frame — no bare browser-default inputs sneak in")
ok("不认名字。挪位置二选一" in _i18 and "改完重启网关才生效" in _i18,
   "K39d the drawer prose says what it means in half the breath, in both tongues")
ok("不认文件夹名" not in _i18 and "端口改动下次启动网关才生效" not in _i18,
   "K39e the old winded wordings are gone, not parked in a corner")

# ---- K40 (master's S5 tail note): the dark settings popover was a stack of
# semi-transparent veils — 66% over page text, then 60% of that, then 50%. ----
_pop = re.search(r"#setpop\{([^}]*)\}", css)
_sec = re.search(r"#setpop \.sec\{([^}]*)\}", css)
_drw = re.search(r"details\.drw\{([^}]*)\n[^}]*\}", css)
ok(_pop and "background:var(--pop)" in _pop.group(1),
   "K40a the popover paints on a dedicated opaque panel token, not the page's translucent card veil")
_rootm = re.search(r":root\{(.{0,900})", css, re.S)
_lightm = re.search(r"html\[data-theme=light\]\{([^}]*)\}", css)
ok(_rootm and _lightm and "--pop:" in _rootm.group(1)
   and all(re.search(r"--pop[a-z]*:#[0-9a-fA-F]{3,8};", b) for b in (_rootm.group(1), _lightm.group(1))),
   "K40b both themes define the popover stack as solid hex colours — no rgba veil sneaks back in")
ok(_sec and _drw and "transparent" not in _sec.group(1) and "transparent" not in _drw.group(1),
   "K40c the inner drawer levels step lighter/darker on solids instead of stacking more transparency")
_i = css.find("#setpop .poprow input[type=password]")
_b = css.find("#setpop .poprow button{")
ok(_i >= 0 and _b >= 0
   and "var(--card)" not in css[_i:_i+320] and "var(--popfield)" in css[_i:_i+320]
   and "var(--card)" not in css[_b:_b+220] and "var(--popsec)" in css[_b:_b+220],
   "K40d fields and buttons inside the popover sit on solid pop tokens too — no var(--card) veil survives a level deeper")

# ---- T7 (v0.2): the orphan card's grey state points the way; the burn-card
# button's orphan-only visibility is load-bearing (master's zero-delete rule) --
ok('tt("未入册","not enrolled")' in js, "T7a orphan labels read 未入册, not 未安装")
ok("未安装" not in js and "未安装" not in html, "T7b the old 未安装 wording is gone from the console")
ok('del.style.display=(!b&&m)?' in js, "T7c burn-card keeps its orphan-only visibility logic")
ok('del.style.display=m?' not in js, "T7d negative pin: delete never reaches normal cards")
ok('data-r=orphanguide' in js, "T7e orphan cards carry the 未入册 guide line in cardHTML")

# ---- T9 (v0.2): the recruit entry + first-run onboarding checklist ---------
ok('id="addrow"' in html and 'id="gw-add"' in html, "T9a the recruit entry row lives under the deck")
ok('data-i18n="add_op"' in html, "T9b the entry button goes through the i18n word source")
ok('function openOnboard(' in js, "T9c the onboarding checklist renderer exists")
ok('openOnboard()' in js, "T9d zero-card users land on the checklist instead of a blank deck")
ok('qs("router/onboard' in js and 'router/onboard?check=1' in js,
   "T9e the checklist pulls /router/onboard and fires ?check=1 on demand")
ok('function openWiz(' in js, "T9f the recruit wizard entry exists (shell until T10, page must run)")

# ---- T10 (v0.2): the three-step full-screen recruit wizard ------------------
ok('ov.id="wiz"' in js and "wiz-steps" in js, "T10a full-screen wizard layer with a three-step bar")
ok("router/setup/models" in js, "T10b the wizard reads the live catalog (setup/models)")
ok("famcard" in js and "tiercard" in js, "T10c split columns: family cards left, tier cards right")
ok('tt("尝鲜","experimental")' in js, "T10d preview families carry the experimental badge")
ok('"32768"' in js and '"1048576"' in js and "k8v4" in js and '"fp16"' in js,
   "T10e step2 params: context presets + the full kv set (no raw args)")
ok('tt("本地 GGUF 目录","local GGUF dir")' in js and 'tt("数据目录","data dir")' in js,
   "T10f local gguf/data dir inputs live in step2")
ok(not re.search(r"退役|卸载模型|uninstall", js + html + css, re.I),
   "T10g zero-delete vocabulary guard (the feature does not exist)")

# ---- T11 (v0.2): live enroll view + top chip + the 重新入册 badge ----------
ok('id="wizchip"' in html and "router/setup/status" in js,
   "T11a the top bar chip exists and status polling is wired")
ok("rebadge" in js and 'tt("重新入册","recruit again")' in js,
   "T11b failed history raises the retry badge with the 重新入册 label")
ok("forgeNow" in js, "T11c done feeds forgeNow - the T12 flip animation data source")
ok('id="wiz-log"' in js and "wizpill" in js, "T11d step3 renders the terminal-style live log with a status pill")

# ---- T12 (v0.2): new-card flip + the disk map inside the gear -------------
ok("facedown" in js and "forgeNow.has" in js,
   "T12a freshly enrolled cards spawn face-down driven by forgeNow")
ok(".card.facedown .cbody" in css and "cfback" in css,
   "T12b the face-down spawn reuses the cback 3D mechanism with a forging watermark")
ok('id="dsk"' in html and "renderDisk" in js and "router/disk" in js,
   "T12c the gear drawer carries the read-only disk map, loaded lazily on open")
_db=js.split("function renderDisk",1)[1].split("\n}",1)[0] if "function renderDisk" in js else ""
ok("1e9" in _db and "1073741824" not in _db and "1024" not in _db,
   "T12d disk-map sizes use the 10^9 website GB convention (the legacy VRAM gbf stays binary - different industry, out of scope)")
ok('tt("共享"' in js and "used_by" in js and 'tt("路径找不到"' in js,
   "T12e shared packs get the 共享 annotation and dangling paths get flagged")

# ---- T13 (v0.2): i18n full-pair + whole-repo self-check guards -------------
import json as _json
try:
    _m = _json.loads(i18njs[i18njs.index("{"):i18njs.rindex("}") + 1])
except Exception:
    _m = {}
ok(_m.get("zh") and set(_m.get("zh", {})) == set(_m.get("en", {})),
   "T13a i18n zh/en key sets are exactly equal - every string ships as a pair")
ok(not re.search(r"[^.a-zA-Z]confirm\s*\(", js + html),
   "T13b zero native confirm() in the console - askDlg owns every verdict")
ok(not re.search(r"com" + r"fy", js + html + css + i18njs, re.I),
   "T13c zero legacy brand word anywhere in the console trio+table")

# ---- T20 (field feedback): anti-overflow, tune grid, setpop scroll+drawers,
#      disk map relocated to the About section with paging + per-model drawers
import re as _re2
def _rule(name):
    m=_re2.search(r"\."+_re2.escape(name)+r"\{([^}]*)\}", css)
    return m.group(1) if m else ""
_m=_re2.search(r"#setpop\{([^}]*)\}", css)
_setpop=_m.group(1) if _m else ""
_m=_re2.search(r"\.famcard,\.tiercard\{([^}]*)\}", css)
ok("line-clamp" in css and css.count("text-overflow:ellipsis")>=2 and _m and "overflow:hidden" in _m.group(1),
   "T20a wizard cards clamp long copy - line clamps, ellipsis, hidden overflow")
ok("white-space:nowrap" in _rule("wstep") and "text-overflow:ellipsis" in _rule("wstep"),
   "T20b step-bar labels can never wrap out of their pills")
ok("max-height" in _setpop and "overflow-y:auto" in _setpop,
   "T20c the gear popover scrolls - nothing hides below the fold")
_m=_re2.search(r'id="setpop".*?</header>', html, _re2.S)
_sp=_m.group(0) if _m else ""
ok("dsk" not in _sp and _sp.count('<details class="drw"')>=3,
   "T20d the settings popover dropped the disk map and folds into drawers")
ok(html.count('id="dsk"')==1 and 'id="dsk-nav"' in html and "sec-about" in html[:html.index('id="dsk"')],
   "T20e the disk map now lives inside the About section, exactly once")
_r=js[js.index("function dkPaint"):js.index("function dkPaint")+1800]
ok("<details" in _r and "<summary" in _r,
   "T20f every mapped model renders as its own drawer inside the disk card")
ok("DKPAGE" in js and "dsk-nav" in js,
   "T20g the disk card pages through models instead of one endless column")
ok("wiz-tune" in js and "wiz-sum" in js and "wiz-prms" in js,
   "T20h step 2 is a designed two-zone grid, not a left rail over blank space")
ok(".wiz-tune{" in css and ".wiz-sum{" in css and ".wiz-prms{" in css,
   "T20i the tune grid, its summary rail and the param grid all have skins")
ok("wizTier" in js,
   "T20j the summary rail reads real tier numbers (download/RAM/Arena), not guesses")
_m=_re2.search(r"function dkPaint.*?\n}\n", js, _re2.S)
ok(bool(_m) and "1e9" in _m.group(0) and "1073741824" not in _m.group(0),
   "T20k relocated disk map keeps the 10^9 website GB convention")

# ---- T21: About section = one wide card, two pages sliding into view,
#      engine dossier and disk map never share the screen
ok(html.count('inf-card wide')==1 and 'class="inftrack"' in html and 'class="infpages"' in html
   and html.index('id="dsk"')>html.index('inftrack'),
   "T21a engine page and disk page live in ONE wide card as a sliding track")
ok(".inftrack{" in css and "transition:transform" in css and "flex:0 0 100%" in css and "overflow:hidden" in _rule("infpages"),
   "T21b the slide has a real animated transform, pages sized to the card")
ok("INFPG" in js and "infPaint" in js and "translateX(-" in js,
   "T21c page flips ride one state var and repaint by transform")
ok('data-ip="0"' in html and 'data-ip="1"' in html and "about.tab.eng" in i18njs and "about.tab.disk" in i18njs,
   "T21d tabs exist with i18n keys for both pages (zh/en pair guaranteed by T13a)")
ok(html.count('id="dsk"')==1 and "dsk-nav" in html,
   "T21e the relocated disk card keeps its single mount point and pager rail")

# ---- T22: the onboarding page can find the engine itself, or be pointed at it
ok('id="onb-detect"' in js and 'id="onb-hpath"' in js and 'id="onb-hset"' in js
   and "router/home/probe" in js and 'router/home"' in js,
   "T22f the not-found row carries both routes: one-click search and manual point-at-it")
ok(".onb-act{" in css and "onb-hmsg" in css,
   "T22g the home-finding row has its own skin and a message slot")

# ---- T23: gear popover hosts the engine-home finder AND the router port knob
_m=_re2.search(r'id="setpop".*?</header>', html, _re2.S)
_sp2=_m.group(0) if _m else ""
ok('id="set-loc"' in _sp2 and 'id="set-port"' in _sp2 and _sp2.count('<details class="drw"')>=5,
   "T23a both the Strata-home finder and the port knob live as drawers in the gear popover")
ok("router/port" in js and "set-pnew" in js and "restart" in js and "set-detect" in js,
   "T23b the port round-trip and the settings-page search button are wired in app.js")
ok("set.locsec" in i18njs and "set.portsec" in i18njs and "set.porthint" in i18njs,
   "T23c the new drawer labels ship as zh/en pairs (parity guaranteed by T13a)")

# ---- T24 (field feedback): the home/port drawers redesigned, and each control
#      answers on ITS OWN message line - a hidden message is no reaction at all
_m=_re2.search(r'id="set-loc".*?</details>', html, _re2.S)
_loc=_m.group(0) if _m else ""
_m=_re2.search(r'id="set-port".*?</details>', html, _re2.S)
_prt=_m.group(0) if _m else ""
ok("set-hmsg" in _loc and "set-pmsg" in _prt and "set-hmsg" not in _prt and "set-pmsg" not in _loc,
   "T24a each drawer carries its own message slot - feedback can never hide in the other drawer")
ok("set.latauto" in _loc and "set.happly" in _loc and "set.locnote" in _loc,
   "T24b the home drawer is three labelled moves: status line, search button, manual apply")
ok("set.pnowlab" in _prt and "set.porthint" in _prt,
   "T24c the port drawer names what is live and when a new port applies")
ok("sayP" in js and "sayP(tt" in js and js.index("sayP")<js.index("function openSettings"),
   "T24d port feedback writes sayP - the message line inside the port drawer")
ok('.lrow{' in css and '.cbtn.wide{' in css,
   "T24e the status rows and the full-width search button have skins")

ok('x.families||["qw"+"en","swift"]' in js,
   "T25g wizard tier lists obey the upstream default: a tier without a families field belongs to qwen/swift only")

# ---- T26a: the enroll bar — a recruit of a 30 GB model must SHOW its percent ----
ok("function parseProg(" in js,
   "T26a1 a dedicated progress parser reads the download lines")
ok('<progress id="wizprog"' in js and "wizprog" in js,
   "T26a2 the live wizard mounts a real progress bar element")
ok("parseProg(d.lines)" in js,
   "T26a3 the live tick drives the bar from the status lines, not only the raw scroll")

# ---- T27: the wizard shows the fit, the catalog carries the table ----
ok("setup/fit" in js and 'id="w-fit"' in js,
   "T27e the tuning step asks the gateway for a fit verdict and paints one budget line")
ok("x2.ram_gb" in js,
   "T27f the tier cards surface the official RAM figures before the download starts")

# ---- T28 pins: the residency clock on the card + the phase in the ring ----
ok('"off_in_s"' in js or "off_in_s" in js,
   "T28f the console reads the countdown field off /router/backends")
ok("router/poke" in js,
   "T28g the card offers a way to keep a resident model awake")
ok("busy.phase" in js or '"phase"' in js,
   "T28h the in-flight ring shows which stage the operation is at")

# ---- T29 pins: history banners itself, live replay stays clean ----
ok("wizhist" in js,
   "T29d the wizard shows archived attempts as dated history, never as live output")

# ---- T30 pin: the release banner ----
ok("router/release" in js and "relbar" in js,
   "T30d the console listens for a newer release and has a place to say it")

# ---- T31 pins: the narrow-screen contract ----
_i = css.find("@media (max-width:760px)")
_blk = css[_i:_i + 800] if _i >= 0 else ""
ok(_blk != "", "T31a the phone breakpoint exists at all")
ok(".card{grid-template-columns:minmax(0,1fr)" in _blk,
   "T31b flip cards stack into one column instead of squeezing 330px+1fr")
ok("#ctlbar{flex-wrap:wrap" in _blk,
   "T31c the sticky control bar may wrap on a narrow face instead of overflowing")
ok(".acts{flex-wrap:wrap" in _blk,
   "T31d the action row breathes instead of cutting buttons off")

# ---- T32: a resumed download must not lie to the progress bar ----
# upstream setup.py keeps finished 32 MB pieces in <name>.part.chunks and
# prints "<have> / <total> GB (<pct>%)" counted from the WHOLE file. The
# console's parseProg must take those resumed lines as-is: no reset to 0.
def _fn_src(text, name):
    i = text.find("function " + name)
    if i < 0:
        return ""
    depth, j = 0, i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        j += 1
    return ""

_pp = _fn_src(js, "parseProg")
ok(bool(_pp), "T32a1 parseProg is extractable for a real run")
if _pp:
    import subprocess as _spp
    import tempfile as _tfpp
    _script = _pp + r"""
var a = parseProg(["  m.gguf: 21.00 / 32.60 GB (64%)"]);
var b = parseProg(["  m.gguf: 21.00 / 32.60 GB (64%)",
                   "  m.gguf: 24.00 / 32.60 GB (74%)"]);
var ok = a && b && +b.cur > +a.cur && b.tot === a.tot && b.pct === 74;
console.log(ok ? "RESUME-MONOTONIC" : "BAD " + JSON.stringify([a, b]));
"""
    _tf = os.path.join(tempfile.gettempdir(), "t32pp.js")
    with open(_tf, "w", encoding="utf-8") as _f:
        _f.write(_script)
    _r = _spp.run(["node", _tf], capture_output=True, text=True, timeout=20)
    os.remove(_tf)
    ok("RESUME-MONOTONIC" in _r.stdout,
       "T32a parseProg reads resumed-download lines as standing where they are, not 0%")

# ---- Q series (issue #18, T3): the engine queue panel in Monitor ------------
# Q1 the frontend-synthesized "queued" badge is RETIRED — ADR-0001's one
# exception finally closes: the chip follows the engine's own live.state,
# the panel carries engine-reported counts, nothing is invented.
ok('if(loaded&&lv.queued>0' not in js, "Q1 synthesized queued badge is gone from app.js")
ok('queued:tt("排队中","queued")' in js and 'else if(state==="queued")' in js,
   "Q1b guard: the STATE queued entry + detail branch stay for the engine's own queued state")

# Q2 the panel shell: right after #mon, before #mon-strip (design record §0.1)
ok('id="mon-queue"' in html
   and html.index('id="mon-queue"') > html.index('id="mon"')
   and html.index('id="mon-queue"') < html.index('id="mon-strip"'),
   "Q2 #mon-queue sits in the Monitor block between the bands and the strip")

# Q3 (review fix #4 — single source): the queue screen copy lives ONLY as
# tt() literals in queuePanel; the i18n table keeps what data-i18n consumes
# (q.band). Pins: every zh/en pair on screen exists as a literal at the
# panel seam, and the dead table copies are gone (a table label nobody
# renders is a second source waiting to drift).
_qt = _json.loads(i18njs[i18njs.index("{"):i18njs.rindex("}") + 1])
def _tpairs(src, pairs):
    return all('tt("%s","%s")' % p in src for p in pairs)
_qcopy = (("排队", "queued"), ("在飞", "in flight"), ("并发", "concurrency"),
          ("准入门槛", "admission cap"),
          ("超上限时 429 admission_full · 等待超时 429 queue_wait_timeout",
           "over cap → 429 admission_full · wait timeout → 429 queue_wait_timeout"),
          ("拒收", "refused"), ("RAM 底线", "RAM floor"), (" · 预算 ", " · budget "),
          ("等待", "waiting"), ("准入中", "admitting"), ("槽位", "slots"),
          ("槽", "slot"), ("状态", "state"), ("读入 tok", "read tok"),
          ("生成 tok", "generated tok"), ("持有 tok", "held tok"),
          ("待机", "idle"), ("生成中", "generating"),
          ("并行槽位空闲", "parallel slots idle"), ("引擎未驻留", "engine off post"),
          ("排队信息在开工后点亮", "queue lights up once the engine answers metrics"),
          ("出图闸等待中 · ", "generation gate holding · "), ("秒", "s"),
          ("该引擎未报告这一字段", "this engine does not report this field"),
          ("外部出图任务仍占卡——引擎请求被挡在门外",
           "an external image job still holds the card — engine requests are held at the door"))
_qdead = sorted(k for k in _qt.get("zh", {}) if k.startswith("q.") and k != "q.band")
ok("q.band" in _qt.get("zh", {}) and "q.band" in _qt.get("en", {}),
   "Q3a the live data-i18n key (q.band) stays a zh/en pair")
ok(_tpairs(_fn_src(js, "queuePanel"), _qcopy),
   "Q3b all %d queue screen pairs ride tt() literals in queuePanel" % len(_qcopy))
ok(not _qdead, "Q3c dead q.* table copies removed (%d left over)" % len(_qdead))

# Q8 (review fix #1, red first): the fail-and-stop latch is a PAUSE, not a
# final stop. The default flow — open page, select an off-post card, clock
# in — must light in-flight/concurrency again; design §0.4 keeps the stop on
# failure but the RESUME is event-driven, like the MCP card's (:179). act()
# (clock in/out) and a saved token both re-arm the v1/status probe.
_act = _fn_src(js, "act")
ok(bool(_act) and "_v1fail=0" in _act,
   "Q8a clocking in/out re-arms the v1/status probe: act() resets the fail latch")
_svh = re.search(r'getElementById\("save"\)\.onclick=function\(\)\{(.*?)\n\};', js, re.S)
ok(bool(_svh) and "_v1fail=0" in _svh.group(1),
   "Q8b a saved token re-arms the v1/status probe (a 401 latch must not outlive the token)")

# Q8c (review fix #2, same event): the heat latch _heat1 mirrors the MCP
# line — a saved token releases it so the next scroll-in re-probes (the
# 401/no-token hidden face is a recovery face, not a permanent one).
ok(bool(_svh) and "_heat1=0" in _svh.group(1),
   "Q8c a saved token releases the heat latch: next scroll-in re-probes (the :179 event)")

# Q4 the queue renderer is a pure function; node runs it over every face variant
_qp = _fn_src(js, "queuePanel")
ok(bool(_qp), "Q4a queuePanel is extractable for a real run")
if _qp:
    import subprocess as _sqp
    import tempfile as _tqp
    _SHIM_ZH = r"""
var LANG="zh";
function tt(z,e){return LANG==="zh"?z:e}
function num(v){if(v==null)return "\u2013";var s=""+Math.round(v);
  return s.replace(/([0-9])(?=([0-9]{3})+$)/g,"$1,")}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
"""
    def _qcase(args, lang="zh"):
        """Run queuePanel(args...) in node over the shim; returns its HTML."""
        _tf = os.path.join(tempfile.gettempdir(), "qcase_%s.js" % lang)
        with open(_tf, "w", encoding="utf-8") as _f:
            _f.write(_SHIM_ZH.replace('var LANG="zh";', 'var LANG="%s";' % lang)
                     + _qp + "\nconsole.log(JSON.stringify(queuePanel(%s)));" % args)
        _r = _sqp.run(["node", _tf], capture_output=True, text=True, timeout=20)
        if _r.returncode != 0:
            ok(False, "queuePanel node run failed: " + _r.stderr[:200])
            return ""
        return _json.loads(_r.stdout)
    # engine truth drives the numbers: live.queued from /metrics, verbatim
    _h1 = _qcase('{"state":"idle","queued":3},null,null,null,true')
    ok("排队" in _h1 and ">3<" in _h1, "Q4b queued count renders from engine live.queued")
    # old engine without the field: a quiet dash, never an error
    _h2 = _qcase('{"state":"idle"},null,null,null,true')
    ok("\u2013" in _h2 and "该引擎未报告这一字段" in _h2,
       "Q4c absent live.queued degrades to dash + q.nofield title")
    # v1/status numbers: in flight + serving/requested concurrency, verbatim
    _h3 = _qcase('{"state":"generating","queued":0},{"concurrency":{"serving":2,"requested":4},'
                 '"activity":{"in_flight":5}},null,null,true')
    ok("在飞" in _h3 and ">5<" in _h3 and "并发" in _h3 and "2/4" in _h3,
       "Q4d in-flight and concurrency render from /v1/status")
    # v1/status absent (old engine 404): both stats dash, no error text
    _h4 = _qcase('{"state":"idle","queued":0},null,null,null,true')
    ok("在飞" in _h4 and "并发" in _h4 and "2/4" not in _h4
       and "429" not in _h4 and _h4.count(">–<") >= 2,
       "Q4e /v1/status missing: in-flight/concurrency dash")
    # admission cap: rendered only when set and >0; never a zero-cap
    _h5 = _qcase('{"state":"idle","queued":0},null,32,null,true')
    ok("准入门槛" in _h5 and ">32<" in _h5 and "429 admission_full" in _h5,
       "Q4f cap renders only when set + the 429 legend rides its title")
    for _caplit in ("null", "0"):
        _h6 = _qcase('{"state":"idle","queued":0},null,%s,null,true' % _caplit)
        ok("准入门槛" not in _h6, "Q4g no cap stat when unset(%s)" % _caplit)
    # refusal counters render only when the payload carries live.admission
    _h7 = _qcase('{"state":"idle","queued":0,"admission":{"total":9,"ram_floor":2,"budget":7}},null,null,null,true')
    ok("拒收" in _h7 and ">9<" in _h7 and "RAM 底线 2" in _h7 and "预算 7" in _h7,
       "Q4h refusal counters render verbatim from live.admission")
    _h8 = _qcase('{"state":"idle","queued":0},null,null,null,true')
    ok("拒收" not in _h8, "Q4i no refusal stat when the engine lacks the counters")
    # parallel: slot table + waiting/admitting only when the engine reports slots
    _h9 = _qcase('{"state":"generating","queued":1,"waiting":2,"admitting":1,'
                 '"slots":[{"slot":0,"state":"generating","prompt_read":1204,"generated":512},'
                 '{"slot":1,"state":"idle","held_tokens":8192}]},null,null,null,true')
    ok("<table" in _h9 and "1,204" in _h9 and ">512<" in _h9 and "8,192" in _h9
       and "待机" in _h9 and "等待" in _h9 and ">2<" in _h9 and "准入中" in _h9,
       "Q4j parallel slots table renders engine rows verbatim")
    _h10 = _qcase('{"state":"idle","queued":0},null,null,null,true')
    ok("<table" not in _h10 and "并行槽位空闲" not in _h10 and "槽位" not in _h10,
       "Q4k not parallel: no table, no 'no slots' text")
    _h11 = _qcase('{"state":"idle","queued":0,"waiting":0,"admitting":0,"slots":[]},null,null,null,true')
    ok("<table" in _h11 and "并行槽位空闲" in _h11,
       "Q4l parallel but slots empty: single idle-row message")
    # generation gate: the secondary line ONLY while holding — gw's own state
    _h12 = _qcase('{"state":"idle","queued":0},null,null,{"waited_s":6},true')
    ok("出图闸等待中" in _h12 and "6" in _h12 and 'role="status"' in _h12
       and "被挡在门外" in _h12, "Q4m gate line renders only while gen_gate holds")
    _h13 = _qcase('{"state":"idle","queued":0},null,null,null,true')
    ok("出图闸" not in _h13, "Q4n no gate line when not holding (never a 'gate idle' row)")
    # backend off: panel stays, stats dash, honest off-post note; no metrics: placeholder
    _h14 = _qcase('{"state":"unloaded"},null,32,null,false')
    ok("引擎未驻留" in _h14 and "准入门槛" not in _h14,
       "Q4o backend off: stats dash + q.off note, panel stays")
    _h15 = _qcase("null,null,32,null,true")
    ok("排队信息在开工后点亮" in _h15 and "<table" not in _h15,
       "Q4p no metrics yet: quiet placeholder")
    # zero synthesis: the renderer never invents a number the payload lacks
    _h16 = _qcase('{"state":"reading"},null,null,null,true')
    ok(">0<" not in _h16 and "排队" in _h16, "Q4q zero-synthesis: missing fields never become fake numbers")
    # EN mirror: the same payload speaks English
    _h17 = _qcase('{"state":"generating","queued":3,"admission":{"total":1,"ram_floor":0,"budget":1}},'
                  '{"concurrency":{"serving":1,"requested":1},"activity":{"in_flight":1}},2,'
                  '{"waited_s":3},true', lang="en")
    ok("queued" in _h17 and "in flight" in _h17 and "concurrency" in _h17
       and "admission cap" in _h17 and "refused" in _h17 and "generation gate holding" in _h17,
       "Q4r EN mirror of the whole panel")

# Q5 polling discipline: the queue rides the 2.5s tick + one small v1/status
# fetch with fail-and-stop; NO new timer is allowed anywhere (discipline guard:
# the timer count must stay exactly what it is today - 5 page loops + 2
# one-shot wizard/onboard ticks + the ONE heat 30 s timer (#22/T7), which the
# H-series pins as uniquely paired with its clearInterval and IO-scoped).
ok(js.count("setInterval") == 8,
   "Q5a the eight setInterval: page loops + wizard ticks + the single paired heat timer")
ok("v1/status" in js and "_v1fail" in js, "Q5b pollMetrics carries the v1/status fetch with fail-and-stop")

# Q6 the event stream names the gate (kind chip + status-ladder color)
ok('gate:tt("出图闸","gate")' in js, "Q6a KIND carries the canonical gate label")
ok(".ev.gate .kind" in css and "var(--warn)" in css, "Q6b .ev.gate rides the warn rung")

# Q7 the shared mcard primitives ship with the panel (design record §0.2)
for _cls in (".mcard", ".stat", ".qstats", ".sdot", ".mnote"):
    ok(_cls in css, "Q7 mcard primitive has a skin: " + _cls)

# ---- C: conversation cache card (issue #19, T4) ---------------------------
# Design record §2: #mon-cache .mcard rides the SAME 2.5s /metrics payload
# (d.conversation_cache) — zero new requests, zero synthesis. Card presence,
# each counter group and both degraded states are pinned against the stub
# factory payloads (tests/stub_common.py _conv_cache = the SIM_STRATA_CCACHE
# tri-state shipped by T1) run through a real node execution.

# C1 the card shell: right after #mon-queue, before #mon-strip (design §0.1)
ok('id="mon-cache"' in html
   and html.index('id="mon-cache"') > html.index('id="mon-queue"')
   and html.index('id="mon-cache"') < html.index('id="mon-strip"'),
   "C1 #mon-cache sits in the Monitor block right after #mon-queue")

# C2 (review fix #4): single source — the cache card's labels are tt()
# literals in cachePanel; the table keeps only what data-i18n consumes
# (cc.band label + cc.tit tooltip).
_ccopy = (("停放缓存读数在开工后点亮", "parking-cache readings light up once loaded"),
          ("引擎未上报会话停放缓存——较旧的引擎没有这些字段",
           "engine does not report the conversation cache — older build, fields absent"),
          ("未启用——引擎启动时未给停放预算",
           "disabled — no parking budget was set at engine boot"),
          ("停放", "parked"), ("停放大小", "parked size"), ("预算 ", "budget "),
          ("停放次", "parks"), ("接回次", "restores"), ("腾退", "evictions"),
          ("拒收", "refused"), ("RAM 底线", "RAM floor"), ("复用", "reuse"),
          (" tok", " tok"), ("尚未停放过会话", "nothing parked yet"),
          ("接回", "restored"), ("最近事件：", "last: "), ("前 · 上次 ", " ago · "),
          ("该引擎未报告这一字段", "this engine does not report this field"))
_cdead = sorted(k for k in _qt.get("zh", {}) if k.startswith("cc.")
                and k not in ("cc.band", "cc.tit"))
ok(all(k in _qt.get("zh", {}) and k in _qt.get("en", {}) for k in ("cc.band", "cc.tit")),
   "C2a the live cache keys (label + tooltip) stay zh/en pairs")
ok(_tpairs(_fn_src(js, "cachePanel"), _ccopy),
   "C2b all %d cache screen pairs ride tt() literals in cachePanel" % len(_ccopy))
ok(not _cdead, "C2c dead cc.* table copies removed (%d left over)" % len(_cdead))

# C3 the cache renderer is a pure function; node runs it over the stub faces.
# Helpers are extracted from app.js itself (not re-implemented here) so the
# node run exercises the real number/format rules.
_cp = _fn_src(js, "cachePanel")
ok(bool(_cp), "C3a cachePanel is extractable for a real run")
if _cp:
    import subprocess as _sc_c
    import tempfile as _tc_c
    import stub_common as _stub_c
    _HELP_C = "\n".join(filter(None, (_fn_src(js, _f) for _f in
                       ("num", "kfmt", "tstr", "mib", "mibFromMiB", "relm"))))
    _SHIM_C = r"""
var LANG="zh";
function tt(z,e){return LANG==="zh"?z:e}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
"""
    def _ccase(args, lang="zh"):
        """Run cachePanel(args...) in node over the shim; returns its HTML."""
        _tf = os.path.join(tempfile.gettempdir(), "ccase_%s.js" % lang)
        with open(_tf, "w", encoding="utf-8") as _f:
            _f.write(_SHIM_C.replace('var LANG="zh";', 'var LANG="%s";' % lang)
                     + _HELP_C + "\n" + _cp
                     + "\nconsole.log(JSON.stringify(cachePanel(%s)));" % args)
        _r = _sc_c.run(["node", _tf], capture_output=True, text=True, timeout=20)
        if _r.returncode != 0:
            ok(False, "cachePanel node run failed: " + _r.stderr[:300])
            return ""
        return _json.loads(_r.stdout)

    # happy face: the FULL stub conversation_cache object renders every group
    _cc_on = _json.dumps(_stub_c._conv_cache("on"))
    _hc1 = _ccase(_cc_on + ",true")
    ok(">2/8<" in _hc1, "C3b parked/slots render verbatim (parked 2 of 8)")
    ok("3.0 GiB" in _hc1 and "pbar warm" in _hc1 and "75.0%" in _hc1,
       "C3c parked size + budget bar ride bytes/budget_mib (binary units)")
    ok("预算 4.0 GiB" in _hc1, "C3d budget sub-line prints mibFromMiB(budget_mib)")
    ok(">12<" in _hc1 and ">9<" in _hc1,
       "C3e parks/restores counters render verbatim")
    ok("14/40" in _hc1 and "3.1K tok" in _hc1,
       "C3f reuse pair + reused_tokens render verbatim")

    # degraded face 1 (SIM_STRATA_CCACHE=absent / cc_mode="absent"): the whole
    # key is missing from an old engine — quiet "not available", card survives
    _hc2 = _ccase("null,true")
    ok("引擎未上报会话停放缓存——较旧的引擎没有这些字段" in _hc2
       and 'class="mnote na"' in _hc2,
       "C3g field-absent state renders the cc.nodata one-liner (mnote.na)")
    ok("stat" not in _hc2 and len(_hc2) > 0,
       "C3h field-absent state invents no stats and never blanks the card")
    # degraded face 0 (no metrics at all — pre-load / engine down): placeholder
    _hc3 = _ccase("null,false")
    ok("停放缓存读数在开工后点亮" in _hc3 and "stat" not in _hc3,
       "C3i no metrics yet: cc.ph placeholder, no invented stats")
    # degraded face 2 (SIM_STRATA_CCACHE=off / cc_mode="off"): enabled:false —
    # the disabled line rides a na dot + final text; zero IS data, not absence
    _hc4 = _ccase(_json.dumps(_stub_c._conv_cache("off")) + ",true")
    ok("未启用——引擎启动时未给停放预算" in _hc4 and "sdot na" in _hc4,
       "C3j enabled:false shows cc.disabled (sdot na + text, never color alone)")
    ok(">0/8<" in _hc4 and "stat" in _hc4 and "error" not in _hc4.lower(),
       "C3k disabled state keeps the stats (0 is data) and the card alive")
    ok("尚未停放过会话" in _hc4,
       "C3l last_at:null degrades to cc.never, no phantom timestamp")
    ok("pbar warm none" in _hc4,
       "C3m zero bytes → dashed .pbar.none (parked:0 rule)")

    import time as _t_c
    # refusal breakdown: refused_total>0 turns warn, the .s sub prints the two
    # counts (RAM floor / budget) — design record §2 field map row 5
    _hc5 = _ccase('{"enabled":true,"parked":1,"slots":4,"bytes":1048576,"budget_mib":4096,'
                  '"parks":3,"restores":1,"evictions":2,"refused":{"ram_floor":3,"budget":6},'
                  '"refused_total":6,"requests":9,"requests_reused":2,"reused_tokens":700,'
                  '"last_event":"parked","last_at":1000000,"last_tokens":900},true')
    ok('<div class="stat warn"><span class="k">拒收' in _hc5
       and ">6<" in _hc5 and "RAM 底线 3" in _hc5 and "预算 6" in _hc5,
       "C3n refused_total>0 rides the warn rung + RAM-floor/budget breakdown")
    ok('<div class="stat warn"><span class="k">腾退' in _hc5,
       "C3o evictions>0 (enabled) rides the warn rung")
    # refused_* absent (real v0.2.16 engine has no counters): quiet dash + title
    _hc6 = _ccase('{"enabled":true,"parked":0,"slots":8,"bytes":12582912,"budget_mib":1024,'
                  '"parks":0,"restores":0,"evictions":0,"requests":0,"requests_reused":0,'
                  '"reused_tokens":0},true')
    ok("拒收" in _hc6 and ">–<" in _hc6 and 'title="该引擎未报告这一字段"' in _hc6,
       "C3p absent refused_* → dash + q.nofield title, never a fake 0")
    ok("12 MiB" in _hc6 and "1.0 GiB" in _hc6 and " GB" not in _hc6,
       "C3q binary units: MiB <1GiB, GiB ≥1024MiB, no gbf-style 'GB' label")
    # last-event marker: a FORMAT of last_at (relm), never an invented number
    _hc7 = _ccase('{"enabled":true,"parked":1,"slots":2,"bytes":1,"budget_mib":2,'
                  '"last_event":"restored","last_at":%s,"last_tokens":1204},true' % (_t_c.time() - 120))
    ok("最近事件：接回" in _hc7 and "2 分前" in _hc7 and "1,204 tok" in _hc7,
       "C3r last row = last_event + relm(last_at) + last_tokens, zh template")
    ok(re.search(r"最近事件：停放 [0-9]{2}:[0-9]{2}前", _hc5),
       "C3s an event older than 2h prints the engine clock HH:MM, not a fake age")
    # zero-synthesis + honesty guards on the FULL stub face
    ok("1,800" not in _hc1 and "640" not in _hc1,
       "C3t last_prompt/last_reused never render (request-table detail)")
    _hc8 = _ccase('{"enabled":true},true')
    ok(">0<" not in _hc8 and "–" in _hc8 and "stat" in _hc8,
       "C3u sparse object: every absent field is a dash, never a 0")
    _he = _ccase(_cc_on + ",true", lang="en")
    ok("parked" in _he and "parked size" in _he and "budget 4.0 GiB" in _he
       and "parks" in _he and "restores" in _he and "evictions" in _he
       and "refused" in _he and "reuse" in _he and "last:" in _he and " ago" in _he
       and " GB" not in _he,
       "C3v EN mirror of the whole card (units stay binary)")
    _hd = _ccase(_json.dumps(_stub_c._conv_cache("off")) + ",true", lang="en")
    ok("disabled — no parking budget was set at engine boot" in _hd
       and "nothing parked yet" in _hd,
       "C3w EN degraded strings are the final §6 copy")

# C4 polling discipline: the card rides the EXISTING payload, adds no request
# and no timer (design §0.4 row 2; Q5a already pins setInterval==8).
_pc = _fn_src(js, "paintCache")
ok(bool(_pc) and "fetch" not in _pc,
   "C4a zero new requests: paintCache touches no fetch")
ok(bool(_pc) and "conversation_cache" in js,
   "C4b the card reads d.conversation_cache from the 2.5s pollMetrics payload")
ok(js.count("paintCache()") >= 2,
   "C4c renderMonitor repaints the card on both the no-data and data paths")
ok('id="mon-cage"' in html and 'getElementById("mon-cage")' in js,
   "C4d the card carries the dim updated-Ns-ago age like #mon-queue (§7 freshness)")
ok('data-i18n-title="cc.tit"' in html,
   "C4e cc.tit tooltip distinguishes the cache from KV/prefix on the label")

# ---- M: MCP servers card (issue #20, T5) ---------------------------------
# Design record §3: #mcp-card, a .mcard at the END of the Monitor block
# (after #mon-hint, before #train-src). Data rides the already-proxied
# /router/mcp (the T72 stub faces) and is fetched EVENT-DRIVEN ONLY (§0.4):
# first scroll into view (IO flag _mcp1), model switch, token save — no
# timer, fail-and-stop via _mcp404. Descriptions and engine error text ride
# title attributes through the attribute-safe escaper — never raw innerHTML.

# M1 the card shell: end of the monitor block (design §0.1 placement)
ok('id="mcp-card"' in html
   and html.index('id="mcp-card"') > html.index('id="mon-hint"')
   and html.index('id="mcp-card"') < html.index('id="train-src"'),
   "M1 #mcp-card sits at the end of the Monitor block, after #mon-hint")

# M2 (review fix #4): single source — the card body labels are tt()
# literals in mcpPanel; the table keeps mcp.band + mcp.tit (data-i18n).
_mcopy = (("引擎未提供 MCP 清单（或需要 token）", "engine exposes no MCP list (or needs the token)"),
          ("读取 MCP 清单…", "reading MCP list…"),
          ("未配置 MCP 服务器", "no MCP servers configured"),
          ("已连接", "connected"), ("错误", "failed"), ("已禁用", "disabled"),
          ("工具", "tools"))
_mdead = sorted(k for k in _qt.get("zh", {}) if k.startswith("mcp.")
                and k not in ("mcp.band", "mcp.tit"))
ok(all(k in _qt.get("zh", {}) and k in _qt.get("en", {}) for k in ("mcp.band", "mcp.tit")),
   "M2a the live MCP keys (label + tooltip) stay zh/en pairs")
ok(_tpairs(_fn_src(js, "mcpPanel"), _mcopy),
   "M2b all %d MCP screen pairs ride tt() literals in mcpPanel" % len(_mcopy))
ok(not _mdead, "M2c dead mcp.* table copies removed (%d left over)" % len(_mdead))

# M3 the MCP renderer is a pure function; node runs it over the stub faces
# (tests/stub_common.py _mcp_payload — the same face the gateway proxies,
# pinned by T72a-g). dgEsc is extracted from app.js itself so the node run
# exercises the REAL escaping discipline.
_mp = _fn_src(js, "mcpPanel")
ok(bool(_mp), "M3a mcpPanel is extractable for a real run")
if _mp:
    import subprocess as _smp
    import tempfile as _tsp
    import stub_common as _stub_m
    _SHIM_M = r"""
var LANG="zh";
function tt(z,e){return LANG==="zh"?z:e}
""" + _fn_src(js, "dgEsc") + "\n"
    def _mcase(args, lang="zh"):
        """Run mcpPanel(args...) in node over the shim; returns its HTML."""
        _tf = os.path.join(tempfile.gettempdir(), "mcase_%s.js" % lang)
        with open(_tf, "w", encoding="utf-8") as _f:
            _f.write(_SHIM_M.replace('var LANG="zh";', 'var LANG="%s";' % lang)
                     + _mp + "\nconsole.log(JSON.stringify(mcpPanel(%s)));" % args)
        _r = _smp.run(["node", _tf], capture_output=True, text=True, timeout=20)
        if _r.returncode != 0:
            ok(False, "mcpPanel node run failed: " + _r.stderr[:300])
            return ""
        return _json.loads(_r.stdout)

    # the happy face: one row per server, every value verbatim off the stub
    _full = _json.dumps(_stub_m._mcp_payload("full"))
    _hm1 = _mcase(_full + ",0")
    ok("strata-tools" in _hm1 and "weather" in _hm1 and "legacy-db" in _hm1
       and 'class="srvrow"' in _hm1, "M3b one .srvrow per server, names verbatim")
    ok("STDIO" in _hm1 and "HTTP" in _hm1 and "SSE" in _hm1,
       "M3c transport chips render the raw value uppercased")
    ok("已连接" in _hm1 and "sdot ok" in _hm1 and "fin ok" in _hm1,
       "M3d connected status: .fin.ok chip + sdot (never colour alone)")
    ok("错误" in _hm1 and "sdot err" in _hm1 and "fin err" in _hm1,
       "M3e error status rides the err rung (rows survive; error state is never hidden)")
    ok("upstream refused" in _hm1 and "&lt;weather.example&gt;" in _hm1
       and "<weather.example>" not in _hm1,
       "M3f engine error text renders verbatim but escaped into the title")
    ok("已禁用" in _hm1 and "sdot na" in _hm1,
       "M3g disabled status: neutral chip + sdot na")
    ok("工具 ×10" in _hm1 and "工具 ×0" in _hm1 and "工具 ×2" in _hm1,
       "M3h per-server tool count chips")
    ok("search_docs" in _hm1 and "prune_logs" in _hm1
       and "tail_live" not in _hm1 and "watch_deck" not in _hm1 and "+2" in _hm1,
       "M3i 8 visible tool chips then +N (cap 8 on the 10-tool server)")
    ok('title="full-text search over docs"' in _hm1,
       "M3j tool description rides the chip title")
    ok("&amp; parse &quot;&lt;html&gt;&quot;" in _hm1
       and 'parse "<html>"' not in _hm1,
       "M3k escaping-hostile description stays escaped inside the attribute")
    ok("in-process bundle" in _hm1, "M3l non-empty info renders as the .s line")

    # the degraded faces — the stub's empty face, and the fetch flags
    ok("未配置 MCP 服务器" in _mcase(_json.dumps(_stub_m._mcp_payload("empty")) + ",0"),
       "M3m empty servers face: mcp.none one-liner, card survives")
    ok("未配置 MCP 服务器" in _mcase('{"tools":0},0'),
       "M3n servers key absent: same mcp.none state")
    ok("读取 MCP 清单…" in _mcase("null,0"), "M3o pending: mcp.load one-liner")
    ok("引擎未提供 MCP 清单（或需要 token）" in _mcase("null,1"),
       "M3p the 404/401 face: mcp.nodata one-liner — quiet, never an error")
    _hq = _mcase(_full + ",1")
    ok("引擎未提供 MCP 清单" in _hq and "strata-tools" not in _hq
       and "srvrow" not in _hq,
       "M3q fail flag wins over stale data: no ghost rows after a failure")

    # unmapped status keeps the engine's own word in a neutral chip
    _hr = _mcase('{"servers":[{"name":"odd","transport":"ws",'
                 '"status":"handshaking"}]},0')
    ok("handshaking" in _hr and "已连接" not in _hr and "错误" not in _hr
       and "已禁用" not in _hr,
       "M3r unmapped status renders the engine value verbatim, uncolored")
    _hz = _mcase('{"servers":[{"name":"bare","status":"connected"}]},0')
    ok("工具 ×0" in _hz and "已连接" in _hz,
       "M3s sparse server: missing tools default to ×0, status still normalizes")

    # EN mirror: the same faces speak English with the §6 final copy
    _he = _mcase(_full + ",0", lang="en")
    ok("connected" in _he and "failed" in _he and "disabled" in _he
       and "tools ×10" in _he and "in-process bundle" in _he,
       "M3t EN mirror of the whole card")
    ok("reading MCP list" in _mcase("null,0", lang="en")
       and "engine exposes no MCP list" in _mcase("null,1", lang="en")
       and "no MCP servers configured" in _mcase('{"servers":[]},0', lang="en"),
       "M3u EN degraded strings are the final §6 copy")

# M4 fetch discipline (design §0.4): the already-proxied path with the model
# selector; event-driven only — IO first-in-view (_mcp1), model switch, token
# save; fail-and-stop (_mcp404) until the next event; NO new timer.
ok('router/mcp?model=' in js, "M4a fetch rides the existing /router/mcp proxy with the model selector")
ok(js.count("IntersectionObserver") == 3 and "_mcp1" in js,
   "M4b IO instances (disk map, MCP card, +1 heat section — #22 legitimate bump) gate the first fetch")
ok("_mcp404" in js and "_mcp404=0" in js,
   "M4c fail-and-stop flag: one failure ends the round, reset only by an event")
_sm = _fn_src(js, "selectModel")
ok(bool(_sm) and "fetchMcp()" in _sm, "M4d model switch re-fetches the MCP list")
_sm2 = re.search(r'getElementById\("save"\)\.onclick=function\(\)\{.*?\};', js, re.S)
ok(bool(_sm2) and "fetchMcp()" in _sm2.group(0), "M4e token save re-fetches the MCP list")
_pm = _fn_src(js, "paintMcp")
ok(bool(_pm) and "_h!==" in _pm and "fetch" not in _pm,
   "M4f paintMcp repaints under the K27 guard and touches no fetch")
_fm = _fn_src(js, "fetchMcp")
ok(bool(_fm) and ".catch(" in _fm and "setInterval" not in _fm,
   "M4g the one fetch carries its .catch (S7 balance) — no timer inside")
ok(js.count("setInterval") == 8,
   "M4h zero new setInterval: the MCP card adds nothing (Q5a's eight holds)")
ok('data-i18n="mcp.band"' in html and 'data-i18n-title="mcp.tit"' in html,
   "M4i card label + read-only tooltip ship as static i18n")
ok(".srvrow{" in css and ".srvrow:first-child{border-top:0}" in css,
   "M4j .srvrow skin with the first-row no-border rule (§3)")
ok("mcp-box" not in js + html and "loadMcp" not in js,
   "M4k negative pin: the retired MCP drawer's names never come back (T43 family)")

# ---- F: About engine facts (issue #21, T6) --------------------------------
# Design record §4: the About tab-0 card grows a SECOND .kvbar (#eng-facts)
# under the existing #eng-kv dossier. Chips ride d.engine.* off the SAME 2.5s
# pollMetrics payload — zero new fetches, zero new timers — and every field
# degrades individually: a missing fact omits its chip, never the block,
# never an error. factsPanel is pure: engine object in, chip HTML out.

# F1 the shell: #eng-facts is the second kvbar INSIDE tab 0, after #eng-kv
ok('id="eng-facts"' in html
   and html.index('id="eng-kv"') < html.index('id="eng-facts"')
   and html.index('id="eng-facts"') < html.index('id="dsk"'),
   "F1 #eng-facts sits in About tab 0 under #eng-kv and before tab 1's disk map")
ok(html.count('<div class="kvbar">') == 2 and 'data-i18n="about.facts"' in html,
   "F1b exactly two .kvbar blocks now; the new header rides about.facts")
ok('getElementById("eng-kv").innerHTML' in js,
   "F1c the legacy #eng-kv dossier keeps rendering from loadInfo (block untouched)")

# F2 (review fix #4): single source — the fact chips' labels are tt()
# literals in factsPanel; the table keeps about.facts (data-i18n header).
_fcopy = (("KV 布局", "KV layout"), ("KV 常驻", "KV resident"),
          ("投机解码", "speculation"), ("上下文", "context"),
          ("显存余量", "VRAM headroom"), ("显存竞技场", "VRAM arena"),
          ("线程池", "pool workers"), ("预填上限", "prefill cap"),
          ("引擎未上报运行事实", "engine reports no runtime facts"))
_fdead = sorted(k for k in _qt.get("zh", {}) if k.startswith("fact"))
ok("about.facts" in _qt.get("zh", {}) and "about.facts" in _qt.get("en", {}),
   "F2a the live facts header key stays a zh/en pair (F1b pins the data-i18n use)")
ok(_tpairs(_fn_src(js, "factsPanel"), _fcopy),
   "F2b all %d facts chip pairs ride tt() literals in factsPanel" % len(_fcopy))
ok(not _fdead, "F2c dead fact.*/facts.* table copies removed (%d left over)" % len(_fdead))

# F3 the renderer is a pure function; node runs it over the stub's engine
# face — tests/stub_common.py _facts_engine is the kit-mirrored field set,
# kv_resident pinned as the ratio face 0.92 there (design §4: the kit pins
# which face kv_resident speaks; the formatter's MiB fallback gets its own pin).
_fp = _fn_src(js, "factsPanel")
ok(bool(_fp), "F3a factsPanel is extractable for a real run")
if _fp:
    import subprocess as _sc_f
    import tempfile as _tc_f
    import stub_common as _stub_f
    _HELP_F = "\n".join(filter(None, (_fn_src(js, _f) for _f in ("num", "mibFromMiB"))))
    _SHIM_F = r"""
var LANG="zh";
function tt(z,e){return LANG==="zh"?z:e}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
"""
    def _fcase(eng, lang="zh"):
        """Run factsPanel(eng) in node over the shim; returns its HTML."""
        _tf = os.path.join(tempfile.gettempdir(), "fcase_%s.js" % lang)
        with open(_tf, "w", encoding="utf-8") as _f:
            _f.write(_SHIM_F.replace('var LANG="zh";', 'var LANG="%s";' % lang)
                     + _HELP_F + "\n" + _fp
                     + "\nconsole.log(JSON.stringify(factsPanel(%s)));" % _json.dumps(eng))
        _r = _sc_f.run(["node", _tf], capture_output=True, text=True, timeout=20)
        if _r.returncode != 0:
            ok(False, "factsPanel node run failed: " + _r.stderr[:300])
            return ""
        return _json.loads(_r.stdout)

    # the full stub face: eight chips in §4 order, values verbatim
    _fe = dict(_stub_f._facts_engine(), kv="k8v4", spec=4, max_context=524288)
    _hf = _fcase(_fe)
    ok(_hf.count('class="kvchip"') == 8, "F3b the full stub face renders eight .kvchip")
    ok(">k8v4<" in _hf and "KV 布局" in _hf, "F3c kv renders raw")
    ok(">92%<" in _hf and "KV 常驻" in _hf,
       "F3d kv_resident 0.92 (the stub-pinned ratio face) → 92%")
    ok(">4 (MTP×2)<" in _hf and "投机解码" in _hf,
       "F3e spec+mtp_max merge into one chip: 4 (MTP×2)")
    ok(">512K tok<" in _hf and "上下文" in _hf,
       "F3f max_context rides the existing ctx-tile K-tok idiom")
    ok(">21.5 GiB<" in _hf and "显存余量" in _hf and ">512 MiB<" in _hf and "显存竞技场" in _hf,
       "F3g vram_free_mib/arena_mib render through mibFromMiB (22000→GiB, 512→MiB)")
    ok(">12<" in _hf and "线程池" in _hf and ">4,096<" in _hf and "预填上限" in _hf,
       "F3h pool_workers/prefill_cap render through num()")
    _ord = ["KV 布局", "KV 常驻", "投机解码", "上下文", "显存余量",
            "显存竞技场", "线程池", "预填上限"]
    ok(all(_hf.index(a) < _hf.index(b) for a, b in zip(_ord, _ord[1:])),
       "F3i chip order matches the §4 table exactly")
    # per-field degrade, evidenced on the stub face: drop ONE key at a time —
    # only that chip is omitted, the other seven survive, the block never dies
    for _fld, _lab in (("kv", "KV 布局"), ("kv_resident", "KV 常驻"),
                       ("spec", "投机解码"), ("max_context", "上下文"),
                       ("vram_free_mib", "显存余量"), ("arena_mib", "显存竞技场"),
                       ("pool_workers", "线程池"), ("prefill_cap", "预填上限")):
        _hd = _fcase({k: v for k, v in _fe.items() if k != _fld})
        ok(_lab not in _hd and _hd.count('class="kvchip"') == 7,
           "F3j stub without engine.%s → that chip alone is omitted" % _fld)
    # spec absent but mtp_max present: the chip keys on spec, still omitted
    _hs = _fcase({k: v for k, v in _fe.items() if k != "spec"})
    ok("投机解码" not in _hs and "MTP" not in _hs and _hs.count('class="kvchip"') == 7,
       "F3k mtp_max without spec invents no speculation chip")
    # mtp_max absent: spec survives alone, no MTP suffix
    _hn = _fcase({k: v for k, v in _fe.items() if k != "mtp_max"})
    ok(">4<" in _hn and "MTP" not in _hn and _hn.count('class="kvchip"') == 8,
       "F3l mtp_max absent → the speculation chip survives without the suffix")
    # zero is data: an explicit 0 renders, it is NOT a missing field
    _hz = _fcase(dict(_fe, vram_free_mib=0, spec=0))
    ok(">0 MiB<" in _hz and "显存余量" in _hz and "投机解码" in _hz
       and _hz.count('class="kvchip"') == 8,
       "F3m zero values (vram_free_mib=0, spec=0) render — never treated as absent")
    # kv_resident fallback face: >1 goes through mibFromMiB (kit pins ratio as primary)
    ok(">14.1 GiB<" in _fcase(dict(_fe, kv_resident=14451)),
       "F3n kv_resident above 1 falls back to mibFromMiB (14451 → 14.1 GiB)")
    # engine object absent / empty → one nodata chip, nothing else, no error
    for _nul in ({}, None):
        _ho = _fcase(_nul)
        ok("引擎未上报运行事实" in _ho and _ho.count('class="kvchip"') == 1
           and "<error" not in _ho.lower() and "报错" not in _ho,
           "F3o engine %s → facts.nodata chip only — quiet, never an error" % (_nul,))
    # engine strings are escaped on the way in (kv is engine-produced text)
    _hx = _fcase(dict(_fe, kv='a<b&"c'))
    ok("a&lt;b&amp;&quot;c" in _hx and 'a<b&"c' not in _hx,
       "F3p kv value escapes — engine text never injects markup")
    # EN mirror of the whole face (labels from the §6 copy)
    _he = _fcase(_fe, lang="en")
    ok(all(x in _he for x in ("KV layout", "KV resident", "speculation", "context",
                              "VRAM headroom", "VRAM arena", "pool workers", "prefill cap"))
       and ">k8v4<" in _he and ">92%<" in _he,
       "F3q EN mirror carries the final §6 labels, values unchanged")
    ok("engine reports no runtime facts" in _fcase({}, lang="en"),
       "F3r EN nodata is the §6 final copy")

# F4 paint discipline: the block rides the existing 2.5s tick — paintFacts
# touches no fetch, repaints only when the chip HTML string changed (K27),
# and renderMonitor calls it on BOTH the no-data and data paths.
_pf = _fn_src(js, "paintFacts")
ok(bool(_pf) and "fetch" not in _pf and "setInterval" not in _pf,
   "F4a zero new requests, zero new timers: paintFacts touches no fetch/setInterval")
ok(bool(_pf) and "_h!==" in _pf,
   "F4b repaint guarded by a single facts-HTML-changed compare (K27 anti-flicker)")
ok(bool(_pf) and 'getElementById("eng-facts")' in _pf and "factsPanel(" in _pf,
   "F4c paintFacts bridges mon.data engine into factsPanel")
ok(js.count("paintFacts()") >= 2,
   "F4d renderMonitor repaints facts on both the no-data and data paths")
_ok_st = open(os.path.join(ROOT, "tests", "stub_common.py"), encoding="utf-8").read()
_ok_kt = open(os.path.join(ROOT, "tools", "sim-strata", "serve", "server.py"),
              encoding="utf-8").read()
def _fbody(src):
    i = src.index("def _facts_engine")
    j = min(src.index(x, i + 1) for x in ("\ndef ", "\nclass ") if x in src[i + 1:])
    return src[i:j]
ok(_fbody(_ok_st) == _fbody(_ok_kt),
   "F4e stub_common and the kit carry _facts_engine byte-identically (no drift)")
ok("**_facts_engine()" in _ok_st and "**_facts_engine()" in _ok_kt,
   "F4f both faces merge the fact fields into their /metrics engine dict")
# F4g/h (review fix #5): the gw suite's OWN inline Stub is the third copy —
# it must carry and merge the same factory, or the two suites drift silently.
_ok_gw = open(os.path.join(ROOT, "tests", "test_gateway_switch.py"), encoding="utf-8").read()
ok("def _facts_engine" in _ok_gw and "**_facts_engine()" in _ok_gw,
   "F4g the gw suite inline Stub defines AND merges _facts_engine (three copies, one face)")
if "def _facts_engine" in _ok_gw:
    ok(_fbody(_ok_gw) == _fbody(_ok_st),
       "F4h the gw-suite _facts_engine copy is byte-ident (stub_common / kit / gw suite)")

# F5 no formatting fork: the chips reuse the §0.3 helpers, they never format
# MiB/GiB locally (design rule 3 — values verbatim through mibFromMiB/num).
ok("mibFromMiB" in _fp and "GiB" not in _fp and " MiB" not in _fp,
   "F5a factsPanel has no local MiB/GiB formatting fork (mibFromMiB only)")

# =====================================================================
# H series (issue #22, ticket T7): the 专家热度 section.
# Design record §5/§6/§9; strata-face §51 (webui experts.js probe
# semantics: show iff 200 AND configured:true). The gateway gains NO
# route (decided deviation from the spec's /router/expert-heat mapping —
# the console rides the catch-all with the engine path verbatim; the
# comment lands in gw/routes.py and by the fetch here).
# =====================================================================

# H1 the heat factory stays byte-ident stub<->kit (F4e pattern) — the
# tri-state configured arg (#22) must not fork the two faces.
def _hbody(src):
    i = src.index("def _heat_payload")
    j = min(src.index(x, i + 1) for x in ("\ndef ", "\nclass ") if x in src[i + 1:])
    return src[i:j]
ok(_hbody(_ok_st) == _hbody(_ok_kt),
   "H1 stub_common and the kit carry _heat_payload byte-identically (no drift)")
ok('SIM_STRATA_HEAT", "on"' in _ok_kt and 'HEAT_MODE == "off"' in _ok_kt
   and '_heat_payload(HEAT_MODE != "false")' in _ok_kt,
   "H1b kit SIM_STRATA_HEAT speaks the same tri-state on|false|off as the stub")

# H2 (review fix #4): single source — the heat card/hover copy is tt()
# literals in heatCard/heatHover; the table keeps sec.experts (data-i18n).
_hcopy = (("档案存档 ", "profile saved "), ("约每 ", "auto-saves every ~"),
          (" 分自动存档", " min"),
          ("· 刷新失败，显示上次数据", "· refresh failed, showing last read"),
          ("热度数据不完整，等待下一次存档",
           "heat data incomplete \\u2014 waiting for the next save"),
          ("最热常驻", "warmest"), ("层", " layers"),
          ("专家热度档案存档于 ", "expert heat profile saved "),
          ("最亮=该层第 1 热 · 越暗排名越靠后 · 透明=无档案",
           "brightest = rank 1 in its layer \\u00b7 dimmer = later \\u00b7 clear = unranked"),
          ("滑到格上读该层的保温排名", "hover a cell to read its rank in its layer"),
          ("无档案", "no rank"), ("层 ", "layer "), (" · 专家 ", " · expert "),
          (" · 该层排名 ", " · rank "), ("", " in layer"))
_hdead = sorted(k for k in _qt.get("zh", {}) if k.startswith("heat."))
ok("sec.experts" in _qt.get("zh", {}) and "sec.experts" in _qt.get("en", {}),
   "H2a the live section-label key stays a zh/en pair (H3b pins the data-i18n use)")
ok(_tpairs((_fn_src(js, "heatCard") or "") + (_fn_src(js, "heatHover") or ""), _hcopy),
   "H2b all %d heat screen pairs ride tt() literals in heatCard/heatHover" % len(_hcopy))
ok(not _hdead, "H2c dead heat.* table copies removed (%d left over)" % len(_hdead))

# H3 the shell: hidden whole-section wrapper between the MCP card and the
# dynamic section (design §0.1 order); a 1px in-flow sentinel is the IO
# anchor — a display:none target never intersects, so the probe needs an
# always-visible neighbour at the section's position.
ok('id="experts-sec"' in html and 'id="experts-io"' in html
   and 'style="display:none"' in html[html.index('id="experts-sec"'):html.index('id="experts-sec"') + 90],
   "H3a #experts-sec ships hidden with an in-flow #experts-io sentinel")
ok('data-i18n="sec.experts"' in html and 'id="heat-body"' in html,
   "H3b section label is an i18n key and the card body is #heat-body")
ok(0 <= html.find('id="experts-sec"') and html.find('id="experts-sec"') > html.find('id="mcp-card"')
   and html.find('id="experts-sec"') < html.find('id="sec-dyn"'),
   "H3c experts sits after the monitor block and before 动态 (design §0.1)")

# H4 the gate is a pure function — hidden faces mirror the degraded table:
# 404 hidden, 200 configured:false hidden, 401 hidden, network error
# hidden; only 200+configured:true shows (§5 + strata-face probe semantics).
_hg = _fn_src(js, "heatGate")
ok(bool(_hg), "H4a heatGate is extractable for a real run")
if _hg:
    import subprocess as _sc_h
    import json as _js_h
    _SHIM_H = r"""
var LANG="zh";
function tt(z,e){return LANG==="zh"?z:e}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
"""
    def _hcase(fnexpr, lang="zh", extra=""):
        _tf = os.path.join(tempfile.gettempdir(), "hcase_%s.js" % lang)
        with open(_tf, "w", encoding="utf-8") as _f:
            _f.write(_SHIM_H.replace('var LANG="zh";', 'var LANG="%s";' % lang)
                     + extra + "\n" + _hg + "\n"
                     + (_fn_src(js, "tstr") or "") + "\n"
                     + (_fn_src(js, "heatPos") or "") + "\n"
                     + (_fn_src(js, "heatAlpha") or "") + "\n"
                     + (_fn_src(js, "num") or "") + "\n"
                     + (_fn_src(js, "heatCard") or "") + "\n"
                     + "console.log(JSON.stringify(%s));" % fnexpr)
        _r = _sc_h.run(["node", _tf], capture_output=True, text=True, timeout=20)
        if _r.returncode != 0:
            ok(False, "heat node run failed: " + _r.stderr[:300])
            return None
        return _js_h.loads(_r.stdout)
    ok(_hcase("heatGate(404,null)") == 0, "H4b 404 face: hidden (never dead UI)")
    ok(_hcase("heatGate(200,{configured:false,ranks:0,rank:[]})") == 0,
       "H4c 200 configured:false face: hidden exactly like the 404 (T70e twin)")
    ok(_hcase("heatGate(401,null)") == 0 and _hcase("heatGate(0,null)") == 0,
       "H4d 401/no-token and a failed fetch also gate closed")
    ok(_hcase("heatGate(200,{configured:true})") == 1, "H4e only 200+configured:true opens")

    # H5 pure formulas, pinned against hand-computed literals (design §5):
    # heatPos is the row-major index->cell map (§9.1 / T70c: rank[19]=1 on
    # the 4x8 face sits at l=2,e=3); heatAlpha is the 0.06+0.94*(1-r/(E-1))^2.2
    # ramp — r0 opaque, r1 ~0.730, tail washes to 0.060.
    _pos = _hcase("heatPos(19,8)")
    ok(_pos == {"l": 2, "e": 3},
       "H5a heatPos(19,8) -> l2 e3: row-major rank[19] face (T70c twin)")
    ok(_hcase("heatAlpha(0,8).toFixed(3)") == "1.000"
       and _hcase("heatAlpha(1,8).toFixed(3)") == "0.730"
       and _hcase("heatAlpha(7,8).toFixed(3)") == "0.060",
       "H5b heatAlpha known values: rank0=1.000 rank1=0.730 rank7=0.060 (E=8, exponent 2.2)")

    # H6 the card renderer is pure over the stub payload (kit-shrunken 4x8,
    # rank (e+3l)%8): meta carries L x E + every_min; digest counts rank<=1
    # per expert (E0 sits top-2 in 2 layers); legend + hover hint ship as
    # the text fallback (never colour alone); a malformed payload degrades
    # in place of the canvas with heat.bad (§5 table), and the stale flag
    # only appends to the meta row.
    import stub_common as _stub_h
    _hp = _stub_h._heat_payload()
    _hc = _hcase("heatCard(%s,0)" % _js_h.dumps(_hp)) or ""
    ok(_hc is not None and "4\u00d78" in _hc and "10" in _hc,
       "H6a meta row renders layers x experts + every_min verbatim")
    ok("E0\u00d72" in _hc and "最热常驻" in _hc and "E1\u00d71" in _hc and "E2\u00d71" in _hc
       and "E3\u00d71" not in _hc,
       "H6b digest: rank<=1 count per expert, top 3 (E0x2,E1x1,E2x1), zh copy")
    ok('id="heatgrid"' in _hc and 'id="heat-read"' in _hc
       and "滑到格上" in _hc and "最亮=" in _hc,
       "H6c canvas + readout + legend/hint text fallback in one card")
    _hcE = _hcase("heatCard(%s,0)" % _js_h.dumps(_hp), lang="en") or ""
    ok("warmest" in _hcE and "hover a cell" in _hcE and "brightest" in _hcE,
       "H6d EN mirror of the whole card")
    _hcB = _hcase("heatCard({configured:true,every_min:10,saved_at:1763560000.0,"
                  "layers:4,experts:8,ranked:0,rank:[]},0)") or ""
    ok("热度数据不完整" in _hcB and 'id="heatgrid"' not in _hcB,
       "H6e malformed payload: heat.bad in place of the canvas, no empty shell")
    _hcS = _hcase("heatCard(%s,1)" % _js_h.dumps(_hp)) or ""
    ok("刷新失败" in _hcS and "4\u00d78" in _hcS,
       "H6f stale flag appends heat.stale and keeps the grid")
    # H6g (review fix #6, red first): engine-sourced numbers never ride
    # HTML/aria raw — every_min is esc()'d, an escaping-hostile payload
    # cannot break out of the meta row (dgEsc discipline, heat's seam).
    _hcX = _hcase("heatCard({configured:true,every_min:'<i>x</i>',saved_at:1763560000.0,"
                  "layers:4,experts:8,ranked:32,rank:new Array(32).fill(0)},0)") or ""
    ok("<i>x</i>" not in _hcX and "&lt;i&gt;x&lt;/i&gt;" in _hcX,
       "H6g every_min is escaped into the meta row (no HTML injection)")
    # H6h (review fix #7, red first): a configured payload WITHOUT saved_at
    # omits the saved segment entirely — never the epoch's local clock
    # printed as fake truth (ADR-0001: absent field = silence, not a zero).
    _hcN = _hcase("heatCard({configured:true,every_min:10,layers:4,experts:8,ranked:32,"
                  "rank:new Array(32).fill(0)},0)") or ""
    ok("档案存档" not in _hcN and "profile saved" not in _hcN and "约每" in _hcN,
       "H6h missing saved_at omits the saved segment (no epoch pseudo-time)")
    # H6i (review fix #6): layers/experts go through the §0.3 num() — the
    # thousands rule is the SAME face the queue stats pinned (Q4j's 1,204).
    _hcV = _hcase("heatCard({configured:true,every_min:10,saved_at:1763560000.0,"
                  "layers:1234,experts:8,ranked:9872,rank:new Array(9872).fill(0)},0)") or ""
    ok("1,234\u00d78" in _hcV and "1234\u00d78" not in _hcV,
       "H6i layers x experts ride num() thousands formatting in meta (and aria)")

# H7 fetch seam: the catch-all path verbatim with the model selector (the
# decided deviation — NOT a /router/expert-heat mapping; gw/routes.py
# carries the matching comment). First probe on first intersect (_heat1),
# model switch re-probes like the MCP card; one fetch, one .catch (S7).
ok("api/expert-heat?model=" in js and 'router/expert-heat' not in js,
   "H7a the probe rides the catch-all (api/expert-heat?model=) — zero new gateway route")
ok("_heat1" in js and '"experts-io"' in js and '"experts-sec"' in js,
   "H7b IO gates the first probe off the in-flow sentinel then follows the section")
_hio = _fn_src(js, "heatIo")
ok(bool(_hio) and "isIntersecting" in _hio and "_heat1" in _hio
   and "setInterval(_heatTick,30000)" in _hio and "clearInterval(_heattimer)" in _hio,
   "H7c the 30 s timer lives ONLY inside the IO lifecycle (start on enter, clearInterval on leave)")
ok(js.count("setInterval(_heatTick,30000)") == 1 and "clearInterval(_heattimer)" in js
   and "clearInterval(_heattimer)" in _hio,
   "H7d the one new timer is uniquely paired with its clearInterval (Q5a's eight)")
_htk = _fn_src(js, "heatTick")
ok(bool(_htk) and "fetchHeat" in _htk and "setInterval" not in _htk and "IntersectionObserver" not in _htk,
   "H7e heatTick only re-fetches — no IO, no timer inside the tick")
_fh2 = _fn_src(js, "fetchHeat")
ok(bool(_fh2) and ".catch(" in _fh2 and "setInterval" not in _fh2,
   "H7f the one heat fetch carries its .catch (S7 balance) — no timer inside")
_sm3 = _fn_src(js, "selectModel")
ok(bool(_sm3) and "fetchHeat()" in _sm3, "H7g model switch re-probes the heat face (per-model truth)")

# H8 zero synthesis: the grid paints ONLY the engine rank[] cells through
# the pinned formulas — layers/experts/rank read from the payload, nothing
# is invented (ADR-0001).
_hd = _fn_src(js, "heatDraw")
ok(bool(_hd) and "heatAlpha(" in _hd and "d.layers" in _hd and "d.experts" in _hd
   and "rank" in _hd,
   "H8a heatDraw consumes d.layers/d.experts/d.rank via heatAlpha — engine array only")
_ph = _fn_src(js, "paintHeat")
ok(bool(_ph) and "_h!==" in _ph and "fetch" not in _ph,
   "H8b paintHeat repaints under the K27 guard and touches no fetch")
_hr = _fn_src(js, "heatRepaint")
ok(bool(_hr), "H8c heatRepaint exists for the theme/lang canvas re-read (--s)")
ok('applyTheme(root.dataset.theme==="dark"?"light":"dark")' in js
   and re.search(r'getElementById\("theme"\)\.onclick=function\(\)\{[^}]*heatRepaint', js)
   and re.search(r'function applyLang\(\)\{.*heatRepaint\(\);', js, re.S),
   "H8d repaint is hooked next to the theme click and applyLang (design §5)")

sys.exit(0 if not F else 1)
