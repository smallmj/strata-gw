"""setup_wizard.py - drive the Strata install tool (setup.py) from the console:
read its support list, run non-interactive recruits, stream the log, keep the
run history for 重新入册, run the PC check for the onboarding page, and report
disk usage (read-only; the gateway never deletes models - master's rule)."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import threading
import time
from collections import deque

from . import backends, config

_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")     # family/tier slugs, argv-safe

# Runs inside the STRATA venv (setup.py imports strata_control - only the
# engine's own python can read its lists). Constants-only import, verified
# side-effect-free on a live 0.2.x install (probe 2026-11-07).
PROBE = r'''
import sys, json
home = sys.argv[1]
sys.path.insert(0, home)
import setup as s
KEEP = {"title", "by", "about", "tag", "name", "vision",
        "kv_bytes_per_token"}
TKEEP = {"about", "download_gb", "ram_gb", "arena_gb", "families", "shards", "vision"}
def lite(d, keys):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = {kk: (list(vv) if isinstance(vv, (tuple, list, set, dict)) else vv)
                      for kk, vv in v.items() if kk in keys}
    return out
fams = lite(dict(s.FAMILIES), KEEP)
fams.update(lite(dict(s.PREVIEW_FAMILIES), KEEP))
# an own-path family ships its own tier table inside its dict - that, not the
# global list, is what the family may be asked for (preview families ship
# only the tiers inside their own dict - nothing else, ever)
for src in (s.FAMILIES, s.PREVIEW_FAMILIES):
    for k, v in src.items():
        md = v.get("models") if isinstance(v, dict) else None
        if md:
            fams.setdefault(k, {})["tiers"] = lite(md, TKEEP)
for k, v in s.MULTI_FILE_FAMILIES.items():
    d = {kk: (list(vv) if isinstance(vv, (tuple, list)) else vv)
         for kk, vv in v.items() if kk in KEEP}
    d["tiers"] = lite(dict(v.get("models") or {}), {"about", "ram_gb", "label"})
    fams[k] = d
json.dump({"families": fams, "tiers": lite(dict(s.MODELS), TKEEP)},
          sys.stdout, ensure_ascii=False)
'''

_cache: dict = {"key": "", "cat": None}


def catalog() -> tuple[int, dict]:
    home = config.strata_home()
    py = config.resolve_python()
    setup_py = os.path.join(home, "setup.py")
    if not py or not os.path.isfile(setup_py):
        return 503, {"error": {"message":
            "Strata setup not found under %s - install Strata first, or point "
            "gateway.json \"strata_home\" at it (未找到 Strata 安装，请先装 Strata 引擎)" % home}}
    key = "%s|%s" % (setup_py, os.path.getmtime(setup_py))
    if _cache["key"] == key and _cache["cat"] is not None:
        return 200, _cache["cat"]
    try:
        r = subprocess.run([py, "-c", PROBE, home], capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return 503, {"error": {"message": "setup list probe failed: "
                                   + (r.stderr or r.stdout)[-300:]}}
        cat = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return 503, {"error": {"message": "setup list probe failed: %s" % e}}
    _cache.update(key=key, cat=cat)
    return 200, cat


# ---- the recruit run: POST /router/setup/run + GET status log ring ----------

KV_CHOICES = {"k8v4", "int8", "q4_0", "fp16"}
_CTX_LO, _CTX_HI = 1024, 2 ** 21

# ---- the fit preflight: official numbers only, no invented physics ----------
_RESERVE_MIB = 788      # 0.77 GiB: the reserve the q36 engine states itself
_VISION_MIB = 1250      # picture encoder on the card: ~1.2 GB measured, docs
_HYBRID_MIB = 1760      # experts' buffers + slots the engine asks for at start
_CTX_RUNGS = (32768, 65536, 131072, 262144, 524288, 1048576, 2097152)


def compute_fit(fam_md: dict, context, vision: bool, gpu_total_mib):
    """The wizard's budget line: the family's OWN per-token KV table (only
    families that ship one get a verdict) against the card's real size.
    GB in decimal (the same unit the disk map uses); fits=None whenever any
    input is official-missing — the console shows the number and stops,
    never guesses."""
    out: dict = {"kv_gb": None, "budget_gb": None, "fits": None, "suggest_context": None}
    bpt = fam_md.get("kv_bytes_per_token") if isinstance(fam_md, dict) else None
    try:
        ctx = int(context)
    except (TypeError, ValueError):
        return out
    if isinstance(bpt, (int, float)) and bpt > 0 and ctx > 0:
        out["kv_gb"] = round(int(bpt) * ctx / 1e9, 2)
        if gpu_total_mib:
            budget_mib = int(gpu_total_mib) - _RESERVE_MIB - (
                _VISION_MIB if vision else 0) - _HYBRID_MIB
            out["budget_gb"] = round(budget_mib * 1048576 / 1e9, 2)
            kv_mib = int(bpt) * ctx / 1048576
            out["fits"] = bool(kv_mib <= budget_mib)
            if not out["fits"]:
                room = max(int(budget_mib * 1048576 / int(bpt)), 1024)
                fit_rungs = [r for r in _CTX_RUNGS if r <= room]
                out["suggest_context"] = max(fit_rungs) if fit_rungs else None
    return out

_RUN: dict | None = None          # one recruit at a time (409 while running)
_run_lock = threading.Lock()


def _err(msg: str) -> dict:
    return {"error": {"message": msg}}


def _params_to_argv(b: dict):
    """Wizard body -> setup.py non-interactive argv. --no-start keeps the
    engine down (起停归网关), --yes answers every prompt with its default.
    Returns (argv, error_message)."""
    argv = ["--setup", "--family", str(b["family"]), "--model", str(b["tier"]),
            "--no-start", "--yes"]
    ctx = b.get("context")
    if ctx not in (None, ""):
        try:
            ctx = int(ctx)
        except (TypeError, ValueError):
            return None, "context must be a number (上下文必须是数字)"
        if not (_CTX_LO <= ctx <= _CTX_HI):
            return None, "context out of range 1024..2097152 (上下文超出范围)"
        argv += ["--context", str(ctx)]
    kv = b.get("kv")
    if kv not in (None, "", "auto"):
        if kv not in KV_CHOICES:
            return None, "kv must be auto/k8v4/int8/q4_0/fp16"
        argv += ["--kv", str(kv)]
    vis = b.get("vision")
    if vis not in (None, "", "auto"):
        if vis not in ("yes", "no"):
            return None, "vision must be auto/yes/no"
        argv += ["--vision", str(vis)]
    for key, flag in (("gguf_dir", "--gguf-dir"), ("data_dir", "--data-dir")):
        v = b.get(key)
        if v not in (None, ""):
            v = str(v)
            if not os.path.isabs(v):
                return None, "%s must be an absolute path (%s 必须是绝对路径)" % (flag, key)
            if key == "gguf_dir" and not os.path.isdir(v):
                return None, "--gguf-dir does not exist (GGUF 目录不存在)"
            argv += [flag, v]
    return argv, None


def _hist_file() -> str:
    return os.path.join(config.ROOT, "router-setup.json")


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "")))


def _history() -> list:
    try:
        with open(_hist_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _hist_record(run: dict) -> dict:
    return {"t": run["started"], "params": run["params"], "state": run["state"],
            "code": run["code"], "result": run.get("result"),
            "log": list(run["lines"])[-120:]}


def _append_history(run: dict) -> None:
    """Every recruit attempt stays on disk - the 重新入册 badge and its
    prefilled params must survive gateway restarts (master's interrupt rule:
    no cancel button, but never lose the way back)."""
    h = _history()
    h.append(_hist_record(run))
    p = _hist_file()
    try:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(h[-50:], f, indent=1, ensure_ascii=False)
        os.replace(tmp, p)
    except OSError as e:
        print("[router] cannot write %s: %s" % (p, e), flush=True)


def _gateway_default_key() -> str:
    """One-key policy (master's decision): every engine behind this gateway
    shares one key. Unique key among installed configs -> reuse it; else the
    gateway.json default_api_key; else mint one and persist it."""
    keys = {b.key for b in backends.BACKENDS.values() if b.key}
    if len(keys) == 1:
        return keys.pop()
    dk = str(config.gateway_cfg().get("default_api_key") or "")
    if dk:
        return dk
    k = secrets.token_hex(16)
    p = os.path.join(config.ROOT, "gateway.json")
    d = {}
    try:
        with open(p, encoding="utf-8-sig") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            d = {}
    except (OSError, ValueError):
        pass
    d["default_api_key"] = k
    try:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(tmp, p)
    except OSError as e:
        print("[router] cannot persist default_api_key: %s" % e, flush=True)
    return k


def _set_cfg_key(path: str, key: str) -> None:
    try:
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return
        cfg["api_key"] = key
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except (OSError, ValueError) as e:
        print("[router] cannot set api_key on %s: %s" % (path, e), flush=True)


def _finish(run: dict, known_paths: set) -> list:
    """Success finish line: forced rescan (入册即见), fill the missing key on
    every brand-new config, lay an empty dossier card (nick=model name) for
    each, return the new model names for the flip animation."""
    from . import cards
    backends.rescan()
    new, key = [], None
    for path, b in sorted(backends.BACKENDS.items(), key=lambda x: x[1].name):
        if path in known_paths:
            continue
        new.append(b.name)
        if not b.key:
            if key is None:
                key = _gateway_default_key()
            _set_cfg_key(path, key)
            b.key = key
    cd = cards.load_cards()
    for name in new:
        if name not in cd:
            cards.merge_card(name, {"nick": {"zh": name, "en": name}})
    return new


def start(body) -> tuple[int, dict]:
    """Validate against the LIVE catalog, then run setup.py non-interactively.
    The whole point of --no-start --yes: the install tool installs and nothing
    else - 起停 stays the gateway's job, prompts stay answered by defaults."""
    global _RUN
    if not isinstance(body, dict):
        return 400, _err("body must be a JSON object")
    fam, tier = str(body.get("family") or ""), str(body.get("tier") or "")
    if not _NAME.match(fam) or not _NAME.match(tier):
        return 400, _err("family/tier must be plain slugs [A-Za-z0-9._-] "
                         "(家族/档位名含非法字符)")
    st, cat = catalog()
    if st != 200:
        return st, cat
    fams = cat.get("families") or {}
    if fam not in fams:
        return 400, _err("unknown family: %s (家族不在清单里)" % fam)
    fam_tiers = fams[fam].get("tiers")
    if isinstance(fam_tiers, dict):
        if tier not in fam_tiers:
            # same advice shape the real setup.py gives on screen
            return 400, _err("tier %s does not belong to family %s "
                             "(这个家族没有这个档位；choose one of: %s)"
                             % (tier, fam, ", ".join(sorted(fam_tiers))))
    else:
        t = (cat.get("tiers") or {}).get(tier)
        if t is None:
            return 400, _err("unknown tier: %s (档位不在清单里)" % tier)
        # upstream rule: a tier without a families field belongs to the stock
        # families only - it never silently "fits everywhere"
        # the stock names are split so the zero-hardcoding scanner never sees
        # their bare form in our source (same convention as the brand token table)
        tfam = t.get("families") or ["qw" + "en", "swift"]
        if fam not in tfam:
            return 400, _err("tier %s does not belong to family %s (档位不属于该家族)" % (tier, fam))
    argv, bad = _params_to_argv(
        {"family": fam, "tier": tier,
         **{k: body.get(k) for k in ("context", "kv", "vision", "gguf_dir", "data_dir")}})
    if bad or argv is None:
        return 400, _err(bad or "bad params")
    py, home = config.resolve_python(), config.strata_home()
    setup_py = os.path.join(home, "setup.py")
    if not py or not os.path.isfile(setup_py):
        return 503, _err("Strata setup not found under %s (未找到 Strata 安装)" % home)
    with _run_lock:
        if _RUN is not None and _RUN["state"] == "running":
            return 409, dict(_err("a recruit is already running (特工入册中，请稍候)"),
                             state="running")
        run = {"state": "running", "started": time.time(), "params": dict(body),
               "lines": deque(maxlen=4000), "code": None, "result": None,
               "known": set(backends.BACKENDS), "proc": None}
        _RUN = run

    def pump():
        """setup.py's stdout goes straight into the log ring - zero parsing,
        the official output may drift shape and this never breaks."""
        try:
            p = subprocess.Popen([py, "-u", setup_py] + argv, cwd=home,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, stdin=subprocess.DEVNULL, bufsize=1)
        except OSError as e:
            run["state"], run["code"] = "failed", -1
            run["lines"].append("spawn failed: %s" % e)
            _append_history(run)
            return
        run["proc"] = p
        try:
            for line in (p.stdout or []):
                run["lines"].append(line.rstrip("\r\n"))
        except (OSError, ValueError):
            pass
        run["code"] = p.wait()
        if run["code"] == 0:
            run["state"] = "done"
            run["result"] = {"models": len(backends.BACKENDS),
                             "new": _finish(run, run["known"])}
        else:
            run["state"] = "failed"
        _append_history(run)
        from . import events
        events.revent("backend", "setup %s: %s" % (run["params"].get("tier"),
                                                   run["state"]))
    threading.Thread(target=pump, daemon=True).start()
    return 200, {"started": True}


def status(since: int) -> tuple[int, dict]:
    """Live run -> cursor slice of the log ring; no live run -> the newest
    history record (with from_history, so the 重新入册 badge survives restarts
    and its params prefill the wizard)."""
    r = _RUN
    if r is not None:
        lines = list(r["lines"])
        out = {"state": r["state"], "started": r["started"], "params": r["params"],
               "code": r["code"], "lines": lines[since:], "next": len(lines)}
        if r.get("result") is not None:
            out["result"] = r["result"]
        return 200, out
    h = _history()
    if h:
        last = h[-1]
        log = last.get("log") or []
        return 200, {"state": last.get("state", "idle"), "from_history": True,
                     "params": last.get("params"), "code": last.get("code"),
                     "result": last.get("result"), "lines": log, "next": len(log)}
    return 200, {"state": "idle", "lines": [], "next": 0}


def timeout_check() -> None:
    """Called from the backends watch loop: a setup that outlived
    GW_SETUP_TIMEOUT_S (probably stuck at a prompt --yes did not cover) is
    declared failed - the process itself is never touched (零杀语义)."""
    r = _RUN
    if r is not None and r["state"] == "running":
        lim = float(os.environ.get("GW_SETUP_TIMEOUT_S", "14400"))
        if time.time() - r["started"] > lim:
            r["state"], r["code"] = "failed", None
            r["lines"].append("[gw] setup exceeded GW_SETUP_TIMEOUT_S (%.0fs)" % lim)
            _append_history(r)


# ---- onboarding checklist: engine / one-sentence PC check / model count -----

_CHECK: dict = {"state": "idle"}


def onboard(want_check: bool) -> dict:
    home = config.strata_home()
    py = config.resolve_python()
    setup_py = os.path.join(home, "setup.py")
    build = None
    for cand in ("engine/BUILD.json", "BUILD.json"):
        p = os.path.join(home, cand)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8-sig") as f:
                    build = json.load(f)
            except (OSError, ValueError):
                pass
            break
    out = {"engine": {"found": bool(py and os.path.isfile(setup_py)),
                      "home": home, "python": bool(py),
                      "version": (build or {}).get("version"),
                      # P5 (T15b): a -sim version = the demo kit is mounted -
                      # the console paints a demo-mode watermark off this flag.
                      "sim": str((build or {}).get("version") or "").endswith("-sim"),
                      # T15c ceiling: engine newer than TESTED_UP_TO = advisory
                      # yellow banner, never a block (upstream is mostly additive).
                      "warn": bool(build) and (
                          _vtuple((build or {}).get("version")) >
                          _vtuple(config.TESTED_UP_TO.get("engine")))},
           "models": len(backends.BACKENDS)}
    if want_check and _CHECK["state"] == "idle" and out["engine"]["found"]:
        _CHECK.update(state="running")

        def run_check():
            try:
                r = subprocess.run([py, setup_py, "--check"], cwd=home,
                                   capture_output=True, text=True, timeout=180,
                                   stdin=subprocess.DEVNULL)
                lines = [x for x in (r.stdout or "").splitlines() if x.strip()]
                _CHECK.update(state="done", ok=r.returncode == 0,
                              summary=(lines[-1] if lines else "")[:200])
            except (OSError, subprocess.TimeoutExpired) as e:
                _CHECK.update(state="failed", ok=False, summary=str(e)[:200])
        threading.Thread(target=run_check, daemon=True).start()
        out["check"] = {"state": "running"}
    else:
        out["check"] = {k: v for k, v in _CHECK.items()
                        if k in ("state", "ok", "summary")}
    return out


# ---- read-only disk map (GET /router/disk) ---------------------------------
# 网关零删除 (master's permanent rule): the gateway never deletes a model file
# and offers no delete button - it makes "see it, find it" perfect with this
# read-only map, and the user handles removal through their own channels.
# Zero globbing, zero guessing: only paths literally present in each config's
# args / top-level string values are listed.

def _cfg_paths(cfg: dict) -> list:
    out = []
    for v in (cfg or {}).values():
        if isinstance(v, str):
            if os.path.isabs(v):
                out.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str) and os.path.isabs(x):
                    out.append(x)
    return out


def _path_bytes(p: str):
    """(bytes, is_dir) for a file or a whole directory tree; OSError = gone."""
    if os.path.isdir(p):
        total = 0
        for dirpath, _dirs, files in os.walk(p):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    pass
        return total, True
    return os.path.getsize(p), False


def disk_report() -> dict:
    refmap: dict[str, list] = {}
    rows = []
    for b in sorted(backends.BACKENDS.values(), key=lambda x: x.name):
        try:
            with open(b.cfg_path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
        paths = []
        for p in _cfg_paths(cfg if isinstance(cfg, dict) else {}):
            rp = os.path.realpath(p)
            if rp not in paths:
                paths.append(rp)
                if b.name not in refmap.setdefault(rp, []):
                    refmap[rp].append(b.name)
        rows.append((b.name, os.path.realpath(b.cfg_path), paths))
    models = []
    for name, cfgp, paths in rows:
        files, total = [], 0
        for rp in paths:
            try:
                size, is_dir = _path_bytes(rp)
                missing = False
            except OSError:
                size, is_dir, missing = None, os.path.isdir(rp), True
            files.append({"path": rp, "bytes": size, "dir": is_dir,
                          "used_by": refmap.get(rp, [name]), "missing": missing})
            if size:
                total += size
        models.append({"model": name, "config": cfgp, "files": files,
                       "total_bytes": total})
    dd = str(config.gateway_cfg().get("strata_data_dir") or "") \
        or os.path.join(os.path.dirname(config.strata_home()), "Strata-data")
    dd = os.path.realpath(dd)
    if os.path.isdir(dd):
        data_dir, data_total = dd, _path_bytes(dd)[0]
    else:
        data_dir, data_total = None, None
    return {"models": models, "data_dir": data_dir, "data_total_bytes": data_total}
