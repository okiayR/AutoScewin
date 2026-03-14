GUI for changing bios settings using SCEWIN.

Main launcher:
run_gui.bat

Python launcher:
python run_gui.py

PySide6 setup:
pip install PySide6

If PySide6 is unavailable, `run_gui.py` falls back to the bundled Python Tk GUI
shipped in `Supporting/pyhwinfo-master/pyhwinfo-master/python`.

GitHub note:
Do not commit generated machine-specific files such as `nvram.txt`,
`nvram.txt.bak`, `nvram_default.txt`, or `log-file.txt`.

First-time use:
Run `Export.bat` or choose the export prompt on startup to create `nvram.txt`
for your own machine before editing settings.
