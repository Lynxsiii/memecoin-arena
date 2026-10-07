@echo off
rem Run 8 first launch: archive run 7's money and keep the Claudes' journals. start_arena.cmd applies these
rem arguments to the first start only, then restarts the arena without them if it ever crashes.
call "%~dp0start_arena.cmd" --reset-money --keep-journals
