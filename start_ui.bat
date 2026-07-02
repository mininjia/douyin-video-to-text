@echo off
setlocal
cd /d "%~dp0"
title Douyin to Text
echo Starting local service...
python work\ui_server.py
pause
