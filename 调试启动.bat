@echo off
title Desktop Pet (Debug)
cd /d "%~dp0"
set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\pet\Scripts\python.exe"
if not exist "%PY%" set "PY=python.exe"
"%PY%" "%~dp0pet.py"
echo.
echo [pet.py exited - see the messages above]
pause
