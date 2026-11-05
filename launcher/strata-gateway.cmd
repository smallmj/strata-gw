@echo off
rem strata-gateway.cmd - start the Strata gateway on Windows.
rem Point GW_HOME at your Strata engine root (the folder holding serve\server.py
rem and the .venv). Everything else derives from it; nothing is hardcoded.
setlocal
set "GW_HOME=C:\Strata"
set "STRATA_HOME=%GW_HOME%"

set "ROUTER=%~dp0..\strata-router.py"
if defined STRATA_PYTHON (set "PY=%STRATA_PYTHON%") else (set "PY=%GW_HOME%\.venv\Scripts\python.exe")

if not exist "%ROUTER%" (
  echo [launcher] gateway entry not found next to this file: %ROUTER%  未找到网关入口
  exit /b 1
)
if not exist "%PY%" (
  echo [launcher] Strata python not found: %PY%  - set STRATA_PYTHON or fix GW_HOME
  exit /b 1
)
"%PY%" "%ROUTER%"
