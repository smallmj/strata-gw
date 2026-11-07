@echo off
rem thin wrapper: python does the heavy lifting (see make_env.py)
python "%~dp0make_env.py" %*
