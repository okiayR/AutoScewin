@echo off
setlocal
cd /d "%~dp0"
py -3 -m PyInstaller --clean --noconfirm autoscewin.spec
