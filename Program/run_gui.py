from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True


PROGRAM_DIR = Path(__file__).resolve().parent
REPO_DIR = PROGRAM_DIR.parent
BUNDLED_PYTHON = (
    REPO_DIR
    / "Supporting"
    / "pyhwinfo-master"
    / "pyhwinfo-master"
    / "python"
    / "python.exe"
)


def _run_with_current_python(module_name: str) -> int:
    module = __import__(module_name)
    main = getattr(module, "main", None)
    try:
        if callable(main):
            main()
            return 0
        runpy.run_module(module_name, run_name="__main__")
        return 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1


def _run_tk_with_bundled_python() -> int:
    if not BUNDLED_PYTHON.exists():
        raise FileNotFoundError(f"Bundled Python not found at {BUNDLED_PYTHON}")

    bootstrap = (
        "import runpy, sys; "
        f"sys.path.insert(0, r'{PROGRAM_DIR}'); "
        f"runpy.run_path(r'{PROGRAM_DIR / 'gui_nvram.py'}', run_name='__main__')"
    )
    result = subprocess.run(
        [str(BUNDLED_PYTHON), "-c", bootstrap],
        cwd=str(PROGRAM_DIR),
        check=False,
    )
    return result.returncode


def _print_environment_help(pyside_error: BaseException, tk_error: BaseException | None) -> None:
    print("AutoScewin could not start a GUI.")
    print()
    print("Primary GUI failure:")
    print(f"  {type(pyside_error).__name__}: {pyside_error}")
    print()
    if tk_error is not None:
        print("Fallback GUI failure:")
        print(f"  {type(tk_error).__name__}: {tk_error}")
        print()
    print("How to fix it:")
    print("  1. Install PySide6 into the Python interpreter used by this repo,")
    print(f"     currently: {sys.executable}")
    print("  2. Or keep using the bundled Python fallback shipped under Supporting/.")


def main() -> int:
    os.chdir(PROGRAM_DIR)

    pyside_error: Exception | None = None
    try:
        return _run_with_current_python("gui_pyside")
    except Exception as exc:
        pyside_error = exc

    try:
        return _run_tk_with_bundled_python()
    except Exception as exc:
        _print_environment_help(pyside_error, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
