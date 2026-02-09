# -*- coding: utf-8 -*-
"""
ViewPage - Chart visibility, time window, report, performance, alert controls.

Corresponds to the "View & Report" tab in the Tkinter dashboard.
Compact flat layout without GroupBoxes for efficient vertical space usage.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QCheckBox, QComboBox, QSlider, QPushButton,
    QSpinBox, QDoubleSpinBox, QLabel, QFrame,
)

from core.constants import WINDOW_PRESETS


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName('sectionLabel')
    lbl.setFixedWidth(110)
    return lbl


def _hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    f.setFixedHeight(1)
    return f


class ViewPage(QWidget):
    """Tab page for chart visibility, time window, reporting, and thresholds.

    Signals:
        visibility_changed(): Any chart visibility toggle changed.
        window_changed(): Time window selection changed.
        save_report_requested(): User clicked Save Report (HTML).
        redraw_interval_changed(int): Redraw interval ms changed.
    """

    visibility_changed = Signal()
    window_changed = Signal()
    save_report_requested = Signal()
    redraw_interval_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 4)
        layout.setSpacing(4)

        # Row 1: Chart Visibility
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(_section_label('Chart Visibility'))
        self.chk_total = QCheckBox('Total')
        self.chk_total.setChecked(True)
        self.chk_total.toggled.connect(lambda: self.visibility_changed.emit())
        row1.addWidget(self.chk_total)
        self.chk_per_agent = QCheckBox('Per-agent')
        self.chk_per_agent.setChecked(True)
        self.chk_per_agent.toggled.connect(lambda: self.visibility_changed.emit())
        row1.addWidget(self.chk_per_agent)
        self.chk_udp_jitter = QCheckBox('UDP Jitter')
        self.chk_udp_jitter.setChecked(True)
        self.chk_udp_jitter.toggled.connect(lambda: self.visibility_changed.emit())
        row1.addWidget(self.chk_udp_jitter)
        self.chk_udp_loss = QCheckBox('UDP Loss')
        self.chk_udp_loss.setChecked(True)
        self.chk_udp_loss.toggled.connect(lambda: self.visibility_changed.emit())
        row1.addWidget(self.chk_udp_loss)
        row1.addStretch()
        layout.addLayout(row1)
        layout.addWidget(_hsep())

        # Row 2: Time Window
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(_section_label('Time Window'))
        self.combo_window = QComboBox()
        self.combo_window.addItems(list(WINDOW_PRESETS.keys()) + ['custom'])
        self.combo_window.setCurrentText('60s')
        self.combo_window.setFixedWidth(100)
        self.combo_window.currentTextChanged.connect(lambda: self.window_changed.emit())
        row2.addWidget(self.combo_window)
        self.slider_window = QSlider(Qt.Horizontal)
        self.slider_window.setRange(10, 259200)
        self.slider_window.setValue(60)
        self.slider_window.valueChanged.connect(self._on_slider_changed)
        row2.addWidget(self.slider_window, 1)
        self.btn_apply_custom = QPushButton('Apply custom')
        self.btn_apply_custom.setFixedWidth(120)
        self.btn_apply_custom.clicked.connect(self._apply_custom)
        row2.addWidget(self.btn_apply_custom)
        layout.addLayout(row2)
        layout.addWidget(_hsep())

        # Row 3: Report
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(_section_label('Report'))
        self.chk_auto_report = QCheckBox('Auto Report')
        self.chk_auto_report.setChecked(True)
        row3.addWidget(self.chk_auto_report)
        self.chk_open_report = QCheckBox('Open Report')
        self.chk_open_report.setChecked(True)
        row3.addWidget(self.chk_open_report)
        self.btn_save_report = QPushButton('Save Report (HTML)')
        self.btn_save_report.clicked.connect(self.save_report_requested.emit)
        row3.addWidget(self.btn_save_report)
        row3.addWidget(QLabel('DPI'))
        self.spin_rep_dpi = QSpinBox()
        self.spin_rep_dpi.setRange(72, 300)
        self.spin_rep_dpi.setValue(120)
        self.spin_rep_dpi.setFixedWidth(75)
        row3.addWidget(self.spin_rep_dpi)
        row3.addStretch()
        layout.addLayout(row3)
        layout.addWidget(_hsep())

        # Row 4: Performance
        row4 = QHBoxLayout()
        row4.setSpacing(8)
        row4.addWidget(_section_label('Performance'))
        row4.addWidget(QLabel('Redraw'))
        self.spin_redraw_ms = QSpinBox()
        self.spin_redraw_ms.setRange(100, 1000)
        self.spin_redraw_ms.setSingleStep(50)
        self.spin_redraw_ms.setValue(200)
        self.spin_redraw_ms.setFixedWidth(100)
        self.spin_redraw_ms.setSuffix(' ms')
        self.spin_redraw_ms.valueChanged.connect(self.redraw_interval_changed.emit)
        row4.addWidget(self.spin_redraw_ms)
        row4.addWidget(QLabel('Rollover'))
        self.spin_roll_min = QSpinBox()
        self.spin_roll_min.setRange(0, 1440)
        self.spin_roll_min.setValue(0)
        self.spin_roll_min.setFixedWidth(100)
        self.spin_roll_min.setSuffix(' min')
        row4.addWidget(self.spin_roll_min)
        self.chk_zip_rolled = QCheckBox('Zip rolled')
        self.chk_zip_rolled.setChecked(True)
        row4.addWidget(self.chk_zip_rolled)
        row4.addStretch()
        layout.addLayout(row4)
        layout.addWidget(_hsep())

        # Row 5: Alert Thresholds
        row5 = QHBoxLayout()
        row5.setSpacing(8)
        row5.addWidget(_section_label('Alert Thresholds'))
        row5.addWidget(QLabel('Jitter >'))
        self.spin_thr_jitter = QDoubleSpinBox()
        self.spin_thr_jitter.setRange(0, 1000)
        self.spin_thr_jitter.setDecimals(1)
        self.spin_thr_jitter.setValue(0.0)
        self.spin_thr_jitter.setFixedWidth(90)
        self.spin_thr_jitter.setSuffix(' ms')
        row5.addWidget(self.spin_thr_jitter)
        row5.addWidget(QLabel('Loss >'))
        self.spin_thr_loss = QDoubleSpinBox()
        self.spin_thr_loss.setRange(0, 100)
        self.spin_thr_loss.setSingleStep(0.5)
        self.spin_thr_loss.setDecimals(2)
        self.spin_thr_loss.setValue(0.0)
        self.spin_thr_loss.setFixedWidth(95)
        self.spin_thr_loss.setSuffix(' %')
        row5.addWidget(self.spin_thr_loss)
        row5.addWidget(QLabel('Sum >='))
        self.spin_thr_sum = QDoubleSpinBox()
        self.spin_thr_sum.setRange(0, 100000)
        self.spin_thr_sum.setSingleStep(10)
        self.spin_thr_sum.setDecimals(1)
        self.spin_thr_sum.setValue(0.0)
        self.spin_thr_sum.setFixedWidth(120)
        self.spin_thr_sum.setSuffix(' Mbps')
        row5.addWidget(self.spin_thr_sum)
        row5.addStretch()
        layout.addLayout(row5)

        layout.addStretch()

    def _on_slider_changed(self, val: int):
        self.window_changed.emit()

    def _apply_custom(self):
        self.combo_window.setCurrentText('custom')
        self.window_changed.emit()

    # ── Accessors ──

    def window_seconds(self) -> int:
        w = self.combo_window.currentText()
        if w == 'custom':
            return self.slider_window.value()
        return WINDOW_PRESETS.get(w, 60)

    def show_total(self) -> bool:
        return self.chk_total.isChecked()

    def show_per_agent(self) -> bool:
        return self.chk_per_agent.isChecked()

    def show_udp_jitter(self) -> bool:
        return self.chk_udp_jitter.isChecked()

    def show_udp_loss(self) -> bool:
        return self.chk_udp_loss.isChecked()

    def auto_report(self) -> bool:
        return self.chk_auto_report.isChecked()

    def open_report(self) -> bool:
        return self.chk_open_report.isChecked()

    def redraw_ms(self) -> int:
        return self.spin_redraw_ms.value()

    def roll_minutes(self) -> int:
        return self.spin_roll_min.value()

    def zip_rolled(self) -> bool:
        return self.chk_zip_rolled.isChecked()

    def threshold_jitter_ms(self) -> float:
        return self.spin_thr_jitter.value()

    def threshold_loss_pct(self) -> float:
        return self.spin_thr_loss.value()

    def threshold_sum_mbps(self) -> float:
        return self.spin_thr_sum.value()

    def report_dpi(self) -> int:
        return self.spin_rep_dpi.value()
