# -*- coding: utf-8 -*-
"""Edit per-client options dialog.

Provides quick-edit fields for proto/parallel/reverse/bidir/bitrate,
plus advanced overrides: interval, omit, length, window, extra_args.
Validates reverse+bidir cannot both be enabled.
"""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)


class EditClientDialog(QDialog):
    """Modal dialog for editing a single client's options.

    Signals:
        saved(dict): Emitted with the updated fields dict on Save.
            Keys: proto, parallel, reverse, bidir, bitrate,
                  interval, omit, length, window, extra_args
    """

    saved = Signal(dict)

    def __init__(self, name: str, current: Dict[str, Any],
                 overrides: Dict[str, Any] | None = None,
                 parent: QWidget | None = None):
        """
        Args:
            name: Client display name (for title bar).
            current: Current visible column values (proto, parallel, reverse, bidir, bitrate).
            overrides: Advanced per-client overrides (interval, omit, length, window, extra_args).
        """
        super().__init__(parent)
        self.setWindowTitle(f"Edit: {name}")
        self.setMinimumWidth(380)
        self._name = name
        self._current = current
        self._overrides = overrides or {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Quick fields
        form = QFormLayout()

        self._proto = QComboBox()
        self._proto.addItems(["", "tcp", "udp"])
        proto_val = str(self._current.get("proto", "")).strip().lower()
        idx = self._proto.findText(proto_val, Qt.MatchFlag.MatchFixedString)
        self._proto.setCurrentIndex(max(idx, 0))
        form.addRow("Proto (tcp|udp)", self._proto)

        self._parallel = QSpinBox()
        self._parallel.setRange(0, 128)
        self._parallel.setSpecialValueText("")
        par_val = str(self._current.get("parallel", "")).strip()
        try:
            self._parallel.setValue(int(par_val))
        except (ValueError, TypeError):
            self._parallel.setValue(0)
        form.addRow("Parallel (-P)", self._parallel)

        self._reverse = QCheckBox()
        rev_val = str(self._current.get("reverse", "")).strip().lower()
        self._reverse.setChecked(rev_val in ("1", "true", "yes", "on"))
        form.addRow("Reverse (-R)", self._reverse)

        self._bidir = QCheckBox()
        bid_val = str(self._current.get("bidir", "")).strip().lower()
        self._bidir.setChecked(bid_val in ("1", "true", "yes", "on"))
        form.addRow("Bidir (--bidir)", self._bidir)

        self._bitrate = QLineEdit(str(self._current.get("bitrate", "")))
        form.addRow("Bitrate (-b)", self._bitrate)

        layout.addLayout(form)

        # Separator
        sep = QLabel("--- Advanced Overrides ---")
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sep)

        # Advanced fields
        adv_form = QFormLayout()

        self._interval = QLineEdit(str(self._overrides.get("interval", "")))
        adv_form.addRow("Interval (-i)", self._interval)

        self._omit = QLineEdit(str(self._overrides.get("omit", "")))
        adv_form.addRow("Omit (-O)", self._omit)

        self._length = QLineEdit(str(self._overrides.get("length", "")))
        adv_form.addRow("Length (-l)", self._length)

        self._window = QLineEdit(str(self._overrides.get("window", "")))
        adv_form.addRow("Window (-w)", self._window)

        extra = self._overrides.get("extra_args", [])
        self._extra = QLineEdit(" ".join(extra) if isinstance(extra, list) else str(extra))
        adv_form.addRow("Extra args", self._extra)

        layout.addLayout(adv_form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_close = QPushButton("Close")
        btn_save.clicked.connect(self._on_save)
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _on_save(self):
        # Validate reverse + bidir
        if self._reverse.isChecked() and self._bidir.isChecked():
            QMessageBox.warning(
                self, "Validation Error",
                "reverse and bidir cannot both be enabled."
            )
            return

        result: Dict[str, Any] = {}

        # Quick fields
        result["proto"] = self._proto.currentText().strip()
        par_val = self._parallel.value()
        result["parallel"] = str(par_val) if par_val > 0 else ""
        result["reverse"] = "1" if self._reverse.isChecked() else ""
        result["bidir"] = "1" if self._bidir.isChecked() else ""
        result["bitrate"] = self._bitrate.text().strip()

        # Advanced overrides
        overrides: Dict[str, Any] = {}
        if self._interval.text().strip():
            overrides["interval"] = self._interval.text().strip()
        if self._omit.text().strip():
            val = self._omit.text().strip()
            overrides["omit"] = int(val) if val.isdigit() else val
        if self._length.text().strip():
            overrides["length"] = self._length.text().strip()
        if self._window.text().strip():
            overrides["window"] = self._window.text().strip()
        if self._extra.text().strip():
            overrides["extra_args"] = [x for x in self._extra.text().split() if x]
        # Also copy quick fields into overrides for compat
        if result["proto"]:
            overrides["proto"] = result["proto"].lower()
        if result["parallel"]:
            try:
                overrides["parallel"] = int(result["parallel"])
            except ValueError:
                overrides["parallel"] = result["parallel"]
        if self._reverse.isChecked():
            overrides["reverse"] = True
        if self._bidir.isChecked():
            overrides["bidir"] = True

        result["overrides"] = overrides

        self.saved.emit(result)
        self.accept()
