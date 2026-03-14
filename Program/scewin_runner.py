from __future__ import annotations

import ctypes
import subprocess
from dataclasses import dataclass
from pathlib import Path

import app_runtime


@dataclass
class ScewinRunResult:
    ok: bool
    action_name: str
    code: int | None = None
    error: str | None = None
    log_path: Path | None = None


def _is_windows() -> bool:
    return hasattr(ctypes, "windll")


def _is_admin() -> bool:
    if not _is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _build_command(mode: str, nvram_path: Path, tools_dir: Path) -> list[str]:
    scewin_path = tools_dir / "SCEWIN_64.exe"
    mode_flag = "/o" if mode == "export" else "/i"
    return [str(scewin_path), mode_flag, "/s", str(nvram_path)]


def _validate_runtime_files(action_name: str) -> ScewinRunResult | None:
    if not _is_windows():
        return ScewinRunResult(
            ok=False,
            action_name=action_name,
            error="This tool can only run on Windows.",
        )

    missing = [
        path.name
        for path in app_runtime.required_tool_paths().values()
        if not path.exists()
    ]
    if not missing:
        return None

    return ScewinRunResult(
        ok=False,
        action_name=action_name,
        error="Missing required runtime files: " + ", ".join(missing),
    )


def _run_direct(command: list[str], working_dir: Path, log_path: Path) -> int:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        result = subprocess.run(
            command,
            cwd=str(working_dir),
            check=False,
            shell=False,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    return result.returncode


def _read_text_if_present(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _run_elevated(mode: str, nvram_path: Path, log_path: Path) -> tuple[int, str]:
    launcher_path, launcher_args = app_runtime.launcher_command(
        ["--elevated-scewin", mode, str(nvram_path), str(log_path)]
    )
    arg_list = ", ".join(_ps_quote(arg) for arg in launcher_args)
    elevated_script = (
        f"$argList = @({arg_list}); "
        "$p = Start-Process "
        f"-FilePath {_ps_quote(str(launcher_path))} "
        "-ArgumentList $argList "
        f"-WorkingDirectory {_ps_quote(str(app_runtime.app_root()))} "
        "-Verb RunAs -Wait -PassThru; "
        "exit $p.ExitCode"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", elevated_script],
        check=False,
        shell=False,
        capture_output=True,
        text=True,
    )
    output_parts = []
    if result.stdout:
        output_parts.append(result.stdout.strip())
    if result.stderr:
        output_parts.append(result.stderr.strip())
    return result.returncode, "\n".join(part for part in output_parts if part)


def run_elevated_helper(mode: str, nvram_path: Path, log_path: Path) -> int:
    action_name = "Export" if mode == "export" else "Import"
    runtime_error = _validate_runtime_files(action_name)
    if runtime_error is not None:
        return 1

    workspace: Path | None = None
    try:
        workspace = app_runtime.create_runtime_workspace()
        command = _build_command(mode, nvram_path.resolve(), workspace)
        return _run_direct(command, workspace, log_path.resolve())
    finally:
        app_runtime.cleanup_runtime_workspace(workspace)


def _run(mode: str, nvram_path: Path) -> ScewinRunResult:
    action_name = "Export" if mode == "export" else "Import"
    runtime_error = _validate_runtime_files(action_name)
    if runtime_error is not None:
        return runtime_error

    nvram_path = nvram_path.resolve()
    log_path = app_runtime.default_log_path()
    if log_path.exists():
        log_path.unlink()

    try:
        if _is_admin():
            workspace = app_runtime.create_runtime_workspace()
            try:
                command = _build_command(mode, nvram_path, workspace)
                code = _run_direct(command, workspace, log_path)
            finally:
                app_runtime.cleanup_runtime_workspace(workspace)
            launcher_output = ""
        else:
            code, launcher_output = _run_elevated(mode, nvram_path, log_path)
    except Exception as exc:
        return ScewinRunResult(
            ok=False,
            action_name=action_name,
            error=str(exc),
            log_path=log_path,
        )

    if code != 0 and not log_path.exists():
        error = launcher_output or (
            "The elevated command did not start. This usually means the Windows "
            "administrator prompt was canceled or blocked."
        )
        return ScewinRunResult(
            ok=False,
            action_name=action_name,
            code=code,
            error=error,
            log_path=None,
        )

    log_text = _read_text_if_present(log_path)
    if code != 0 and log_text:
        error = f"{action_name} exited with code {code}.\n\n{log_text}"
        return ScewinRunResult(
            ok=False,
            action_name=action_name,
            code=code,
            error=error,
            log_path=log_path,
        )

    return ScewinRunResult(
        ok=(code == 0),
        action_name=action_name,
        code=code,
        log_path=log_path,
    )


def run_export(nvram_path: Path | None = None) -> ScewinRunResult:
    return _run("export", nvram_path or app_runtime.default_nvram_path())


def run_import(nvram_path: Path | None = None) -> ScewinRunResult:
    return _run("import", nvram_path or app_runtime.default_nvram_path())
