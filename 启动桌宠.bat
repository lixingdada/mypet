@echo off
title Desktop Pet
cd /d "%~dp0"
set "PYW=%USERPROFILE%\.workbuddy\binaries\python\envs\pet\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
start "" "%PYW%" "%~dp0pet.py"
