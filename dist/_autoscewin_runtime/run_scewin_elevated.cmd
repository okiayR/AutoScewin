@echo off
cd /d "C:\Programming\Repos\AutoScewin\dist\_autoscewin_runtime"
"C:\Programming\Repos\AutoScewin\dist\_autoscewin_runtime\SCEWIN_64.exe" /o /s "C:\Programming\Repos\AutoScewin\dist\nvram.txt" > "C:\Programming\Repos\AutoScewin\dist\log-file.txt" 2>&1
exit /b %errorlevel%
