@echo off
rem =====================================================================
rem  strata-gw launcher  (mirrors the legacy internal strata-gw.cmd)
rem  [1/3] sweep OUR previous gateway + its tree, so a restart
rem        never leaves a half-dead process holding the console
rem  [2/3] free the gateway port (18075 by default), then VERIFY it:
rem        if the holder survives the kill (it runs under another
rem        account - e.g. an old headless instance started as SYSTEM),
rem        the launcher STOPS with the pid + owner named. A second
rem        router on one port silently splits traffic and hides the
rem        engines' logs in the other window - never do that quietly.
rem  [3/3] start the gateway in THIS window (closing the window stops
rem        the engines too - they live in this job)
rem  Safety: the sweep only ever touches python processes whose command
rem  line contains THIS folder. A production router living in another
rem  folder is never harmed.
rem =====================================================================
setlocal
cd /d "%~dp0"
if "%GATEWAY_PORT%"=="" set GATEWAY_PORT=18075
set "GATEWAY_PY=D:\Strata\.venv\Scripts\python.exe"
if not exist "%GATEWAY_PY%" set "GATEWAY_PY=python"

net session >nul 2>&1 || echo NOTE: this window is NOT elevated - processes owned by another account (e.g. SYSTEM) cannot be stopped from here

echo [1/3] sweeping previous gateway processes under %CD% ...
powershell -NoProfile -Command "$d=(Get-Location).Path; Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like ('*' + $d + '*') } | ForEach-Object { Write-Host ('   taskkill /F /T pid ' + $_.ProcessId); taskkill /F /T /PID $_.ProcessId }"

echo [2/3] freeing port %GATEWAY_PORT% ...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %GATEWAY_PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('   kill port owner pid ' + $_.OwningProcess); taskkill /F /T /PID $_.OwningProcess }"
powershell -NoProfile -Command "$p=%GATEWAY_PORT%; for($i=0;$i -lt 12;$i++){ if(-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)){ exit 0 }; Start-Sleep -Milliseconds 500 }; Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $proc=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.OwningProcess); $o=$proc | Invoke-CimMethod -Name GetOwner -ErrorAction SilentlyContinue; Write-Host ('   STILL HELD by pid ' + $_.OwningProcess + ' (' + $proc.Name + ', owner ' + $o.Domain + [char]92 + $o.User + ')') }; exit 1"
if errorlevel 1 (
echo [2/3] FAILED: port %GATEWAY_PORT% is still held by the process named above.
echo        Refusing to start: a second router on one port splits requests and
echo        keeps the engines' logs out of this window. Open an ELEVATED
echo        window and run   taskkill /F /T /PID ^<pid^>   then run this again.
exit /b 1
)

echo [3/3] starting gateway (keep this window open) ...
"%GATEWAY_PY%" strata-router.py
