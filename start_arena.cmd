@echo off
cd /d "%~dp0"
title Memecoin Arena (Ctrl+C does nothing; create stop.flag to stop)
rem Thin wrapper: run_arena.py is the Ctrl+C-proof watchdog (restart loop, logs\arena-DATE.log, stop.flag).
rem Arguments (e.g. --reset-money --keep-journals) apply to the FIRST start only.
python -u run_arena.py %*
cmd /k
