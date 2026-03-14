# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


# PyInstaller executes spec files without defining __file__, so anchor to the
# current working directory used by build_exe.bat.
repo_root = Path.cwd()
program_dir = repo_root / "Program"
datas = [
    (str(program_dir / "SCEWIN_64.exe"), "Program"),
    (str(program_dir / "amifldrv64.sys"), "Program"),
    (str(program_dir / "amigendrv64.sys"), "Program"),
]

presets_dir = program_dir / "Presets"
if presets_dir.exists():
    datas.append((str(presets_dir), "Program/Presets"))


a = Analysis(
    ["Program/run_gui.py"],
    pathex=[str(program_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "app_runtime",
        "gui_pyside",
        "read_nvram",
        "scewin_runner",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AutoScewin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
