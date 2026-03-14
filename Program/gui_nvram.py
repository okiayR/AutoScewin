import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import ctypes
import subprocess
from pathlib import Path

import read_nvram as nv


class NVRAMGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NVRAM Quick Settings")
        self.geometry("1100x600")

        self._path_var = tk.StringVar(value="nvram.txt")
        self._status_var = tk.StringVar(value="Ready")
        self._row_vars = []

        self._build_ui()
        self._load_data(show_missing_error=False)

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="NVRAM file:").pack(side="left")
        path_entry = ttk.Entry(top, textvariable=self._path_var, width=60)
        path_entry.pack(side="left", padx=(6, 6))

        ttk.Button(top, text="Browse", command=self._browse).pack(side="left")
        ttk.Button(top, text="Load", command=self._load_data).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Export NVRAM", command=self._run_export).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Import NVRAM", command=self._run_import).pack(side="left", padx=(6, 0))

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self._canvas = tk.Canvas(list_frame, highlightthickness=0)
        self._canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self._canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self._canvas.configure(yscrollcommand=scrollbar.set)

        self._rows_frame = ttk.Frame(self._canvas)
        self._rows_window = self._canvas.create_window((0, 0), window=self._rows_frame, anchor="nw")

        self._rows_frame.bind(
            "<Configure>",
            lambda event: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda event: self._canvas.itemconfigure(self._rows_window, width=event.width),
        )

        status_bar = ttk.Label(self, textvariable=self._status_var, anchor="w")
        status_bar.pack(fill="x", padx=10, pady=(0, 8))

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select nvram.txt",
            filetypes=[("NVRAM text", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._path_var.set(path)
            self._load_data()

    @staticmethod
    def _run_batch_file(batch_path: Path, action_name: str) -> bool:
        if not batch_path.exists():
            messagebox.showerror(f"{action_name} failed", f"{batch_path.name} not found in this folder.")
            return False

        if ctypes.windll.shell32.IsUserAnAdmin():
            try:
                result = subprocess.run(
                    [str(batch_path), "--no-pause"],
                    check=False,
                    shell=True,
                )
            except Exception as exc:
                messagebox.showerror(f"{action_name} failed", str(exc))
                return False
            if result.returncode != 0:
                messagebox.showerror(
                    f"{action_name} failed",
                    f"{batch_path.name} exited with code {result.returncode}.",
                )
                return False
            return True

        quoted_batch = str(batch_path.resolve()).replace("'", "''")
        ps_command = (
            "$p = Start-Process -FilePath 'cmd.exe' "
            f"-ArgumentList '/c \"\"{quoted_batch}\"\" --no-pause' "
            "-Verb RunAs -Wait -PassThru; "
            "exit $p.ExitCode"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_command],
                check=False,
                shell=False,
            )
        except Exception as exc:
            messagebox.showerror(f"{action_name} failed", str(exc))
            return False

        if result.returncode != 0:
            messagebox.showerror(
                f"{action_name} failed",
                f"{batch_path.name} exited with code {result.returncode}.",
            )
            return False
        return True

    def _run_export(self) -> None:
        if not self._run_batch_file(Path("Export.bat"), "Export"):
            return
        self._load_data(show_missing_error=False)

    def _run_import(self) -> None:
        if not self._run_batch_file(Path("Import.bat"), "Import"):
            return
        self._load_data(show_missing_error=False)

    def _load_data(self, show_missing_error: bool = True) -> None:
        path = Path(self._path_var.get())
        if not path.exists():
            for child in self._rows_frame.winfo_children():
                child.destroy()
            self._row_vars.clear()
            self._set_status(f"File not found: {path}")
            if show_missing_error:
                messagebox.showerror("File not found", f"Cannot find: {path}")
            else:
                self._set_status(
                    "No nvram.txt yet. Run Export NVRAM to create one for this machine."
                )
            return

        try:
            settings = nv.parse_nvram_file(path)
        except Exception as exc:
            self._set_status(f"Failed to parse: {exc}")
            messagebox.showerror("Parse error", str(exc))
            return

        for child in self._rows_frame.winfo_children():
            child.destroy()
        self._row_vars.clear()

        header = ttk.Frame(self._rows_frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=0, minsize=40)
        header.columnconfigure(1, weight=0, minsize=40)
        header.columnconfigure(2, weight=1)
        header.columnconfigure(3, weight=1)

        ttk.Label(header, text="Select", anchor="center").grid(
            row=0, column=0, padx=(0, 8), sticky="ew"
        )
        ttk.Label(header, text="").grid(row=0, column=1, padx=8)
        ttk.Label(header, text="Alias").grid(row=0, column=2, padx=8)
        ttk.Label(header, text="Current").grid(row=0, column=3, padx=8)

        row = 1
        for key in nv.QUICK_LOOKUPS:
            alias = nv.QUICK_LOOKUP_ALIASES.get(key, key)
            matches = [s for s in settings if nv.match_setting_by_key(s, key)]

            row_frame = ttk.Frame(self._rows_frame)
            row_frame.grid(row=row, column=0, sticky="ew", pady=2)
            row_frame.columnconfigure(0, weight=0, minsize=40)
            row_frame.columnconfigure(1, weight=0, minsize=32)
            row_frame.columnconfigure(2, weight=1)
            row_frame.columnconfigure(3, weight=1)

            selected_var = tk.BooleanVar(value=False)
            self._row_vars.append(selected_var)
            check = ttk.Checkbutton(row_frame, variable=selected_var)
            check.grid(row=0, column=0, padx=8)

            spacer = ttk.Label(row_frame, text="")
            spacer.grid(row=0, column=1, padx=(0, 8), sticky="w")

            current_label = ttk.Label(row_frame, text="")

            def apply_setting(setting: nv.Setting) -> None:
                if setting.options:
                    labels = {o.label.lower() for o in setting.options}
                    is_toggle = labels == {"enabled", "disabled"} and len(setting.options) == 2
                    if is_toggle:
                        selected_var.set(nv.pick_current_label(setting).lower() == "enabled")
                        check.state(["!disabled"])
                        return
                selected_var.set(False)
                check.state(["disabled"])

            if not matches:
                check.state(["disabled"])
                current_label.configure(text="")
            elif len(matches) == 1:
                s = matches[0]
                if s.options:
                    current_label.configure(text=nv.pick_current_label(s))
                else:
                    current_label.configure(text=s.value or "(no value parsed)")
                apply_setting(s)
            else:
                current_label.configure(text="")
                check.state(["disabled"])

                child_frame = ttk.Frame(self._rows_frame)
                child_frame.grid(row=row + 1, column=0, sticky="ew", pady=(0, 6))
                child_frame.grid_remove()
                child_frame.columnconfigure(2, weight=1)

                expander_var = tk.BooleanVar(value=False)

                def toggle_children(frame=child_frame, button_text=expander_var) -> None:
                    button_text.set(not button_text.get())
                    if button_text.get():
                        frame.grid()
                        expander.configure(text="-")
                    else:
                        frame.grid_remove()
                        expander.configure(text="+")

                expander = ttk.Button(
                    row_frame,
                    text="+",
                    width=3,
                    command=toggle_children,
                )
                expander.grid(row=0, column=1, padx=(0, 8), sticky="w")
                spacer.grid_remove()

                for idx, match in enumerate(matches):
                    child_row = ttk.Frame(child_frame)
                    child_row.grid(row=idx, column=0, sticky="ew", padx=(32, 0), pady=2)
                    child_row.columnconfigure(3, weight=1)

                    child_var = tk.BooleanVar(value=False)
                    child_check = ttk.Checkbutton(child_row, variable=child_var)
                    child_check.grid(row=0, column=0, padx=(0, 8), sticky="w")

                    ttk.Label(child_row, text=match.question).grid(
                        row=0, column=2, padx=(0, 8), sticky="w"
                    )
                    cur_text = nv.pick_current_label(match) if match.options else (match.value or "(no value parsed)")
                    ttk.Label(child_row, text=cur_text).grid(
                        row=0, column=3, padx=(0, 8), sticky="w"
                    )

                    if match.options:
                        labels = {o.label.lower() for o in match.options}
                        is_toggle = labels == {"enabled", "disabled"} and len(match.options) == 2
                        if is_toggle:
                            child_var.set(nv.pick_current_label(match).lower() == "enabled")
                        else:
                            child_check.state(["disabled"])
                    else:
                        child_check.state(["disabled"])

            ttk.Label(row_frame, text=alias).grid(row=0, column=2, padx=(0, 8), sticky="w")
            current_label.grid(row=0, column=3, padx=(0, 8), sticky="w")
            if len(matches) > 1:
                row += 2
            else:
                row += 1

        self._set_status(f"Loaded {len(settings)} settings | {len(nv.QUICK_LOOKUPS)} quick items")

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)


def main() -> None:
    app = NVRAMGui()
    app.mainloop()


if __name__ == "__main__":
    main()
