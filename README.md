GUI for changing bios settings using SCEWIN.

Main launcher:
run_gui.bat

Python launcher:
python run_gui.py

PySide6 setup:
pip install PySide6

If PySide6 is unavailable, `run_gui.py` falls back to the bundled Python Tk GUI
shipped in `Supporting/pyhwinfo-master/pyhwinfo-master/python`.

First-time use:
Run `Export.bat` or choose the export prompt on startup to create `nvram.txt`
for your own machine before editing settings.

Single EXE build:
Install `PySide6` and `pyinstaller`, then run:

`pyinstaller --clean --noconfirm autoscewin.spec`

or:

`build_exe.bat`

The finished one-file Windows build will be created as:

`dist/AutoScewin.exe`

That EXE bundles the Python app, `SCEWIN_64.exe`, and the required `.sys`
driver files. At runtime it extracts the bundled BIOS tool to a temporary
folder, runs it elevated, and keeps `nvram.txt` plus `log-file.txt` next to
the EXE.
