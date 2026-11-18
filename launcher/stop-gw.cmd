@echo off
rem stop-gw.cmd - stop THIS deployment's gateway (router, its lazy backends and engines).
rem
rem The old version matched the router by the substring "strata-gw\strata-router" in its
rem command line, but the live router's command line is only "strata-router.py" (the fold-
rem er lives in its cwd), so nothing was ever killed. This version identifies the gateway
rem by the port it listens on (GATEWAY_PORT, default 18075), kills the process tree under
rem that port, sweeps orphaned routers, and verifies the port is free before saying ok.
setlocal
if "%GATEWAY_PORT%"=="" set GATEWAY_PORT=18075
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-gw.ps1" -Port %GATEWAY_PORT%
endlocal
