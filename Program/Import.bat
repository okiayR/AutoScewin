@echo off
set "NO_PAUSE=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

:: Request administrator privileges
fltmc >nul 2>&1 || (
    PowerShell Start -Verb RunAs '%0' 2> nul || (
        echo error: right-click on the script and select "Run as administrator"
        if "%NO_PAUSE%"=="0" pause
    )
    exit /b 1
)

pushd %~dp0

for %%a in ("amifldrv64.sys", "amigendrv64.sys", "nvram.txt") do (
    if not exist "%%~a" (
        echo error: %%~a not found in the current directory

        if "%%~a" == "nvram.txt" (
            echo Please rename your NVRAM script file to "nvram.txt" or run "Export.bat" to create it
        )

        if "%NO_PAUSE%"=="0" pause
        exit /b 1
    )
)

SCEWIN_64.exe /i /s nvram.txt 2> log-file.txt
type log-file.txt
echo See log-file.txt for output messages
if "%NO_PAUSE%"=="0" pause
