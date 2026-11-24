#!/usr/bin/env python3
"""engine_source - the gateway's first-class handle on which engine binary the
backends run: "config" (the scanned exe paths, the default, byte for byte what
setup.py wrote) or "component" (the upstream "component:strata-engine"
reference; server.py resolves it against the component store - newest package,
a rollback pin honored, signed and SHA-256 verified at start - so the gateway
follows the desktop app's strata update / components rollback with zero gw
changes). This suite pins the resolution ladder, the managed spawn config,
the scan skip, and the stamp dispatch. Pure stdlib, no gateway process."""
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))
from stub_common import ok                      # noqa: E402
from gw import config, backends                 # noqa: E402

TMP = tempfile.mkdtemp(prefix="engine-source-")
_ENV_SAVED = {}


def setenv(name, value):
    if name not in _ENV_SAVED:
        _ENV_SAVED[name] = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def plant_package(store, version, *, with_build=True, with_reader=True):
    """A minimal component-store package: manifest (authoritative version) +
    BUILD.json + a picture reader, the three faces the gateway reads."""
    folder = os.path.join(store, "engine", version + "-windows-x86_64-cuda-cuda13")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, config.COMPONENT_MANIFEST), "w", encoding="utf-8") as f:
        json.dump({"schema_version": 2, "id": "strata-engine", "version": version,
                   "platform": "windows-x86_64", "backend": "cuda"}, f)
    if with_build:
        with open(os.path.join(folder, "BUILD.json"), "w", encoding="utf-8") as f:
            json.dump({"version": version, "cuda": "13.0"}, f)
    if with_reader:
        with open(os.path.join(folder, "strata-vision.exe"), "wb") as f:
            f.write(b"reader")
    return folder


def fake_source_config(name="strata-m1.json", **over):
    cfg = {"model_name": "m1", "exe": "D:/Strata/terminal/engine/strata.exe",
           "args": ["--kv", "k8v4"], "cwd": "D:/Strata",
           "vision": {"exe": "D:/Strata/terminal/engine/strata-vision.exe",
                      "mmproj": "D:/Strata-data/mmproj.gguf", "gpu": True}}
    cfg.update(over)
    src = os.path.join(TMP, "cfg")
    os.makedirs(src, exist_ok=True)
    path = os.path.join(src, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return path


try:
    # ---- resolution ladder -------------------------------------------------------------
    setenv("STRATA_ENGINE_SOURCE", "component")
    ok(config.engine_source() == "component", "ES1 env STRATA_ENGINE_SOURCE=component selects the component source")
    # ES2 must not read the real gateway.json (the activation key lands there
    # later): point config.ROOT at a temp tree with an empty one for this check.
    saved_root = config.ROOT
    root_tmp = os.path.join(TMP, "root")
    os.makedirs(root_tmp, exist_ok=True)
    with open(os.path.join(root_tmp, "gateway.json"), "w", encoding="utf-8") as f:
        json.dump({}, f)
    config.ROOT = root_tmp
    try:
        setenv("STRATA_ENGINE_SOURCE", "")
        ok(config.engine_source() == "config", "ES2 an empty env with no key falls through to config")
    finally:
        config.ROOT = saved_root
        setenv("STRATA_ENGINE_SOURCE", "component")

    setenv("STRATA_ENGINE_SOURCE", "component")
    store = os.path.join(TMP, "store-none")
    setenv("STRATA_COMPONENTS_DIR", store)
    ok(config.component_engine_dir() is None, "ES3 an empty store answers None, never a guess")

    store = os.path.join(TMP, "store")
    p65 = plant_package(store, "0.1.65")
    plant_package(store, "0.1.63")
    setenv("STRATA_COMPONENTS_DIR", store)
    ok(config.component_engine_dir() == p65, "ES4 no pin: the newest installed package wins (0.1.65 over 0.1.63)")

    upd = os.path.join(store, ".updates")
    os.makedirs(upd, exist_ok=True)
    with open(os.path.join(upd, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"engine": {"pinned": "0.1.63-windows-x86_64-cuda-cuda13"}}, f)
    ok(config.component_engine_dir().endswith("0.1.63-windows-x86_64-cuda-cuda13"),
       "ES5 a rollback pin beats the newest package (components rollback is followed)")

    with open(os.path.join(upd, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"engine": {"pinned": "../elsewhere"}}, f)
    ok(config.component_engine_dir() == p65, "ES6 a pin that leaves the store is ignored, newest wins again")

    # ---- stamp dispatch ----------------------------------------------------------------
    stamp = config.engine_stamp()
    ok(stamp and stamp.get("version") == "0.1.65", "ES7 component source: the stamp is the store package's BUILD.json")
    shutil.rmtree(os.path.join(p65), ignore_errors=True)
    plant_package(store, "0.1.65", with_build=False)
    stamp = config.engine_stamp()
    ok(stamp and stamp.get("version") == "0.1.65", "ES8 a package without BUILD.json still reports its manifest version")

    setenv("STRATA_ENGINE_SOURCE", "config")
    home = os.path.join(TMP, "home")
    os.makedirs(os.path.join(home, "terminal", "engine"), exist_ok=True)
    with open(os.path.join(home, "terminal", "engine", "BUILD.json"), "w", encoding="utf-8") as f:
        json.dump({"version": "0.1.63"}, f)
    setenv("STRATA_HOME", home)
    stamp = config.engine_stamp()
    ok(stamp and stamp.get("version") == "0.1.63", "ES9 config source: the stamp is the install's, unchanged behavior")

    # ---- managed spawn config ------------------------------------------------------------
    setenv("STRATA_ENGINE_SOURCE", "component")
    setenv("STRATA_HOME", home)                    # from ES9; harmless here
    src = fake_source_config()
    out_dir = os.path.join(TMP, "runtime")
    got = backends.managed_config(src, out_dir=out_dir)
    with open(got, encoding="utf-8-sig") as f:
        m = json.load(f)
    ok(os.path.dirname(got) == out_dir and os.path.basename(got) == "strata-m1.json",
       "MC1 the managed copy keeps the config's basename under the destination dir")
    ok(m.get("exe") == "component:strata-engine", "MC2 exe is the upstream component reference, not a hardcoded path")
    ok(m.get("args") == ["--kv", "k8v4"] and m.get("cwd") == "D:/Strata" and m.get("model_name") == "m1",
       "MC3 everything but exe is inherited untouched")
    with open(src, encoding="utf-8-sig") as f:
        original = json.load(f)
    # The component store ships WINDOWS packages, and a scanned config's exe paths
    # are drive-absolute ("D:/..."), which os.path.isabs() rejects on a POSIX host -
    # so the picture-reader rewrite only ever fires on the box that runs the engine.
    # Both faces are pinned: a platform skip must never rot into a silent pass.
    win_box = os.name == "nt"
    ok(m["vision"]["exe"] == (os.path.join(p65, "strata-vision.exe") if win_box
                               else original["vision"]["exe"]),
       "MC4 the picture reader follows the resolved package folder"
       + ("" if win_box else " (posix face: the rewrite is Windows-only)"))
    ok(original["exe"].endswith("terminal/engine/strata.exe") and
       original["vision"]["exe"].endswith("terminal/engine/strata-vision.exe"),
       "MC5 the scanned JSON stays read-only")

    src_nov = fake_source_config(name="strata-m2.json")
    with open(src_nov, encoding="utf-8-sig") as f:
        c = json.load(f)
    c.pop("vision")
    with open(src_nov, "w", encoding="utf-8") as f:
        json.dump(c, f)
    m2 = json.loads(open(backends.managed_config(src_nov, out_dir=out_dir), encoding="utf-8-sig").read())
    ok("vision" not in m2, "MC6 a config without vision spawns fine")

    p66 = plant_package(store, "0.1.66")
    m3 = json.loads(open(backends.managed_config(src, out_dir=out_dir), encoding="utf-8-sig").read())
    ok(m3["vision"]["exe"] == (os.path.join(p66, "strata-vision.exe") if win_box
                               else original["vision"]["exe"]),
       "MC7 a store update moves the reader with zero gw changes"
       + ("" if win_box else " (posix face: it stays put, see MC4)"))

    # ---- both edit surfaces stay honest ---------------------------------------------------
    import time as _time
    with open(src, encoding="utf-8-sig") as f:
        c = json.load(f)
    c["args"] = ["--changed"]
    with open(src, "w", encoding="utf-8") as f:
        json.dump(c, f)
    got2 = backends.managed_config(src, out_dir=out_dir)
    with open(got2, encoding="utf-8-sig") as f:
        m4 = json.load(f)
    ok(m4["args"] == ["--changed"], "MC8 a hand-edited scanned config re-inherits on the next spawn")
    with open(src, encoding="utf-8-sig") as f:
        c = json.load(f)
    c["args"] = ["--newer"]
    with open(src, "w", encoding="utf-8") as f:
        json.dump(c, f)
    old = _time.time() - 100
    os.utime(src, (old, old))                      # the source backdated: the copy was edited later
    got3 = backends.managed_config(src, out_dir=out_dir)
    with open(got3, encoding="utf-8-sig") as f:
        m5 = json.load(f)
    ok(m5["args"] == ["--changed"] and m5["exe"] == "component:strata-engine",
       "MC9 settings saved through the engine's own page survive a respawn")

    src_shared = os.path.splitext(src)[0] + ".shared-settings.json"
    with open(src_shared, "w", encoding="utf-8") as f:
        json.dump({"temperature": 0.5}, f)
    backends.managed_config(src, out_dir=out_dir)
    dst_shared = os.path.splitext(got3)[0] + ".shared-settings.json"
    with open(dst_shared, encoding="utf-8-sig") as f:
        shared = json.load(f)
    ok(shared.get("temperature") == 0.5,
       "MC10 the shared chat settings are mirrored into the copy's namespace")

    # the managed copy must never become a backend, even if a future scan dir
    # change reaches the runtime folder: the skip filter is name-based.
    setenv("STRATA_COMPONENTS_DIR", os.path.join(TMP, "store-empty"))
    real = os.path.join(TMP, "scandir")
    os.makedirs(real, exist_ok=True)
    shutil.copyfile(src_nov, os.path.join(real, "strata-real.json"))
    shutil.copyfile(got, os.path.join(real, "strata-m1.runtime.json"))
    setenv("STRATA_HOME", real)
    ports = os.path.join(TMP, "ports.json")
    saved_ports, saved_root_ports = config.PORTS_FILE, None
    try:
        saved_root_ports = open(config.PORTS_FILE, "rb").read() if os.path.isfile(config.PORTS_FILE) else None
    except OSError:
        saved_root_ports = None
    config.PORTS_FILE = ports
    try:
        found = backends.scan_configs()
        ok(len(found) == 1 and os.path.basename(list(found)[0]) == "strata-real.json",
           "SC1 scan_configs picks up real configs and never the .runtime copies")
    finally:
        config.PORTS_FILE = saved_ports
        if saved_root_ports is not None:
            open(config.PORTS_FILE, "wb").write(saved_root_ports)
        elif os.path.isfile(config.PORTS_FILE):
            os.remove(config.PORTS_FILE)
        # scan_configs may have persisted the fake mapping into the temp ports file only

    # ---- fallback honesty ----------------------------------------------------------------
    setenv("STRATA_COMPONENTS_DIR", store)
    setenv("STRATA_HOME", home)
finally:
    for name, old in _ENV_SAVED.items():
        setenv(name, old)
    shutil.rmtree(TMP, ignore_errors=True)

print("ALL PASS")
