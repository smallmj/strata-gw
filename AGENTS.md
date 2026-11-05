# AGENTS.md — maintenance handbook

Read this first. It tells you where everything is, how to verify changes, and
the standing rules of this repo. Future maintenance sessions (human or AI)
should follow it without re-exploring.

## 1. File map

```
strata-router.py        entry point (thin) — starts gw/
gw/config.py            env/knobs: STRATA_HOME, STRATA_PYTHON, STRATA_ROUTER_PORT,
                        gateway.json loader, strata_home()/resolve_python()
gw/main.py              boot: scans strata-<name>.json next to the entry, spawns backends
gw/backends.py          per-model lifecycle: lazy spawn, load/unload/switch state machine
gw/routes.py            /v1/* OpenAI proxy + /router/* control API; PROXY_PATHS forwards
                        engine endpoints verbatim (404 passthrough = panel shows unavailable)
gw/console.py           serves the page: inlines index.html + i18n.js + app.js at render
gw/cards.py             cards/cards.json read/merge; virtual `_pet` / `_hero` keys
gw/events.py            persistent event log (survives reloads, not gateway restarts)
gw/gpu_free.py          optional external-VRAM yield protocol (/free + /system_stats)
console/index.html      structure; data-i18n annotations on every static string
console/app.js          one IIFE — ALL logic lives inside it (watch scope when patching)
console/i18n.js         window.__I18N__ = {zh:{...},en:{...}} — single word table
console/style.css       theme, ctlbar, pet stage, monitor tiles
cards/cards.json        factory cards (persona/dossier/art metadata)
gw-assets/              pet.png, character art, bg-loop.mp4, uploads/ (git-ignored)
launcher/               strata-gateway.cmd / .sh — GW_HOME single-line knob
config-examples/        copy-to templates; api_key fields are intentionally empty
tests/                  see §2
docs/                   README screenshots
```

## 2. Test commands

```bash
python3 tests/test_gateway_switch.py strata-router.py   # baseline 50+ behaviors (the big one)
for f in tests/test_*.py; do python3 "$f"; done          # the rest (sanitized/console_ctl/pet/…)
```

Expected: every file prints `ALL PASS`. The gateway suite starts stub backends
on ports 1809x/1810x — kill any local demo first (`lsof -ti:18090 | xargs -r kill`).
Anything else is a red flag to stop and fix, not to route around.

## 3. Forbidden tokens

`tests/test_sanitized.py` is the authority — see its `_STRICT_TOKENS` table.
Gist: no personal hardware/model/config identifiers anywhere in console/, gw/,
launcher/, config-examples/, the entry file; no personal paths or build hashes
in docs. Brand-word scan runs over the whole repo with **zero exceptions**
(write scan patterns as concatenations like `'co'+'m'+'fy'` so the scanner
never matches itself). Run it after ANY copy change; a red T9/T10 = leak.

## 4. Code conventions

- **stdlib only** in the gateway; no pip installs, Python 3.9+.
- **Every user-facing string is bilingual.** Static text → `data-i18n` key in
  console/i18n.js; dynamic text in app.js → `tt("中文","english")`. Never hardcode
  a raw literal into innerHTML/say/alert paths (T8l lint enforces this).
- Keep the boot flow intact: applyLang runs on every refresh; `act()` is the
  only place lifecycle ops start.
- Don't break the baseline suite: gateway JSON contracts (`/router/backends`,
  `/router/cards`, `/router/version`, 404 passthrough) are asserted verbatim.
- Console patches: stay inside the IIFE; `node --check console/app.js` after edits.
- Services started for testing must be stopped afterwards. Long-lived instances
  are the owner's job — agents write scripts/configs/verification, not daemons.

## 5. Release flow

1. `for f in tests/test_*.py; do python3 "$f"; done` — all green, twice.
2. `python3 tests/test_sanitized.py` — all green (brand/leak scans 0 hits).
3. Bump `VERSION` (single source of `/router/version` + header chip).
4. External actions need the owner's explicit go-ahead, one by one:
   `gh repo create` → push → `git tag vX.Y.Z && git push --tags` → `gh release create`.
5. Last check after publishing: `git ls-files | grep -E "strata-(qwen|sc117)|uploads/"` empty.

## 6. Commit trailer

Every commit carries:

```
git commit -m "feat: ..." -m "Written-by: qwen3.8-flash-next-iq3_s via strata-gw (RTX 3090, 64GB DDR4)"
```

If a session with different authorship lands a change, state it honestly in
that commit's trailer instead of omitting the line.
