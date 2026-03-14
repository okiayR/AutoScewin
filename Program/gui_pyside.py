from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets

import app_runtime
import read_nvram as nv
import scewin_runner


TOKEN_COL_WIDTH = 90
ACTION_COL_WIDTH = 88
RESET_COL_WIDTH = 88
TREE_INDENT_PX = 14


def is_toggle_setting(setting: nv.Setting) -> bool:
    if not setting.options:
        return False
    labels = {o.label.lower() for o in setting.options}
    return labels == {"enabled", "disabled"} and len(setting.options) == 2


class NoWheelComboBox(QtWidgets.QComboBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class NVRAMWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NVRAM Quick Settings")
        self.resize(1100, 600)

        self._path_edit = QtWidgets.QLineEdit("nvram.txt")
        self._search_edit = QtWidgets.QLineEdit()
        self._search_edit.setPlaceholderText("Search...")
        self._preset_combo = QtWidgets.QComboBox()
        self._preset_combo.addItem("None")
        self._preset_combo.addItem("Low Latency, No Power Saving")
        self._status_label = QtWidgets.QLabel("Ready")
        self._save_button = QtWidgets.QPushButton("Save")
        self._save_button.setEnabled(False)
        self._reset_all_button = QtWidgets.QPushButton("Reset All")
        self._reset_all_button.setEnabled(False)
        self._dirty = False
        self._original_text = ""
        self._original_values: dict[str, dict[str, str]] = {}
        self._token_to_name: dict[str, str] = {}
        self._value_formats: dict[str, str] = {}
        self._pending_updates: dict[str, dict[str, str]] = {}
        self._presets: dict[str, dict[str, str]] = {}

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(["Alias", "Token", "Current", "Enable", "Disable", "Reset"])
        self._tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setStyleSheet("QTreeWidget::item { padding: 2px 4px; }")

        self._build_ui()
        if not self._show_disclaimer():
            QtCore.QTimer.singleShot(0, QtWidgets.QApplication.instance().quit) # type: ignore
            return
        self._load_presets()
        self._load_data(show_missing_error=False)

    def _build_ui(self) -> None:
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("NVRAM file:"))
        top.addWidget(self._path_edit, stretch=1)

        load_btn = QtWidgets.QPushButton("Load")
        load_btn.clicked.connect(self._load_data)
        top.addWidget(load_btn)
        import_btn = QtWidgets.QPushButton("Import NVRAM")
        import_btn.clicked.connect(self._run_import)
        top.addWidget(import_btn)
        top.addWidget(QtWidgets.QLabel("Preset:"))
        top.addWidget(self._preset_combo)
        top.addWidget(QtWidgets.QLabel("Search:"))
        top.addWidget(self._search_edit, stretch=1)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(self._tree, stretch=1)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(self._status_label, stretch=1)
        bottom.addWidget(self._reset_all_button)
        bottom.addWidget(self._save_button)
        layout.addLayout(bottom)

        self.setCentralWidget(container)
        self._search_edit.textChanged.connect(self._apply_filter)
        self._save_button.clicked.connect(self._save_to_file)
        self._reset_all_button.clicked.connect(self._reset_all_defaults)
        self._preset_combo.activated[int].connect(self._on_preset_activated) # type: ignore

    @staticmethod
    def _clean_value_text(raw: str) -> str:
        clean = raw.split("//", 1)[0].strip()
        if clean.startswith("<") and clean.endswith(">"):
            return clean[1:-1].strip()
        return clean

    @staticmethod
    def _detect_value_format(raw: str) -> str:
        clean = raw.split("//", 1)[0].strip()
        if clean.startswith("<") and clean.endswith(">"):
            return "angle"
        return "raw"

    def _load_presets(self) -> None:
        self._presets.clear()
        preset_file = app_runtime.preset_path("Low Latency, No Powersaving.txt")
        if not preset_file.exists():
            return
        name = "Low Latency, No Power Saving"
        self._presets[name] = self._parse_preset_file(preset_file)

    @staticmethod
    def _parse_preset_file(path: Path) -> dict[str, str]:
        entries: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            entries[key] = value
        return entries

    def _configure_tree_header(self) -> None:
        header = self._tree.header()
        header.setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(0)
        self._tree.setColumnWidth(1, TOKEN_COL_WIDTH)
        self._tree.setColumnWidth(2, 260)
        self._tree.setColumnWidth(3, ACTION_COL_WIDTH)
        self._tree.setColumnWidth(4, ACTION_COL_WIDTH)
        self._tree.setColumnWidth(5, RESET_COL_WIDTH)
        header.resizeSection(1, TOKEN_COL_WIDTH)
        header.resizeSection(3, ACTION_COL_WIDTH)
        header.resizeSection(4, ACTION_COL_WIDTH)
        header.resizeSection(5, RESET_COL_WIDTH)
        self._tree.setIndentation(TREE_INDENT_PX)
        header_item = self._tree.headerItem()
        header_item.setTextAlignment(1, QtCore.Qt.AlignmentFlag.AlignCenter)
        header_item.setTextAlignment(3, QtCore.Qt.AlignmentFlag.AlignCenter)
        header_item.setTextAlignment(4, QtCore.Qt.AlignmentFlag.AlignCenter)
        header_item.setTextAlignment(5, QtCore.Qt.AlignmentFlag.AlignCenter)

    def _show_disclaimer(self) -> bool:
        message = (
            "This BIOS GUI Editor modifies firmware-level data. Improper use may corrupt your BIOS image and render "
            "your system unstable or inoperable. If issues occur, you may be required to reflash your BIOS or reset "
            "your CMOS to recover functionality. I am not responsible for any damage, data loss, or hardware failure. "
            "Use this software at your own risk."
        )
        reply = QtWidgets.QMessageBox.question(
            self,
            "Disclaimer",
            message,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes

    @staticmethod
    def _show_scewin_result(result: scewin_runner.ScewinRunResult) -> bool:
        if result.ok:
            return True

        details = result.error or f"{result.action_name} exited with code {result.code}."
        if result.log_path is not None:
            details = f"{details}\n\nSee log for details:\n{result.log_path}"
        QtWidgets.QMessageBox.critical(None, f"{result.action_name} failed", details)
        return False

    @staticmethod
    def run_export() -> bool:
        return NVRAMWindow._show_scewin_result(scewin_runner.run_export())

    def run_import(self) -> bool:
        nvram_path = Path(self._path_edit.text())
        return self._show_scewin_result(scewin_runner.run_import(nvram_path))

    def _run_import(self) -> None:
        if not self.run_import():
            return
        self._load_data()

    def _load_data(self, *, show_missing_error: bool = True) -> None:
        path = Path(self._path_edit.text())
        if not path.exists():
            self._tree.clear()
            self._configure_tree_header()
            self._save_button.setEnabled(False)
            self._reset_all_button.setEnabled(False)
            self._set_status(f"File not found: {path}")
            if show_missing_error:
                QtWidgets.QMessageBox.critical(self, "File not found", f"Cannot find: {path}")
            else:
                self._set_status(
                    "No nvram.txt yet. Run Export NVRAM or choose export on startup to create one."
                )
            return

        try:
            settings = nv.parse_nvram_file(path)
        except Exception as exc:
            self._set_status(f"Failed to parse: {exc}")
            QtWidgets.QMessageBox.critical(self, "Parse error", str(exc))
            return

        self._tree.clear()
        self._configure_tree_header()
        self._dirty = False
        self._save_button.setEnabled(False)
        self._reset_all_button.setEnabled(False)
        self._original_text = path.read_text(encoding="utf-8", errors="replace")
        self._pending_updates = {}
        self._original_values = {}
        self._token_to_name = {}
        self._value_formats = {}

        for key in nv.QUICK_LOOKUPS:
            alias = nv.QUICK_LOOKUP_ALIASES.get(key, key)
            matches = [s for s in settings if nv.match_setting_by_key(s, key)]

            if not matches:
                continue

            if len(matches) == 1:
                setting = matches[0]
                self._token_to_name[setting.token] = setting.question
                if setting.options:
                    self._original_values[setting.token] = {
                        "option_label": nv.pick_current_label(setting)
                    }
                else:
                    self._original_values[setting.token] = {
                        "value": self._clean_value_text(setting.value or "")
                    }
                    self._value_formats[setting.token] = self._detect_value_format(
                        setting.value or ""
                    )
                if setting.options:
                    editor = NoWheelComboBox()
                    option_labels = [o.label for o in setting.options]
                    editor.addItems(option_labels)
                    sel_idx = nv.pick_selected_option_index(setting)
                    if sel_idx is not None:
                        editor.setCurrentIndex(sel_idx)
                    cur_text = editor.currentText()
                    editor.currentIndexChanged.connect(self._mark_dirty)
                else:
                    cur_text = self._clean_value_text(setting.value or "")
                    if setting.question.strip().lower() == "enable hibernation":
                        editor = NoWheelComboBox()
                        editor.addItems(["0", "1"])
                        if cur_text in ("0", "1"):
                            editor.setCurrentIndex(0 if cur_text == "0" else 1)
                        cur_text = editor.currentText()
                        editor.currentIndexChanged.connect(self._mark_dirty)
                    else:
                        editor = QtWidgets.QLineEdit(cur_text)
                        editor.textEdited.connect(self._mark_dirty)
                enabled = is_toggle_setting(setting)
                checked = enabled and (nv.pick_current_label(setting).lower() == "enabled")
                self._add_tree_item(
                    None,
                    alias,
                    setting.token,
                    cur_text or "(no value parsed)" if not setting.options else cur_text,
                    checked=checked,
                    checkable=enabled,
                    current_editor=editor,
                    setting=setting,
                )
                continue

            parent_item = self._add_tree_item(
                None,
                alias,
                "",
                "",
                checked=False,
                checkable=False,
                setting=None,
            )
            parent_item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )

            child_items: list[QtWidgets.QTreeWidgetItem] = []
            all_toggle = True
            for match in matches:
                self._token_to_name[match.token] = match.question
                if match.options:
                    self._original_values[match.token] = {
                        "option_label": nv.pick_current_label(match)
                    }
                else:
                    self._original_values[match.token] = {
                        "value": self._clean_value_text(match.value or "")
                    }
                    self._value_formats[match.token] = self._detect_value_format(
                        match.value or ""
                    )
                if match.options:
                    editor = NoWheelComboBox()
                    option_labels = [o.label for o in match.options]
                    editor.addItems(option_labels)
                    sel_idx = nv.pick_selected_option_index(match)
                    if sel_idx is not None:
                        editor.setCurrentIndex(sel_idx)
                    cur_text = editor.currentText()
                    editor.currentIndexChanged.connect(self._mark_dirty)
                    if not any(lbl.strip().lower() == "enabled" for lbl in option_labels):
                        all_toggle = False
                    if not any(lbl.strip().lower() == "disabled" for lbl in option_labels):
                        all_toggle = False
                else:
                    cur_text = self._clean_value_text(match.value or "")
                    if match.question.strip().lower() == "enable hibernation":
                        editor = NoWheelComboBox()
                        editor.addItems(["0", "1"])
                        if cur_text in ("0", "1"):
                            editor.setCurrentIndex(0 if cur_text == "0" else 1)
                        cur_text = editor.currentText()
                        editor.currentIndexChanged.connect(self._mark_dirty)
                    else:
                        editor = QtWidgets.QLineEdit(cur_text)
                        editor.textEdited.connect(self._mark_dirty)
                    all_toggle = False
                enabled = is_toggle_setting(match)
                checked = enabled and (nv.pick_current_label(match).lower() == "enabled")
                child_item = self._add_tree_item(
                    parent_item,
                    match.question,
                    match.token,
                    cur_text or "(no value parsed)" if not match.options else cur_text,
                    checked=checked,
                    checkable=enabled,
                    current_editor=editor,
                    setting=match,
                )
                child_items.append(child_item)

            if all_toggle and child_items:
                enable_btn = QtWidgets.QPushButton("Enable")
                disable_btn = QtWidgets.QPushButton("Disable")
                enable_btn.setFixedWidth(ACTION_COL_WIDTH - 12)
                disable_btn.setFixedWidth(ACTION_COL_WIDTH - 12)
                enable_btn.clicked.connect(
                    lambda _checked=False, items=child_items: self._set_group_toggle(items, True)
                )
                disable_btn.clicked.connect(
                    lambda _checked=False, items=child_items: self._set_group_toggle(items, False)
                )
                self._tree.setItemWidget(parent_item, 3, enable_btn)
                self._tree.setItemWidget(parent_item, 4, disable_btn)

            if child_items:
                parent_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"children": child_items})
                reset_widget = self._tree.itemWidget(parent_item, 5)
                if isinstance(reset_widget, QtWidgets.QWidget):
                    btn = reset_widget.findChild(QtWidgets.QPushButton)
                    if btn is not None:
                        btn.setEnabled(True)
                        btn.setToolTip("Reset all children to BIOS defaults")

        self._set_status(
            f"Loaded {len(settings)} settings | {len(nv.QUICK_LOOKUPS)} quick items"
        )
        self._tree.header().resizeSection(5, RESET_COL_WIDTH)
        self._apply_filter(self._search_edit.text())
        self._reset_all_button.setEnabled(True)

    def _add_tree_item(
        self,
        parent: QtWidgets.QTreeWidgetItem | None,
        alias: str,
        token: str,
        current: str,
        *,
        checked: bool,
        checkable: bool,
        current_editor: QtWidgets.QWidget | None = None,
        setting: nv.Setting | None,
    ) -> QtWidgets.QTreeWidgetItem:
        item = QtWidgets.QTreeWidgetItem(parent or self._tree)
        item.setText(0, alias)
        item.setText(1, token)
        item.setTextAlignment(1, QtCore.Qt.AlignmentFlag.AlignCenter)
        item.setFlags(
            item.flags()
            | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        if current_editor is not None:
            self._tree.setItemWidget(item, 2, current_editor)
        self._store_current_text(item, current)
        if setting is not None:
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"setting": setting})

        reset_button = QtWidgets.QPushButton("Reset")
        reset_button.setFixedWidth(RESET_COL_WIDTH - 32)
        reset_button.setEnabled(setting is not None)
        reset_button.clicked.connect(lambda _checked=False, i=item: self._apply_default(i))

        reset_container = QtWidgets.QWidget()
        reset_layout = QtWidgets.QHBoxLayout(reset_container)
        reset_layout.setContentsMargins(2, 0, 2, 0)
        reset_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        reset_layout.addWidget(reset_button)
        if setting is not None:
            default_label = nv.pick_default_label(setting)
            default_value = nv.pick_default_value(setting)
            default_text = default_label or default_value or "No BIOS default found"
            reset_button.setToolTip(f"BIOS Default: {default_text}")
        self._tree.setItemWidget(item, 5, reset_container)
        return item

    def _store_current_text(self, item: QtWidgets.QTreeWidgetItem, text: str) -> None:
        item.setData(2, QtCore.Qt.ItemDataRole.UserRole, text)
        if self._tree.itemWidget(item, 2) is None:
            item.setText(2, text)
        else:
            item.setText(2, "")

    def _apply_default(self, item: QtWidgets.QTreeWidgetItem) -> None:
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("children"):
            for child in data["children"]:
                self._apply_default(child)
            self._mark_dirty()
            return
        if not isinstance(data, dict) or "setting" not in data:
            return
        setting = data["setting"]
        editor = self._tree.itemWidget(item, 2)
        if isinstance(editor, QtWidgets.QComboBox):
            default_idx = nv.pick_default_option_index(setting)
            if default_idx is None:
                default_idx = 0 if editor.count() > 0 else None
            if default_idx is None:
                return
            editor.setCurrentIndex(default_idx)
            self._store_current_text(item, editor.currentText())
        else:
            default_label = nv.pick_default_label(setting)
            default_value = nv.pick_default_value(setting)
            default_text = default_label or default_value
            if not default_text:
                return
            default_text = self._clean_value_text(default_text)
            if isinstance(editor, QtWidgets.QLineEdit):
                editor.setText(default_text)
            self._store_current_text(item, default_text)

        self._mark_dirty()

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _format_value(self, token: str, value: str) -> str:
        if self._value_formats.get(token) == "angle":
            stripped = value.strip()
            if not (stripped.startswith("<") and stripped.endswith(">")):
                return f"<{stripped}>"
        return value

    def _set_group_toggle(self, items: list[QtWidgets.QTreeWidgetItem], enable: bool) -> None:
        target = "enabled" if enable else "disabled"
        for item in items:
            editor = self._tree.itemWidget(item, 2)
            if not isinstance(editor, QtWidgets.QComboBox):
                continue
            for i in range(editor.count()):
                if editor.itemText(i).strip().lower() == target:
                    editor.setCurrentIndex(i)
                    self._store_current_text(item, editor.currentText())
                    break
        self._mark_dirty()

    def _on_preset_activated(self, index: int) -> None:
        name = self._preset_combo.itemText(index)
        self._apply_preset(name)

    @staticmethod
    def _set_combo_to_text(editor: QtWidgets.QComboBox, desired: str) -> bool:
        alternatives = [p.strip() for p in desired.split(" or ")]
        if not alternatives:
            return False
        for alt in alternatives:
            alt_lower = alt.strip().lower()
            alt_norm = "".join(ch for ch in alt_lower if ch.isalnum())
            for i in range(editor.count()):
                option = editor.itemText(i).strip().lower()
                option_norm = "".join(ch for ch in option if ch.isalnum())
                if option == alt_lower or option_norm == alt_norm:
                    editor.setCurrentIndex(i)
                    return True
        return False

    def _restore_loaded_values(self) -> int:
        restored = 0
        root = self._tree.invisibleRootItem()
        stack = [root]
        while stack:
            item = stack.pop()
            for i in range(item.childCount()):
                stack.append(item.child(i))

            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict) or "setting" not in data:
                continue

            setting = data["setting"]
            original = self._original_values.get(setting.token, {})
            editor = self._tree.itemWidget(item, 2)

            if isinstance(editor, QtWidgets.QComboBox):
                desired = original.get("option_label")
                if desired is None:
                    desired = original.get("value")
                if desired is None:
                    continue
                if self._set_combo_to_text(editor, desired):
                    self._store_current_text(item, editor.currentText())
                    restored += 1
                continue

            if isinstance(editor, QtWidgets.QLineEdit):
                desired = original.get("value")
                if desired is None:
                    continue
                editor.setText(desired)
                self._store_current_text(item, desired)
                restored += 1

        self._refresh_dirty_state()
        return restored

    def _apply_preset(self, name: str) -> None:
        if name == "None":
            restored = self._restore_loaded_values()
            if restored == 0:
                self._set_status("Preset cleared. No loaded values needed restoring.")
            else:
                self._set_status("Preset cleared. Restored loaded values.")
            return
        preset = self._presets.get(name)
        if not preset:
            return

        preset_map = {k.strip().lower(): v for k, v in preset.items()}

        def find_desired(key: str) -> str | None:
            k = key.strip().lower()
            if k in preset_map:
                return preset_map[k]
            for preset_key, value in preset_map.items():
                if k.startswith(preset_key):
                    return value
            return None
        root = self._tree.invisibleRootItem()
        stack = [root]
        applied = 0
        while stack:
            item = stack.pop()
            for i in range(item.childCount()):
                stack.append(item.child(i))

            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            alias_text = item.text(0).strip()
            if isinstance(data, dict) and data.get("children"):
                desired = find_desired(alias_text)
                if not desired:
                    continue
                for child in data["children"]:
                    self._apply_preset_to_item(child, desired)
                    applied += 1
                continue
            if not isinstance(data, dict) or "setting" not in data:
                continue
            setting = data["setting"]
            question_text = setting.question.strip()
            desired = find_desired(alias_text) or find_desired(question_text)
            if not desired:
                continue
            if self._apply_preset_to_item(item, desired):
                applied += 1

        if applied == 0:
            self._set_status(f"Preset '{name}' made no changes.")
            return
        self._refresh_dirty_state()

    def _apply_preset_to_item(self, item: QtWidgets.QTreeWidgetItem, desired: str) -> bool:
        editor = self._tree.itemWidget(item, 2)
        if isinstance(editor, QtWidgets.QComboBox):
            if not self._set_combo_to_text(editor, desired):
                return False
            self._store_current_text(item, editor.currentText())
            return True
        if isinstance(editor, QtWidgets.QLineEdit):
            clean = self._clean_value_text(desired)
            editor.setText(clean)
            self._store_current_text(item, clean)
            return True
        return False

    def _has_unsaved_changes(self) -> bool:
        root = self._tree.invisibleRootItem()
        stack = [root]
        while stack:
            item = stack.pop()
            for i in range(item.childCount()):
                stack.append(item.child(i))

            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict) or "setting" not in data:
                continue

            setting = data["setting"]
            original = self._original_values.get(setting.token, {})
            editor = self._tree.itemWidget(item, 2)

            if isinstance(editor, QtWidgets.QComboBox):
                current = editor.currentText()
                baseline = original.get("option_label")
                if baseline is None:
                    baseline = original.get("value")
                if baseline != current:
                    return True
                continue

            if isinstance(editor, QtWidgets.QLineEdit):
                if original.get("value") != editor.text():
                    return True

        return False

    def _refresh_dirty_state(self) -> None:
        self._dirty = self._has_unsaved_changes()
        self._save_button.setEnabled(self._dirty)
        self._reset_all_button.setEnabled(self._tree.topLevelItemCount() > 0)

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._save_button.setEnabled(True)
        self._reset_all_button.setEnabled(self._tree.topLevelItemCount() > 0)

    def _save_to_file(self) -> None:
        path = Path(self._path_edit.text())
        if not path.exists():
            QtWidgets.QMessageBox.critical(self, "File not found", f"Cannot find: {path}")
            return

        updates: dict[str, dict[str, str]] = {}
        root = self._tree.invisibleRootItem()
        stack = [root]
        while stack:
            item = stack.pop()
            for i in range(item.childCount()):
                stack.append(item.child(i))

            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict) or "setting" not in data:
                continue
            setting = data["setting"]

            editor = self._tree.itemWidget(item, 2)
            if isinstance(editor, QtWidgets.QComboBox):
                current = editor.currentText()
                if setting.options:
                    original = self._original_values.get(setting.token, {}).get("option_label")
                    if original != current:
                        updates[setting.token] = {"option_label": current}
                else:
                    original = self._original_values.get(setting.token, {}).get("value")
                    if original != current:
                        updates[setting.token] = {
                            "value": self._format_value(setting.token, current)
                        }
            elif isinstance(editor, QtWidgets.QLineEdit):
                current = editor.text()
                original = self._original_values.get(setting.token, {}).get("value")
                if original != current:
                    updates[setting.token] = {
                        "value": self._format_value(setting.token, current)
                    }

        if not updates:
            self._set_status("No changes to save.")
            return

        self._pending_updates = updates
        preview_lines = []
        for token, update in updates.items():
            name = self._token_to_name.get(token, token)
            if "option_label" in update:
                new_val = update["option_label"]
                old_val = self._original_values.get(token, {}).get("option_label", "")
                preview_lines.append((name, f"{name}: {old_val} -> {new_val}"))
            elif "value" in update:
                new_val = update["value"]
                old_val = self._original_values.get(token, {}).get("value", "")
                preview_lines.append((name, f"{name}: {old_val} -> {new_val}"))
        preview_lines.sort(key=lambda x: x[0].lower())
        preview_text = "\n".join(line for _, line in preview_lines)

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Confirm Save")
        dialog_layout = QtWidgets.QVBoxLayout(dialog)
        dialog_layout.setContentsMargins(10, 10, 10, 10)

        dialog_layout.addWidget(
            QtWidgets.QLabel("Apply the following changes?")
        )

        preview = QtWidgets.QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(preview_text)
        preview.setMinimumHeight(200)
        dialog_layout.addWidget(preview)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Yes
            | QtWidgets.QDialogButtonBox.StandardButton.No
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        try:
            backup_path = path.with_suffix(path.suffix + ".bak")
            backup_path.write_text(self._original_text, encoding="utf-8")
            nv.update_nvram_file(path, updates)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save error", str(exc))
            return

        for token, update in updates.items():
            normalized = {}
            if "value" in update:
                normalized["value"] = self._clean_value_text(update["value"])
            if "option_label" in update:
                normalized["option_label"] = update["option_label"]
            self._original_values.setdefault(token, {}).update(normalized)
        self._original_text = path.read_text(encoding="utf-8", errors="replace")

        self._dirty = False
        self._save_button.setEnabled(False)
        self._reset_all_button.setEnabled(True)
        self._set_status(f"Saved changes to {path}")

    def _reset_all_defaults(self) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            "Reset All",
            "Reset all settings to BIOS defaults?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        root = self._tree.invisibleRootItem()
        stack = [root]
        while stack:
            item = stack.pop()
            for i in range(item.childCount()):
                stack.append(item.child(i))
            self._apply_default(item)

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            self._filter_item_recursive(item, query)

    def _filter_item_recursive(self, item: QtWidgets.QTreeWidgetItem, query: str) -> bool:
        text_alias = (item.text(0) or "").lower()
        text_token = (item.text(1) or "").lower()
        stored_current = item.data(2, QtCore.Qt.ItemDataRole.UserRole)
        text_current = ((stored_current or item.text(2)) or "").lower()
        matches_self = (not query) or (query in text_alias) or (query in text_current)
        if query and (query in text_token):
            matches_self = True

        any_child_match = False
        for i in range(item.childCount()):
            child = item.child(i)
            child_match = self._filter_item_recursive(child, query)
            any_child_match = any_child_match or child_match

        visible = matches_self or any_child_match
        item.setHidden(not visible)
        return visible


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    reply = QtWidgets.QMessageBox.question(
        None,
        "Run Export",
        "Run Export NVRAM before opening the editor?",
        QtWidgets.QMessageBox.StandardButton.Yes
        | QtWidgets.QMessageBox.StandardButton.No,
    )
    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
        if not NVRAMWindow.run_export():
            sys.exit(1)
    window = NVRAMWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
