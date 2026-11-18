"""sweep.py - the strata process sweep the legacy gateway had and this one lost.

The old internal launcher ran a PowerShell that killed every strata-router,
every serve/server.py wrapper and every strata.exe / strata-vision.exe before
starting the gateway. Without that, a restart silently ADOPTS the stragglers:
two routers bind one port (traffic splits, probes go flaky), adopted engines
keep their logs out of the console window (the master sees no stream), and
orphaned engines go on holding VRAM so the next model load crawls.

The gateway now owns the sweep itself, so EVERY boot path (double-clicked .cmd,
.bat, scheduled task) gets the same clean-boot semantics:

  boot  - reap other routers of THIS folder, serve wrappers of OUR engine home
          and every strata engine process, then spawn fresh children whose logs
          stream into the same console.
  load  - reap orphaned leftovers (an engine whose wrapper died, a wrapper whose
          gateway died) right before weights move in.

Folder safety: an ABSOLUTE-path router is judged by its folder, separator-aware,
so a gateway under a twin folder (a side-by-side test deployment) is never
touched; the relative form ("python strata-router.py") can only come from a
launcher that cd'd into its own folder, so it is treated as ours. Unrelated
processes (image generators, chat clients, everything else) are never in the
family. This process and its python ancestors (the venv stub parent!) are
never touched.

Knob: STRATA_SWEEP=0 (env) or gateway.json "sweep": false turns it off - a
deployment that must never kill the engines around it sets it. Non-Windows
boots (CI) are inert by definition.
"""
from __future__ import annotations

import os
import re
import subprocess
import time

from . import config
from . import events

# the gateway's own entry-point name; a python running this is a router
ROUTER_TOKEN = "strata-router"
# engine executables under the engine home (strata.exe, strata-vision.exe, ...)
ENGINE = re.compile(r"^strata[a-z0-9_-]*\.exe$", re.I)
PYNAME = re.compile(r"^(python|pythonw)", re.I)


def enabled() -> bool:
    """Sweep on unless someone turns it off: STRATA_SWEEP env wins, then the
    gateway.json "sweep" key, default on."""
    v = (config.env("STRATA_SWEEP") or "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    if config.gateway_cfg().get("sweep") is False:
        return False
    return True


def norm(p: str) -> str:
    return p.replace("/", "\\").lower()


def is_under(path: str, base: str) -> bool:
    """Separator-aware containment: a sibling folder whose name merely STARTS
    with ours as a string ("<base>-test") is NOT under us - prefix != folder."""
    b = norm(base).rstrip("\\")
    p = norm(path)
    return p == b or p.startswith(b + "\\")


def parse_rows(text: str) -> list[dict]:
    """One line per process: 'pid|name|ppid|cmdline' (pipes inside the cmdline
    stay in the last field - the split is bounded). Missing cmdline = empty."""
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) < 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[2])
        except ValueError:
            continue
        out.append({"pid": pid, "ppid": ppid, "name": parts[1],
                    "cmdline": parts[3] if len(parts) > 3 else ""})
    return out


def ancestors(rows: list[dict], pid: int) -> set[int]:
    """pid plus the python/pythonw chain above it - the venv launcher stub
    shares our exact command line, so it must share our protection."""
    by = {r["pid"]: r for r in rows}
    out = {pid}
    cur = by.get(pid)
    while cur is not None and PYNAME.match(cur["name"] or ""):
        out.add(cur["pid"])
        cur = by.get(cur["ppid"])
    return out


def _router_token(cmd: str) -> str | None:
    """The whitespace-delimited field naming the entry script ('"X\\strata-router.py"'
    or the bare relative form), quotes stripped; None when absent."""
    for f in cmd.split():
        g = f.strip('"').strip("'")
        if g.lower().endswith(ROUTER_TOKEN + ".py"):
            return g
    return None


def _is_engine_family_row(r: dict, server_py: str | None = None) -> bool:
    name = (r["name"] or "").lower()
    cmd = (r["cmdline"] or "").lower()
    if ENGINE.match(name):
        return True
    if PYNAME.match(name):
        if ROUTER_TOKEN in cmd:
            return True
        sp = norm(server_py) if server_py else ""
        return bool(sp and sp in norm(cmd)) or "server.py" in cmd
    return False


def plan_boot(rows: list[dict], me: set[int], root: str, server_py: str) -> list[tuple[int, str, str]]:
    """Everything strata's own family that isn't this process: routers of our
    folder (and of the relative launcher form), serve wrappers of our engine
    home, and every strata engine process."""
    plan: list[tuple[int, str, str]] = []
    for r in rows:
        pid, name, cmd = r["pid"], r["name"] or "", r["cmdline"] or ""
        if pid in me:
            continue
        low = cmd.lower()
        if ENGINE.match(name.lower()):
            plan.append((pid, name, "engine"))
            continue
        if not PYNAME.match(name):
            continue
        if ROUTER_TOKEN in low:
            tok = _router_token(cmd)
            if tok and (":" in tok or tok.startswith("\\\\")):
                if is_under(tok, root):
                    plan.append((pid, name, "router"))
            else:
                plan.append((pid, name, "router"))
            continue
        if norm(server_py) in norm(cmd):
            plan.append((pid, name, "wrapper"))
    return plan


def plan_orphans(rows: list[dict], me: set[int],
                 server_py: str | None = None) -> list[tuple[int, str, str]]:
    """Only family members whose PARENT IS GONE: an engine whose serve wrapper
    died, a wrapper whose gateway died. A family member under a live parent is
    in service - even when another gateway runs it side by side - and is left
    alone."""
    live = {r["pid"] for r in rows}
    sp = server_py if server_py is not None else config.SERVER_PY
    plan = []
    for r in rows:
        if r["pid"] in me:
            continue
        if _is_engine_family_row(r, sp) and r["ppid"] not in live:
            plan.append((r["pid"], r["name"] or "?", "orphan"))
    return plan


_PS_ROW_SCRIPT = (
    'Get-CimInstance Win32_Process | ForEach-Object { '
    '"{0}|{1}|{2}|{3}" -f $_.ProcessId, $_.Name, $_.ParentProcessId, '
    '(($_.CommandLine -replace "[|`r`n]", " ")) }'
)


def _enumerate() -> list[dict]:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", _PS_ROW_SCRIPT],
                           capture_output=True, timeout=40)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[router] sweep: process enumeration failed ({e}); "
              "no sweep performed", flush=True)
        return []
    rows = parse_rows((r.stdout or b"").decode("utf-8", "replace"))
    if not rows:
        print("[router] sweep: enumeration returned no processes (exit "
              "{0}): {1}".format(r.returncode,
                                 (r.stderr or b"").decode("utf-8", "replace")[:200]),
              flush=True)
    return rows


def _kill(plan: list[tuple[int, str, str]]) -> None:
    if not plan:
        return
    # taskkill, not Stop-Process: it tree-kills (venv stub + interpreter +
    # children in one call) and it auto-enables SeDebugPrivilege, so a process
    # owned by SYSTEM or another account gets a REAL chance to die. The old
    # Stop-Process -ErrorAction SilentlyContinue path failed with a swallowed
    # access-denied and the "survived the kill" line was the only trace.
    for pid, _name, _why in plan:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    # prove it: re-enumerate until the named pids are gone (or patience ends)
    wanted = {pid for pid, _n, _w in plan}
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if not (wanted & {r["pid"] for r in _enumerate()}):
            break
        time.sleep(0.5)
    still = wanted & {r["pid"] for r in _enumerate()}
    if still:
        names = {pid: nm for pid, nm, _w in plan}
        own = owners(sorted(still))
        for pid in sorted(still):
            o = own.get(pid, "?")
            print(f"[router] sweep: pid {pid} ({names.get(pid, '?')}, owner {o}) "
                  "survived the kill - access denied (it runs under a different "
                  "account than this gateway) or it is wedged in a driver call. "
                  f"Fix from an ELEVATED session: taskkill /F /T /PID {pid}",
                  flush=True)
        events.revent("boot", f"sweep could not stop {len(still)} process(es) "
                              "(different account / access denied)")


def parse_owners(text: str) -> dict[int, str]:
    """'42400|NT AUTHORITY\\SYSTEM' lines -> {pid: 'DOMAIN\\USER'}."""
    out: dict[int, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        pid, own = line.split("|", 1)
        try:
            out[int(pid)] = own.strip()
        except ValueError:
            continue
    return out


def owners(pids: list[int]) -> dict[int, str]:
    if not pids or os.name != "nt":
        return {}
    flt = " OR ".join(f"ProcessId={p}" for p in pids)
    script = ('Get-CimInstance Win32_Process -Filter "' + flt + '" '
              '| ForEach-Object { $o = $_ | Invoke-CimMethod -Name GetOwner '
              '-ErrorAction SilentlyContinue; '
              '"{0}|{1}\\{2}" -f $_.ProcessId, $o.Domain, $o.User }')
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", script], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_owners((r.stdout or b"").decode("utf-8", "replace"))


def parse_listen_rows(text: str) -> list[int]:
    """Get-NetTCPConnection enumeration: one pid per line."""
    out: list[int] = []
    for line in text.splitlines():
        s = line.strip()
        if s.isdigit():
            out.append(int(s))
    return out


def listeners(port: int) -> list[int]:
    if os.name != "nt":
        return []
    script = (f'Get-NetTCPConnection -LocalPort {port} -State Listen '
              '-ErrorAction SilentlyContinue | '
              'ForEach-Object { "{0}" -f $_.OwningProcess }')
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", script], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_listen_rows((r.stdout or b"").decode("utf-8", "replace"))


def warn_port_squatters(port: int) -> list[int]:
    """After this router binds: anything ELSE still listening on our port means
    the boot sweep could not stop it (different account) - two routers sharing
    one port split traffic and hide engine logs in someone else's console. This
    must never be silent: name pid + owner on the console and in the events."""
    if os.name != "nt":
        return []
    others = [p for p in listeners(port) if p != os.getpid()]
    if not others:
        return []
    own = owners(others)
    for p in others:
        print(f"[router] WARNING: pid {p} ({own.get(p, '?')}) is ALSO listening "
              f"on :{port} - the boot sweep could not stop it, so this gateway "
              "SHARES the port: requests split between the two routers and the "
              "engines' logs stream into the OTHER window. Stop it from an "
              f"ELEVATED session: taskkill /F /T /PID {p}", flush=True)
    events.revent("boot", f"port :{port} is shared with surviving process(es) "
                          f"{others} - stop them from an elevated session")
    return others


def _report(plan: list[tuple[int, str, str]], verb: str) -> None:
    lines = ", ".join(f"{why} pid {pid} ({name})" for pid, name, why in plan)
    print(f"[router] {verb} {len(plan)} old strata process(es): {lines}", flush=True)


def sweep_boot() -> list[tuple[int, str, str]]:
    """Called by main.py BEFORE scanning configs: the box comes up clean, so
    every engine the gateway then spawns is its own child - live logs in this
    console, the VRAM card genuinely free, and no second router on the port."""
    if os.name != "nt" or not enabled():
        return []
    rows = _enumerate()
    if not rows:
        return []
    plan = plan_boot(rows, ancestors(rows, os.getpid()), config.ROOT, config.SERVER_PY)
    if not plan:
        print("[router] boot sweep: no old strata processes found (clean boot)", flush=True)
        return []
    _report(plan, "boot sweep stopped")
    _kill(plan)
    events.revent("boot", f"startup sweep stopped {len(plan)} old strata process(es)")
    return plan


def sweep_orphans() -> list[tuple[int, str, str]]:
    """Called on every load, before the weights move in: engines left behind by
    a crashed generation of this gateway hold VRAM quietly; this reaps exactly
    those - and only those."""
    if os.name != "nt" or not enabled():
        return []
    rows = _enumerate()
    if not rows:
        return []
    plan = plan_orphans(rows, {os.getpid()})
    if not plan:
        return []
    _report(plan, "load sweep reaped")
    _kill(plan)
    events.revent("gpu", f"load sweep reaped {len(plan)} orphaned strata process(es) holding VRAM")
    return plan
