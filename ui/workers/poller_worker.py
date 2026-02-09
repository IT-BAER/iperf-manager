# -*- coding: utf-8 -*-
"""
PollerWorker - QTimer-based metrics polling worker.

Replaces the threading.Thread Poller with QObject+QTimer on a QThread.
Uses net_utils.poll_metrics() for HTTP polling.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from core.net_utils import poll_metrics


class PollerWorker(QObject):
    """Polls agent /metrics endpoints on a QTimer tick.

    Signals:
        metrics_received(dict): Snapshot dict with keys:
            't': float (epoch), 'items': list of tuples, 'has_udp': bool
        error_occurred(str): Error description
    """

    metrics_received = Signal(dict)
    error_occurred = Signal(str)

    # Signals for cross-thread invocation from main thread
    sig_configure = Signal(dict, int)
    sig_start = Signal()
    sig_stop = Signal()
    sig_set_mode_hint = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._cfg: dict | None = None
        self._acc_bytes: dict = {}
        self._mode_hint: str | None = None
        self._running = False

        # Connect internal signals to slots for thread-safe invocation
        self.sig_configure.connect(self._do_configure)
        self.sig_start.connect(self._do_start)
        self.sig_stop.connect(self._do_stop)
        self.sig_set_mode_hint.connect(self._do_set_mode_hint)

    # ── Public API (thread-safe, emit signals) ──

    def configure(self, cfg: dict, interval_ms: int = 1000):
        """Set polling configuration (thread-safe)."""
        self.sig_configure.emit(cfg, interval_ms)

    def set_mode_hint(self, hint: str | None):
        """Update the mode hint (thread-safe)."""
        self.sig_set_mode_hint.emit(hint or '')

    def start_polling(self):
        """Start the QTimer (thread-safe)."""
        self.sig_start.emit()

    def stop_polling(self):
        """Stop the QTimer (thread-safe)."""
        self.sig_stop.emit()

    # ── Slots (run on worker thread) ──

    @Slot(dict, int)
    def _do_configure(self, cfg: dict, interval_ms: int):
        self._cfg = cfg
        self._acc_bytes = {}
        for c in cfg.get('clients', []):
            self._acc_bytes[c['name']] = {'sent': 0.0, 'recv': 0.0, 'last_ts': None}
        self._timer.setInterval(max(200, interval_ms))

    @Slot(str)
    def _do_set_mode_hint(self, hint: str):
        self._mode_hint = hint if hint else None

    @Slot()
    def _do_start(self):
        if self._cfg is None:
            return
        self._running = True
        self._timer.start()

    @Slot()
    def _do_stop(self):
        self._running = False
        self._timer.stop()

    # ── Private ──

    def _poll(self):
        if not self._running or self._cfg is None:
            return
        try:
            t = time.time()
            snap = {'t': t, 'items': [], 'has_udp': False}
            clients = self._cfg.get('clients', [])
            hint = self._mode_hint
            global_api_key = str(self._cfg.get('api_key', '')).strip()

            # Parallel polling of all agents
            def _poll_one(c):
                client_api_key = str(c.get('api_key') or global_api_key).strip() or None
                return c, poll_metrics(c['agent'], mode_hint=hint, api_key=client_api_key)

            if len(clients) > 1:
                with ThreadPoolExecutor(max_workers=min(len(clients), 10)) as ex:
                    results = list(ex.map(_poll_one, clients))
            else:
                results = [_poll_one(c) for c in clients]

            for c, (u, d, ub, db, jit, los) in results:
                if (jit or 0.0) != 0.0 or (los or 0.0) != 0.0:
                    snap['has_udp'] = True
                a = self._acc_bytes.setdefault(
                    c['name'], {'sent': 0.0, 'recv': 0.0, 'last_ts': None}
                )
                last = a['last_ts']
                if ub is not None or db is not None:
                    if ub is not None:
                        a['sent'] += ub / 1_000_000.0
                    if db is not None:
                        a['recv'] += db / 1_000_000.0
                    dt = max(0.2, (t - last) if last is not None else 1.0)
                    if ub is not None:
                        u = (ub * 8.0) / (1_000_000.0 * dt)
                    if db is not None:
                        d = (db * 8.0) / (1_000_000.0 * dt)
                else:
                    if last is not None:
                        dt = max(0.2, t - last)
                        a['sent'] += u * dt / 8.0
                        a['recv'] += d * dt / 8.0
                a['last_ts'] = t
                snap['items'].append((
                    c['name'], c['agent'], u, d,
                    jit or 0.0, los or 0.0,
                    a['sent'], a['recv'],
                ))
            self.metrics_received.emit(snap)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
