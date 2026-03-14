from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path


PROGRAM_SUBDIR = "Program"
RUN_GUI_NAME = "run_gui.py"
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_runtime_workspace() -> Path:
    runtime_dir = Path(tempfile.mkdtemp(prefix="autoscewin-"))
    for name, source in required_tool_paths().items():
        destination = runtime_dir / name
        shutil.copy2(source, destination)
        if _sha256(source) != _sha256(destination):
            raise RuntimeError(f"Failed to verify copied runtime file: {name}")
    return runtime_dir


def cleanup_runtime_workspace(path: Path | None) -> None:
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)


def launcher_command(extra_args: list[str] | None = None) -> tuple[Path, list[str]]:
    args = list(extra_args or [])
    if is_frozen():
        return Path(sys.executable).resolve(), args
    return Path(sys.executable).resolve(), [str(app_path(RUN_GUI_NAME)), *args]
