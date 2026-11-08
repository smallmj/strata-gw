# protocol snapshot: Strata v0.2.12 / engine 0.1.58 (pinned 2026-11-08)
"""sim-strata setup.py - the FAKE Strata install tool for the demo kit.

Everything here is pretend: no downloads, no GPU, no inference. The kit lets
strata-gw's recruit wizard run end-to-end on a machine with no Strata at all.
Mirrors the real install tool in the one way the gateway relies on: constants
live at import time (the gateway probe imports this file), the CLI only runs
under __main__.
"""
import argparse
import json
import os
import sys
import time

FAMILIES = {
    "simcore": {"title": "SimCore One", "by": "strata-gw sim",
                "about": "demo family - no real inference",
                "name": "simcore-one", "tag": "", "vision": True},
    "simforge": {"title": "SimForge", "by": "strata-gw sim",
                 "about": "demo code-type family - no real inference",
                 "name": "simforge-two", "tag": "", "vision": False},
    "simvista": {"title": "SimVista", "by": "strata-gw sim",
                 "about": "demo vision family - shares the ngram pack with SimCore",
                 "name": "simvista-three", "tag": "", "vision": True},
}
PREVIEW_FAMILIES = {
    "simbeta": {"title": "SimBeta", "by": "strata-gw sim",
                "about": "demo preview family - no real inference",
                "name": "simbeta-preview", "tag": "preview", "vision": False},
}
MULTI_FILE_FAMILIES = {
    "simmulti": {"title": "SimMulti", "by": "strata-gw sim",
                 "about": "demo multi-file family with its own tiers",
                 "name": "simmulti-many", "tag": "", "vision": False,
                 "models": {
                     "V1": {"label": "V1 small demo", "about": "demo v1", "ram_gb": 8},
                     "V2": {"label": "V2 big demo", "about": "demo v2", "ram_gb": 16},
                 }},
}
MODELS = {
    "Q4SIM": {"about": "demo 4-bit", "download_gb": 4.0, "ram_gb": 8, "arena_gb": 2,
              "families": ["simcore", "simforge", "simvista", "simbeta"]},
    "Q8SIM": {"about": "demo 8-bit", "download_gb": 8.0, "ram_gb": 16, "arena_gb": 4,
              "families": ["simcore", "simvista", "simbeta"]},
    "MAXSIM": {"about": "demo big", "download_gb": 16.0, "ram_gb": 32, "arena_gb": 8,
               "families": ["simcore", "simforge"]},
    "FAILSIM": {"about": "demo failure tier: dies mid-run on purpose - "
                          "use it to watch the retry badge",
                "download_gb": 4.0, "ram_gb": 8, "arena_gb": 2,
                "families": ["simcore", "simforge", "simvista", "simbeta"]},
}


def _data_dir(a):
    if a.data_dir:
        return os.path.abspath(a.data_dir)
    if os.environ.get("SIM_STRATA_DATA"):
        return os.path.abspath(os.environ["SIM_STRATA_DATA"])
    home = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(home), "Strata-data")


def _check():
    print("sim check: engine venv present (fake)", flush=True)
    print("sim check: disk free plenty (fake)", flush=True)
    print("SIM PC check: sim environment, everything fake, plenty of disk", flush=True)
    return 0


def _pack(path, total_bytes, nshards):
    os.makedirs(path, exist_ok=True)
    per = max(total_bytes // nshards, 1)
    for i in range(nshards):
        with open(os.path.join(path, "shard-%03d.gguf-part" % i), "wb") as f:
            f.truncate(per)


def _setup(a):
    fams = dict(FAMILIES)
    fams.update(PREVIEW_FAMILIES)
    fams.update(MULTI_FILE_FAMILIES)
    if os.environ.get("SIM_ARGS_DUMP") == "1":   # tests assert param pass-through
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "args_dump.json"), "w") as f:
            json.dump(sys.argv[1:], f)
    if a.family not in fams:
        print("sim: unknown family %r" % a.family, flush=True)
        return 2
    if a.model in MODELS:
        spec = MODELS[a.model]
    else:
        m = (MULTI_FILE_FAMILIES.get(a.family) or {}).get("models") or {}
        if a.model in m:
            spec = {"download_gb": 2.0, "ram_gb": m[a.model].get("ram_gb", 8)}
        else:
            print("sim: unknown model %r" % a.model, flush=True)
            return 2
    gb_per_mb = float(os.environ.get("SIM_STRATA_PACK_MB_PER_GB", "100"))
    steps = 5                                   # 3 pack shards + index + meta
    for i in range(steps):
        if a.model == "FAILSIM" and i >= 3:     # ~60% in: die on purpose
            print("sim: link flapped, giving up", flush=True)
            return 3
        print("sim: fetching %s %d/%d (%.1f GB)" % (a.model, i + 1, steps,
              float(spec["download_gb"]) / steps), flush=True)
        time.sleep(float(os.environ.get("SIM_STRATA_TOTAL_S", "45")) / steps)
    data = _data_dir(a)
    here = os.path.dirname(os.path.abspath(__file__))
    tier = a.model.lower()
    packs = os.path.join(data, "packs")
    pack = os.path.join(packs, tier)
    total = int(float(spec["download_gb"]) * gb_per_mb * 1024 * 1024)
    print("sim: packing...", flush=True)
    _pack(pack, total, 3)
    args = ["--pack", pack, "--max-context", str(a.context or 131072)]
    if a.family in ("simcore", "simvista"):     # shared pack: the 共享 teaching case
        shared = os.path.join(packs, "shared-ngram")
        _pack(shared, int(1.0 * gb_per_mb * 1024 * 1024), 1)
        args += ["--pack", shared]
    fname = fams[a.family]["name"]
    cfg = {"model_name": fname + "-" + tier, "args": args}
    with open(os.path.join(here, "strata-%s-%s.json" % (fname, tier)), "w",
              encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    print("sim: config written", flush=True)
    return 0


def _main():
    ap = argparse.ArgumentParser(prog="sim-strata setup (demo)")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--family")
    ap.add_argument("--model")
    ap.add_argument("--context", type=int)
    ap.add_argument("--kv")
    ap.add_argument("--vision")
    ap.add_argument("--gguf-dir", dest="gguf_dir")
    ap.add_argument("--data-dir", dest="data_dir")
    ap.add_argument("--no-start", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--check", action="store_true")
    a, extra = ap.parse_known_args()
    if extra:
        print("sim setup: ignoring unknown args: %s" % " ".join(extra), flush=True)
    if a.check:
        return _check()
    if not a.setup or not a.family or not a.model:
        ap.print_usage()
        return 2
    return _setup(a)


if __name__ == "__main__":
    sys.exit(_main())
