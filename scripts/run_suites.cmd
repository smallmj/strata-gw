@echo off
rem run_suites.cmd - the release gate on the Windows box, in one command.
rem
rem The suites print bilingual labels, and one pin names the gear glyph; the box
rem starts cmd in code page 936, so a bare "python tests\test_x.py" dies INSIDE a
rem PASS line with UnicodeEncodeError and the verdict never prints - the run
rem looks like a green file followed by a bare traceback. PYTHONUTF8=1 is the whole
rem fix. Run this from anywhere; it cds to the repo root on its own.
setlocal
set PY=%1
if "%PY%"=="" set PY=python
cd /d "%~dp0.."
set PYTHONUTF8=1
set FAILS=0
for %%f in (tests\test_*.py) do (
  echo == %%f
  call %PY% "%%f" 2>&1 | findstr /B /C:"ALL PASS" /C:"FAILED" /C:"SKIP"
  if errorlevel 1 set /a FAILS+=1
)
if %FAILS% GTR 0 (
  echo %FAILS% suite^(s^) not green
  exit /b 1
)
echo ALL SUITES GREEN
exit /b 0
