# -*- coding: utf-8 -*-
"""
TestPage - Test mode, duration, port, protocol, and control buttons.

Corresponds to the "Test & Mode" tab in the Tkinter dashboard.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLabel,
)

from core.constants import TEST_MODES, PROTOCOLS


class TestPage(QWidget):
    """Tab page for iperf3 test parameters and start/stop controls.

    Signals:
        start_requested(): User clicked Start Test.
        stop_requested(): User clicked STOP.
    """

    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)

        # Test parameters group
        params = QGroupBox('Test Parameters')
        form = QFormLayout()

        # Row 1: Mode, Duration, Base Port
        row1 = QHBoxLayout()
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(TEST_MODES)
        self.combo_mode.setCurrentText('bidir')
        row1.addWidget(QLabel('Mode'))
        row1.addWidget(self.combo_mode)

        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(1, 999999)
        self.spin_duration.setValue(30)
        self.spin_duration.setSuffix(' s')
        row1.addWidget(QLabel('Duration'))
        row1.addWidget(self.spin_duration)

        self.spin_base_port = QSpinBox()
        self.spin_base_port.setRange(1024, 65535)
        self.spin_base_port.setValue(5211)
        row1.addWidget(QLabel('Base Port'))
        row1.addWidget(self.spin_base_port)
        row1.addStretch()
        form.addRow(row1)

        # Row 2: Proto, Parallel, Omit
        row2 = QHBoxLayout()
        self.combo_proto = QComboBox()
        self.combo_proto.addItems(PROTOCOLS)
        self.combo_proto.setCurrentText('tcp')
        row2.addWidget(QLabel('Proto'))
        row2.addWidget(self.combo_proto)

        self.spin_parallel = QSpinBox()
        self.spin_parallel.setRange(1, 128)
        self.spin_parallel.setValue(1)
        row2.addWidget(QLabel('Parallel'))
        row2.addWidget(self.spin_parallel)

        self.spin_omit = QSpinBox()
        self.spin_omit.setRange(0, 60)
        self.spin_omit.setValue(1)
        row2.addWidget(QLabel('Omit'))
        row2.addWidget(self.spin_omit)
        self.spin_poll_interval = QDoubleSpinBox()
        self.spin_poll_interval.setRange(0.2, 10.0)
        self.spin_poll_interval.setSingleStep(0.1)
        self.spin_poll_interval.setDecimals(1)
        self.spin_poll_interval.setValue(1.0)
        self.spin_poll_interval.setSuffix(' s')
        row2.addWidget(QLabel('Poll'))
        row2.addWidget(self.spin_poll_interval)
        row2.addStretch()
        form.addRow(row2)

        # Row 3: Bitrate, Length, TCP window
        row3 = QHBoxLayout()
        self.edit_bitrate = QLineEdit()
        self.edit_bitrate.setPlaceholderText('e.g. 100M')
        self.edit_bitrate.setMaximumWidth(120)
        row3.addWidget(QLabel('Bitrate'))
        row3.addWidget(self.edit_bitrate)

        self.edit_length = QLineEdit()
        self.edit_length.setPlaceholderText('e.g. 128K')
        self.edit_length.setMaximumWidth(120)
        row3.addWidget(QLabel('Length'))
        row3.addWidget(self.edit_length)

        self.edit_tcp_window = QLineEdit()
        self.edit_tcp_window.setPlaceholderText('e.g. 256K')
        self.edit_tcp_window.setMaximumWidth(120)
        row3.addWidget(QLabel('TCP window (-w)'))
        row3.addWidget(self.edit_tcp_window)
        row3.addStretch()
        form.addRow(row3)

        params.setLayout(form)
        layout.addWidget(params)

        # Control buttons
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton('Start Test')
        self.btn_start.setMinimumWidth(120)
        self.btn_start.clicked.connect(self.start_requested.emit)
        btn_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton('STOP')
        self.btn_stop.setMinimumWidth(120)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    # ── State control ──

    def set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)

    # ── Accessors ──

    def mode(self) -> str:
        return self.combo_mode.currentText()

    def set_mode(self, mode: str):
        idx = self.combo_mode.findText(mode)
        if idx >= 0:
            self.combo_mode.setCurrentIndex(idx)

    def duration(self) -> int:
        return self.spin_duration.value()

    def set_duration(self, val: int):
        self.spin_duration.setValue(val)

    def base_port(self) -> int:
        return self.spin_base_port.value()

    def set_base_port(self, val: int):
        self.spin_base_port.setValue(val)

    def proto(self) -> str:
        return self.combo_proto.currentText()

    def set_proto(self, val: str):
        idx = self.combo_proto.findText(val)
        if idx >= 0:
            self.combo_proto.setCurrentIndex(idx)

    def parallel(self) -> int:
        return self.spin_parallel.value()

    def set_parallel(self, val: int):
        self.spin_parallel.setValue(val)

    def omit(self) -> int:
        return self.spin_omit.value()

    def set_omit(self, val: int):
        self.spin_omit.setValue(val)

    def poll_interval_sec(self) -> float:
        return float(self.spin_poll_interval.value())

    def set_poll_interval_sec(self, val: float):
        self.spin_poll_interval.setValue(float(val))

    def bitrate(self) -> str:
        return self.edit_bitrate.text().strip()

    def set_bitrate(self, val: str):
        self.edit_bitrate.setText(val)

    def length(self) -> str:
        return self.edit_length.text().strip()

    def set_length(self, val: str):
        self.edit_length.setText(val)

    def tcp_window(self) -> str:
        return self.edit_tcp_window.text().strip()

    def set_tcp_window(self, val: str):
        self.edit_tcp_window.setText(val)
