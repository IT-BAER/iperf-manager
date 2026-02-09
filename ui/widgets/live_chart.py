# -*- coding: utf-8 -*-
"""Real-time chart widget using pyqtgraph for iperf3 live metrics.

Four stacked subplots:
  1. Total Up / Down / Sum (Mbps)
  2. Per-agent Up / Down (Mbps)
  3. Per-agent UDP Jitter (ms)
  4. Per-agent UDP Loss (%)

Designed for streaming 8000+ data points per series efficiently.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout

import pyqtgraph as pg

from ui.theme.colors import (
    CHART_COLORS, BASE, SURFACE1, TEXT, SUBTEXT1,
    OVERLAY0, THRESHOLD_LINE, GREEN, RED,
    LATTE_BASE, LATTE_SURFACE1, LATTE_TEXT, LATTE_SUBTEXT1,
    LATTE_OVERLAY1,
)

# ── Constants ─────────────────────────────────────────────────────────
MAX_POINTS = 8000
DEFAULT_MARKERS = ["o", "x", "t", "star", "s", "d", "p", "+", "t1", "t2", "t3"]

# pyqtgraph symbol mapping (Qt symbols differ from matplotlib)
_PG_SYMBOLS = ["o", "x", "t", "star", "s", "d", "p", "+", "t1", "t2", "t3"]


class _TimeAxisItem(pg.AxisItem):
    """X-axis that displays epoch timestamps as HH:MM:SS."""

    def tickStrings(self, values, scale, spacing):
        result = []
        for v in values:
            try:
                result.append(time.strftime("%H:%M:%S", time.localtime(v)))
            except (OSError, OverflowError, ValueError):
                result.append("")
        return result


class _SmartYAxisItem(pg.AxisItem):
    """Y-axis that dynamically thins out tick labels to prevent overlap."""

    def tickStrings(self, values, scale, spacing):
        strings = super().tickStrings(values, scale, spacing)
        if len(strings) <= 2:
            return strings
        try:
            height = self.boundingRect().height()
        except Exception:
            return strings
        if height <= 0:
            return strings
        max_labels = max(2, int(height / 24))
        if len(strings) <= max_labels:
            return strings
        step = max(2, round(len(strings) / max_labels))
        return [s if i % step == 0 else '' for i, s in enumerate(strings)]


class LiveChartWidget(QWidget):
    """Four-subplot real-time chart for iperf3 metrics."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._agents: List[str] = []
        self._series: Dict[str, dict] = {}
        self._total = {"ts": deque(maxlen=MAX_POINTS),
                       "up": deque(maxlen=MAX_POINTS),
                       "dn": deque(maxlen=MAX_POINTS)}

        # Visibility flags
        self._show_total = True
        self._show_agents = True
        self._show_jitter = True
        self._show_loss = True

        # Time window (seconds); -1 = show all
        self._time_window: int = 60

        # Threshold lines
        self._thr_sum_mbps: float = 0.0
        self._thr_jitter_ms: float = 0.0
        self._thr_loss_pct: float = 0.0

        # Plot curves cache: agent_name -> {up: PlotDataItem, dn: PlotDataItem, ...}
        self._curves: Dict[str, dict] = {}
        self._total_curves: dict = {}
        self._threshold_lines: dict = {}

        self._is_dark = True
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Global pyqtgraph config
        pg.setConfigOptions(antialias=False, useOpenGL=False)

        self._graphics = pg.GraphicsLayoutWidget()
        self._graphics.setBackground(BASE)
        layout.addWidget(self._graphics)

        # Shared time axis style
        axis_pen = pg.mkPen(color=OVERLAY0, width=1)
        grid_pen = pg.mkPen(color=SURFACE1, width=1, style=Qt.PenStyle.DotLine)
        label_style = {"color": SUBTEXT1, "font-size": "11px"}

        def _make_plot(title: str, row: int, y_label: str) -> pg.PlotItem:
            ax_bottom = _TimeAxisItem(orientation="bottom")
            ax_bottom.setPen(axis_pen)
            ax_bottom.setTextPen(pg.mkPen(SUBTEXT1))
            ax_bottom.enableAutoSIPrefix(False)

            ax_left = _SmartYAxisItem(orientation="left")
            ax_left.setPen(axis_pen)
            ax_left.setTextPen(pg.mkPen(SUBTEXT1))

            p = self._graphics.addPlot(row=row, col=0,
                                       axisItems={"bottom": ax_bottom, "left": ax_left})
            p.setTitle(title, color=TEXT, size="12px")
            p.getAxis("left").setLabel(y_label, **label_style)
            p.getAxis("left").setWidth(55)
            p.getAxis("left").setStyle(tickTextOffset=8)
            p.getAxis("left").setTickFont(QFont("Segoe UI", 9))
            p.getAxis("bottom").setLabel("", **label_style)
            p.showGrid(x=True, y=True, alpha=0.15)
            p.setDownsampling(mode="peak")
            p.setClipToView(True)
            p.addLegend(offset=(10, 10), labelTextColor=TEXT, labelTextSize="10px",
                        brush=pg.mkBrush(BASE + "cc"))
            return p

        self._plot_total = _make_plot("Total Up/Down (Mbps)", 0, "Mbps")
        self._plot_agents = _make_plot("Per-agent Up/Down", 1, "Mbps")
        self._plot_jitter = _make_plot("UDP Jitter", 2, "ms")
        self._plot_loss = _make_plot("UDP Loss", 3, "%")

        # Row spacing between subplots
        self._graphics.ci.layout.setSpacing(12)

        # Link X-axes
        self._plot_agents.setXLink(self._plot_total)
        self._plot_jitter.setXLink(self._plot_total)
        self._plot_loss.setXLink(self._plot_total)

        # Pre-create total curves
        self._total_curves["up"] = self._plot_total.plot(
            pen=pg.mkPen(CHART_COLORS[0], width=2), name="Total UP")
        self._total_curves["dn"] = self._plot_total.plot(
            pen=pg.mkPen(CHART_COLORS[1], width=2), name="Total DOWN")
        self._total_curves["sum"] = self._plot_total.plot(
            pen=pg.mkPen(OVERLAY0, width=1, style=Qt.PenStyle.DashLine),
            name="Sum (UP+DOWN)")

        self._apply_visibility()

    # ── Public API ────────────────────────────────────────────────────

    def setup_agents(self, names: List[str]):
        """Initialize series storage and curves for a new set of agents."""
        self.clear_all()
        self._agents = list(names)

        for i, name in enumerate(names):
            color = CHART_COLORS[i % len(CHART_COLORS)]
            symbol = _PG_SYMBOLS[i % len(_PG_SYMBOLS)]

            self._series[name] = {
                "ts":   deque(maxlen=MAX_POINTS),
                "up":   deque(maxlen=MAX_POINTS),
                "dn":   deque(maxlen=MAX_POINTS),
                "jit":  deque(maxlen=MAX_POINTS),
                "loss": deque(maxlen=MAX_POINTS),
            }

            up_pen = pg.mkPen(color=color, width=1.5)
            dn_pen = pg.mkPen(color=color, width=1.5, style=Qt.PenStyle.DashLine)

            self._curves[name] = {
                "up": self._plot_agents.plot(pen=up_pen, name=f"{name} up"),
                "dn": self._plot_agents.plot(pen=dn_pen, name=f"{name} dn"),
                "jit": self._plot_jitter.plot(
                    pen=pg.mkPen(color=color, width=1.5), name=f"{name}"),
                "loss": self._plot_loss.plot(
                    pen=None,
                    symbol=symbol, symbolSize=4,
                    symbolBrush=pg.mkBrush(color),
                    symbolPen=None,
                    name=f"{name}"),
            }

    def update_data(self,
                    series: Dict[str, dict],
                    total: dict):
        """Push new data points and redraw curves.

        Args:
            series: {agent_name: {ts, up, dn, jit, loss}} - deque-like objects
            total:  {ts, up, dn} - deque-like objects
        """
        now = time.time()
        cutoff = now - self._time_window if self._time_window > 0 else 0

        # Update total
        if total and self._show_total:
            ts_arr = np.array(total.get("ts", []), dtype=np.float64)
            if len(ts_arr) > 0:
                if cutoff > 0:
                    mask = ts_arr >= cutoff
                    ts_arr = ts_arr[mask]
                    up_arr = np.array(total.get("up", []), dtype=np.float64)[mask]
                    dn_arr = np.array(total.get("dn", []), dtype=np.float64)[mask]
                else:
                    up_arr = np.array(total.get("up", []), dtype=np.float64)
                    dn_arr = np.array(total.get("dn", []), dtype=np.float64)

                self._total_curves["up"].setData(ts_arr, up_arr)
                self._total_curves["dn"].setData(ts_arr, dn_arr)
                self._total_curves["sum"].setData(ts_arr, up_arr + dn_arr)
        else:
            self._total_curves["up"].setData([], [])
            self._total_curves["dn"].setData([], [])
            self._total_curves["sum"].setData([], [])

        # Update threshold line for sum
        self._update_threshold_line("sum", self._plot_total, self._thr_sum_mbps)

        # Update per-agent series
        for name in self._agents:
            s = series.get(name)
            curves = self._curves.get(name)
            if s is None or curves is None:
                continue

            ts_arr = np.array(s.get("ts", []), dtype=np.float64)
            if len(ts_arr) == 0:
                for key in ("up", "dn", "jit", "loss"):
                    curves[key].setData([], [])
                continue

            if cutoff > 0:
                mask = ts_arr >= cutoff
                ts_arr = ts_arr[mask]
            else:
                mask = np.ones(len(ts_arr), dtype=bool)

            if self._show_agents:
                up_arr = np.array(s.get("up", []), dtype=np.float64)[mask]
                dn_arr = np.array(s.get("dn", []), dtype=np.float64)[mask]
                curves["up"].setData(ts_arr, up_arr)
                curves["dn"].setData(ts_arr, dn_arr)
            else:
                curves["up"].setData([], [])
                curves["dn"].setData([], [])

            if self._show_jitter:
                jit_arr = np.array(s.get("jit", []), dtype=np.float64)[mask]
                curves["jit"].setData(ts_arr, jit_arr)
            else:
                curves["jit"].setData([], [])

            if self._show_loss:
                los_arr = np.array(s.get("loss", []), dtype=np.float64)[mask]
                curves["loss"].setData(ts_arr, los_arr)
            else:
                curves["loss"].setData([], [])

        # Update threshold lines for jitter/loss
        self._update_threshold_line("jit", self._plot_jitter, self._thr_jitter_ms)
        self._update_threshold_line("loss", self._plot_loss, self._thr_loss_pct)

    def set_time_window(self, seconds: int):
        """Set the rolling time window in seconds. -1 = show all."""
        self._time_window = seconds

    def set_visible(self, total: bool, agents: bool, jitter: bool, loss: bool):
        """Toggle visibility of each subplot."""
        self._show_total = total
        self._show_agents = agents
        self._show_jitter = jitter
        self._show_loss = loss
        self._apply_visibility()

    def set_threshold(self, sum_mbps: float = 0.0,
                      jitter_ms: float = 0.0,
                      loss_pct: float = 0.0):
        """Set threshold values. 0 = disabled."""
        self._thr_sum_mbps = sum_mbps
        self._thr_jitter_ms = jitter_ms
        self._thr_loss_pct = loss_pct

    def set_theme(self, is_dark: bool):
        """Switch chart colors between dark and light theme."""
        self._is_dark = is_dark
        if is_dark:
            bg, text_c, sub_c, axis_c, grid_c = BASE, TEXT, SUBTEXT1, OVERLAY0, SURFACE1
        else:
            bg, text_c, sub_c, axis_c, grid_c = LATTE_BASE, LATTE_TEXT, LATTE_SUBTEXT1, LATTE_OVERLAY1, LATTE_SURFACE1

        self._graphics.setBackground(bg)
        axis_pen = pg.mkPen(color=axis_c, width=1)
        text_pen = pg.mkPen(sub_c)
        label_style = {"color": sub_c, "font-size": "11px"}

        for p in (self._plot_total, self._plot_agents, self._plot_jitter, self._plot_loss):
            p.setTitle(p.titleLabel.text, color=text_c, size="12px")
            for side in ("left", "bottom"):
                ax = p.getAxis(side)
                ax.setPen(axis_pen)
                ax.setTextPen(text_pen)
            legend = p.legend
            if legend is not None:
                legend.setLabelTextColor(text_c)
                legend.setBrush(pg.mkBrush(bg + "cc"))

    def clear_all(self):
        """Remove all series data and curves."""
        self._agents.clear()
        self._series.clear()
        self._total["ts"].clear()
        self._total["up"].clear()
        self._total["dn"].clear()

        # Clear total curves
        for c in self._total_curves.values():
            c.setData([], [])

        # Remove agent curves from plots
        for name, curves in self._curves.items():
            for key, item in curves.items():
                plot = item.parentItem()
                if plot is not None:
                    try:
                        plot.removeItem(item)
                    except Exception:
                        pass
        self._curves.clear()

        # Remove threshold lines
        for key, line in self._threshold_lines.items():
            try:
                line.parentItem().removeItem(line)
            except Exception:
                pass
        self._threshold_lines.clear()

        # Clear legends
        for p in (self._plot_agents, self._plot_jitter, self._plot_loss):
            legend = p.legend
            if legend is not None:
                legend.clear()

    # ── Internal ──────────────────────────────────────────────────────

    def _apply_visibility(self):
        self._plot_total.setVisible(self._show_total)
        self._plot_agents.setVisible(self._show_agents)
        self._plot_jitter.setVisible(self._show_jitter)
        self._plot_loss.setVisible(self._show_loss)

    def _update_threshold_line(self, key: str, plot: pg.PlotItem, value: float):
        """Add or update a horizontal threshold line."""
        if value > 0:
            if key not in self._threshold_lines:
                line = pg.InfiniteLine(
                    pos=value, angle=0,
                    pen=pg.mkPen(THRESHOLD_LINE, width=1.5, style=Qt.PenStyle.DashLine),
                    label=f"thr={value}",
                    labelOpts={"color": THRESHOLD_LINE, "position": 0.95},
                )
                plot.addItem(line)
                self._threshold_lines[key] = line
            else:
                self._threshold_lines[key].setPos(value)
        else:
            if key in self._threshold_lines:
                try:
                    plot.removeItem(self._threshold_lines[key])
                except Exception:
                    pass
                del self._threshold_lines[key]
