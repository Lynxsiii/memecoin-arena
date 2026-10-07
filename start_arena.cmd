@echo off
title Memecoin Arena
cd /d C:\Users\noahh\Downloads\memecoin-arena
if not exist logs mkdir logs
rem Arguments (e.g. --reset-money --keep-journals) apply to the FIRST start only; restarts after a crash get none.
set ARGS=%*
:loop
if exist stop.flag (echo stop.flag found, not restarting & goto end)
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set D=%%d
echo [%date% %time%] starting python -u main.py %ARGS% >> logs\arena-%D%.log
python -u main.py %ARGS% >> logs\arena-%D%.log 2>&1
set RC=%errorlevel%
set ARGS=
echo [%date% %time%] exited with %RC%, restarting in 15s >> logs\arena-%D%.log
powershell -NoProfile -Command Start-Sleep 15
goto loop
:end
cmd /k
