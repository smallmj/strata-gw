# Strata Gateway (strata-gw)

The gateway sits between clients and a local Strata install, presenting every
backend as a card in one bilingual console. This glossary pins the domain
language the console, issues, and tests must use.

## Language

### Two version planes

**Strata**:
the installed suite and its webui, versioned by git tags (what `terminal/`
contains). _Avoid_: "the app", "upstream UI".
**Engine**:
the inference binary underneath serve, versioned separately (BUILD.json stamp).
"引擎版本 / engine version" always means this one. _Avoid_: conflating it with
the Strata tag.

### Caches (three distinct things — never mix)

**Conversation cache / 会话停放缓存**:
whole idle conversations parked in RAM by the engine so they can be restored
without reprompting; eviction is budget-driven and automatic. Actions are
**park / restore (停放 / 接回)**. _Avoid_: "session cache", "prefix cache".
**Prefix reuse / 前缀复用** (`reused`):
prompt tokens re-read from cache within/between requests; shown by Context
fill. Not the conversation cache.
**Expert VRAM cache / 专家显存缓存**:
expert slots resident in VRAM at runtime (the existing tile). Distinct from
**Expert heat / 专家热度** below.

### Experts

**Expert heat / 专家热度**:
the learned (layer × expert) usage ranking the engine saves as an
**Expert profile / 专家档案** (ranks only, no switches). Purely observational;
there is no load/unload an expert over HTTP.

### Queues (three distinct things — never mix)

**Engine queue / 引擎队列**:
serve-layer FIFO ahead of one backend (`queued`, `in_flight`, concurrency).
**Admission / 准入门槛**:
the optional engine-queue cap (`max_queue`) whose overflow answers 429
(`admission_full` / `queue_wait_timeout`).
**Generation gate / 出图闸**:
the gateway's own wait behind an external generator's queue before starting
local generation (event kind `gate`). Not the engine queue.

### VRAM

**Card yield / 让卡**:
releasing VRAM held by an external service so a card can load (the
`/free` + `/system_stats` protocol). _Avoid_: confusing it with the engine's
own vram reserve knob.

### Console product language

**Card / 特工卡**: one backend as presented in the deck.
**Recruit / 招募**: registering a new backend into the gateway.
**Go to work / 开工** and **clock out / 下班**: load and unload.
**Special training / 特训**: editing a card's dossier and parameters.
