# protocol snapshot: Strata v0.2.12 / engine 0.1.58 (pinned 2026-11-08)
r"""sim-strata make_env.py - lays out the Windows TEST environment.

Usage:  make-env.cmd [gw_dir] [shome_dir]
        defaults:  D:\strata-gw-test   D:\Strata-test

Writes (all ASCII - cmd files must survive the OEM code page):
  <gw_dir>\gateway.json      strata_home -> shome, gpu_free -> holder 18288
  <gw_dir>\start-test.cmd    sweep-by-own-dir -> holder -> router (foreground)
  <gw_dir>\stop-test.cmd     same sweep, whole tree down
  <gw_dir>\update-test.cmd   git fetch <bundle> dev + reset --hard (never pull)
Every port here lives in the demo band (router 18175, engines 18201+,
holder 18288) and never touches production 18075/1808x or test 1809x.
"""
import json
import os
import shutil
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
ROUTER_PORT = "18175"
FIRST_BACKEND = "18201"
HOLDER_PORT = "18288"

START = r'''@echo off
setlocal
cd /d "%~dp0"
set "GD=%CD%"
set "SH=%SH%"
for /f "delims=" %%h in ('git -C "%GD%" rev-parse --short HEAD 2^>nul') do set "TIPH=%%h"
echo ==========================================================
echo  TEST BUILD: %TIPH% (sim environment)
echo  router :%RP%  engines :%FB%+  image holder :%HP%
echo  gw dir : %GD%
echo  fake Strata : %SH%
echo ==========================================================
echo [1/3] sweeping previous test processes under %GD% ...
powershell -NoProfile -Command "$d=(Get-Location).Path; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ('*' + $d + '*') -and $_.Name -match 'python' } | ForEach-Object { Write-Host ('   kill pid ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo [2/3] starting the fake image holder :%HP% ...
start "sim-holder" /min "%SIM%" "%SH%\holder.py" %HP%
timeout /t 2 /nobreak >nul
echo [3/3] starting the gateway (keep THIS window open - closing it stops the sim tree) ...
set "STRATA_ROUTER_PORT=%RP%"
set "STRATA_HOME=%SH%"
set "STRATA_PYTHON=%SIM%"
set "STRATA_FIRST_BACKEND_PORT=%FB%"
set "GW_SCAN_WATCH_S=5"
"%SIM%" "%GD%\strata-router.py"
'''

STOP = r'''@echo off
setlocal
cd /d "%~dp0"
echo stopping the sim tree (processes whose command line contains this folder) ...
powershell -NoProfile -Command "$d=(Get-Location).Path; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ('*' + $d + '*') -and $_.Name -match 'python' } | ForEach-Object { Write-Host ('   kill pid ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo done.
'''

UPDATE = r'''@echo off
setlocal
if "%~1"=="" (echo usage: update-test.cmd ^<bundle-path^> & exit /b 2)
git -C "%~dp0." fetch %~1 dev && git -C "%~dp0." reset --hard FETCH_HEAD
git -C "%~dp0." rev-parse --short HEAD
echo now close the gateway window and double-click start-test.cmd again.
'''


def main():
    gw = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else r"D:\strata-gw-test"
    sh = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else r"D:\Strata-test"
    if not os.path.isdir(gw):
        print("gw dir missing (clone dev there first):", gw)
        return 2
    os.makedirs(sh, exist_ok=True)
    for item in ("setup.py", "holder.py", "serve", "engine"):
        s = os.path.join(KIT, item)
        d = os.path.join(sh, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy(s, d)
    cfg = {"strata_home": sh,
           "gpu_free": {"urls": ["http://127.0.0.1:%s" % HOLDER_PORT],
                        "enabled": True}}
    with open(os.path.join(gw, "gateway.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    simpy = sys.executable.replace("\\", "/")
    subs = {"%RP%": ROUTER_PORT, "%FB%": FIRST_BACKEND, "%HP%": HOLDER_PORT,
            "%SH%": sh, "%SIM%": simpy}
    for name, body in (("start-test.cmd", START), ("stop-test.cmd", STOP),
                       ("update-test.cmd", UPDATE)):
        for k, v in subs.items():
            body = body.replace(k, v)
        with open(os.path.join(gw, name), "w", encoding="ascii", newline="\r\n") as f:
            f.write(body)
    print("test env ready:")
    print("  gw dir      :", gw)
    print("  fake strata :", sh)
    print("  now double-click start-test.cmd in the gw dir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
