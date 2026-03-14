from __future__ import annotations

import shutil
import sys
from pathlib import Path


PROGRAM_SUBDIR = "Program"
RUNTIME_SUBDIR = "_autoscewin_runtime"
REQUIRED_TOOL_FILES = (
    "SCEWIN_64.exe",
    "amifldrv64.sys",
    "amigendrv64.sys",
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / PROGRAM_SUBDIR
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_path(*parts: str) -> Path:
    return app_root().joinpath(*parts)


def bundle_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def default_nvram_path() -> Path:
    return app_path("nvram.txt")


def default_log_path() -> Path:
    return app_path("log-file.txt")


def preset_path(*parts: str) -> Path:
    return bundle_path("Presets", *parts)


def required_tool_paths() -> dict[str, Path]:
    return {name: bundle_path(name) for name in REQUIRED_TOOL_FILES}


def runtime_root() -> Path:
    return app_path(RUNTIME_SUBDIR)


def ensure_runtime_tools() -> Path:
    runtime_dir = runtime_root()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for name, source in required_tool_paths().items():
        destination = runtime_dir / name
        if destination.exists():
            try:
                same_size = destination.stat().st_size == source.stat().st_size
            except OSError:
                same_size = False
            if same_size:
                continue
        shutil.copy2(source, destination)
    return runtime_dir
