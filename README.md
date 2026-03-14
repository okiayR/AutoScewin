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
