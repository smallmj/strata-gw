@echo off
rem =====================================================================
rem  strata-gw launcher  (mirrors the legacy internal strata-gw.cmd)
rem  [1/3] sweep OUR previous gateway + its engine children, so a restart
rem        never leaves a half-dead process holding the console
rem  [2/3] free the gateway port (18075 by default) if anyone still holds it
rem  [3/3] start the gateway in THIS window (closing the window stops the
rem        engines too - they live in this job)
rem  Safety: the sweep only ever touches python processes whose command
rem  line contains THIS folder. A production router living in another
rem  folder is never harmed.
rem =====================================================================
setlocal
cd /d "%~dp0"
if "%GATEWAY_PORT%"=="" set GATEWAY_PORT=18075
set "GATEWAY_PY=D:\Strata\.venv\Scripts\python.exe"
if not exist "%GATEWAY_PY%" set "GATEWAY_PY=python"

echo [1/3] sweeping previous gateway processes under %CD% ...
powershell -NoProfile -Command "$d=(Get-Location).Path; Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like ('*' + $d + '*') } | ForEach-Object { Write-Host ('   kill pid ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [2/3] freeing port %GATEWAY_PORT% ...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %GATEWAY_PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('   kill port owner pid ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo [3/3] starting gateway (keep this window open) ...
"%GATEWAY_PY%" strata-router.py
