# -*- coding: utf-8 -*-
"""
DashboardWindow - PySide6 main window for the iperf3 Live Dashboard.

Replaces the Tkinter LiveDashboard class with a QMainWindow.
Integrates: 3 tab pages, table+chart+log splitter, 3 QThread workers,
profile auto-load, CSV recording, and report generation.
"""
from __future__ import annotations

import datetime
import json
import time
import webbrowser
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QMainWindow, QMenuBar,
    QMessageBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from core.config_model import TestConfig
from core.constants import DASHBOARD_VERSION, METRIC_COLUMNS
from core.csv_recorder import CsvRecorder
from core.helpers import extract_ip_port

from ui.dialogs.discover_dialog import DiscoverDialog
from ui.dialogs.edit_client_dialog import EditClientDialog
from ui.models.client_table_model import ClientTableModel, COLUMNS
from ui.pages.agents_page import AgentsPage
from ui.pages.test_page import TestPage
from ui.pages.view_page import ViewPage
from ui.widgets.live_chart import LiveChartWidget
from ui.widgets.log_viewer import LogViewer
from ui.widgets.table_view import ClientTableView
from ui.workers.discovery_worker import DiscoveryWorker
from ui.workers.poller_worker import PollerWorker
from ui.workers.test_runner_worker import TestRunnerWorker

# Data directory
_DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
_PROFILE_PATH = _DATA_DIR / 'last_profile.json'
_PROFILES_DIR = _DATA_DIR / 'profiles'


class DashboardWindow(QMainWindow):
    """Main dashboard window integrating all iperf3 UI components."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'iperf3 Live Dashboard v{DASHBOARD_VERSION}')
        self.resize(1400, 900)

        # Theme
        self._is_dark_theme = True

        # State
        self._running = False
        self._test_start_time: float = 0.0
        self._test_duration: int = 0
        self._run_base: str = ''
        self._csv_recorder: Optional[CsvRecorder] = None
        self._discovered_agents: List[dict] = []

        # Per-agent series data (accumulated for chart)
        self._series: Dict[str, dict] = {}
        self._total = {'ts': deque(maxlen=8000),
                       'up': deque(maxlen=8000),
                       'dn': deque(maxlen=8000)}

        # Per-agent min/max tracking
        self._stats: Dict[str, dict] = {}

        # Build UI
        self._model = ClientTableModel(self)
        self._build_ui()

        # Setup workers and threads
        self._setup_workers()

        # Setup redraw timer
        self._redraw_timer = QTimer(self)
        self._redraw_timer.timeout.connect(self._redraw_chart)
        self._redraw_timer.setInterval(200)

        # Status bar timer
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start(1000)

        # Auto-load profile after short delay
        QTimer.singleShot(100, self._auto_load_profile)
        QTimer.singleShot(200, self._refresh_profile_combo)

    # ── UI Construction ────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Tab widget for the 3 pages
        self._tabs = QTabWidget()
        self._agents_page = AgentsPage()
        self._test_page = TestPage()
        self._view_page = ViewPage()
        self._tabs.addTab(self._agents_page, 'Agents && Servers')
        self._tabs.addTab(self._test_page, 'Test && Mode')
        self._tabs.addTab(self._view_page, 'View && Report')
        self._tabs.setMaximumHeight(260)
        main_layout.addWidget(self._tabs)

        # Splitter: table (top) | chart (middle) | log (bottom)
        self._splitter = QSplitter(Qt.Orientation.Vertical)

        self._table_view = ClientTableView(self._model)
        self._table_view.setMinimumHeight(100)
        self._splitter.addWidget(self._table_view)

        self._chart = LiveChartWidget()
        self._splitter.addWidget(self._chart)

        self._log = LogViewer()
        self._splitter.addWidget(self._log)

        # Initial proportions: table 20%, chart 60%, log 20%
        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 6)
        self._splitter.setStretchFactor(2, 2)

        main_layout.addWidget(self._splitter, 1)

        # Connect page signals
        self._connect_signals()

        # Menu bar
        menu = self.menuBar()
        view_menu = menu.addMenu('View')
        self._theme_action = QAction('Switch to Light Theme', self)
        self._theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._theme_action)

        # Status bar
        self.statusBar().showMessage('Ready')

    def _connect_signals(self):
        """Wire up all signals between pages, table, and workers."""
        # Agents page
        self._agents_page.discover_requested.connect(self._on_discover)
        self._agents_page.test_server_requested.connect(self._on_test_server)
        self._agents_page.add_client_requested.connect(self._on_add_client)
        self._agents_page.remove_client_requested.connect(self._on_remove_client)
        self._agents_page.clear_clients_requested.connect(self._on_clear_clients)
        self._agents_page.edit_client_requested.connect(self._on_edit_client)
        self._agents_page.show_log_changed.connect(self._on_show_log_changed)
        self._agents_page.save_profile_requested.connect(self._on_save_named_profile)
        self._agents_page.load_profile_requested.connect(self._on_load_named_profile)
        self._agents_page.delete_profile_requested.connect(self._on_delete_named_profile)

        # Test page
        self._test_page.start_requested.connect(self._on_start_test)
        self._test_page.stop_requested.connect(self._on_stop_test)

        # View page
        self._view_page.visibility_changed.connect(self._apply_chart_visibility)
        self._view_page.window_changed.connect(self._apply_time_window)
        self._view_page.save_report_requested.connect(self._on_save_report)
        self._view_page.redraw_interval_changed.connect(
            lambda ms: self._redraw_timer.setInterval(ms)
        )

    # ── Worker Setup ───────────────────────────────────────────────────

    def _setup_workers(self):
        """Create 3 QThreads and move workers onto them."""
        # Poller
        self._poller_thread = QThread(self)
        self._poller_worker = PollerWorker()
        self._poller_worker.moveToThread(self._poller_thread)
        self._poller_worker.metrics_received.connect(self._on_metrics)
        self._poller_worker.error_occurred.connect(
            lambda msg: self._log.append_log(f'[POLL ERR] {msg}')
        )
        self._poller_thread.start()

        # Test runner
        self._runner_thread = QThread(self)
        self._runner_worker = TestRunnerWorker()
        self._runner_worker.moveToThread(self._runner_thread)
        self._runner_worker.test_started.connect(self._on_test_started)
        self._runner_worker.test_finished.connect(self._on_test_finished)
        self._runner_worker.log_message.connect(
            lambda msg: self._log.append_log(msg)
        )
        self._runner_worker.error_occurred.connect(
            lambda msg: self._log.append_log(f'[ERROR] {msg}')
        )
        self._runner_thread.start()

        # Discovery
        self._disco_thread = QThread(self)
        self._disco_worker = DiscoveryWorker()
        self._disco_worker.moveToThread(self._disco_thread)
        self._disco_worker.agent_found.connect(self._on_agent_found)
        self._disco_worker.discovery_finished.connect(self._on_discovery_finished)
        self._disco_worker.error_occurred.connect(
            lambda msg: self._log.append_log(f'[DISCO ERR] {msg}')
        )
        self._disco_thread.start()

    # ── Profile Load/Save ──────────────────────────────────────────────

    def _auto_load_profile(self):
        """Load last_profile.json on startup."""
        try:
            if _PROFILE_PATH.exists():
                cfg = TestConfig.load_profile(_PROFILE_PATH)
                self._apply_config(cfg)
                self._log.append_log(f'Profile loaded: {_PROFILE_PATH}')
        except Exception as e:
            self._log.append_log(f'Profile load failed: {e}')

    def _apply_config(self, cfg: TestConfig):
        """Apply a TestConfig to the UI."""
        self._agents_page.set_server_url(cfg.server_agent)
        self._agents_page.set_server_bind(cfg.server_bind)
        self._agents_page.set_keep_servers_open(cfg.keep_servers_open)
        self._agents_page.set_api_key(getattr(cfg, 'api_key', ''))
        self._test_page.set_mode(cfg.mode)
        self._test_page.set_duration(cfg.duration_sec)
        self._test_page.set_base_port(cfg.base_port)
        self._test_page.set_proto(cfg.proto)
        self._test_page.set_parallel(cfg.parallel)
        self._test_page.set_omit(cfg.omit)
        self._test_page.set_poll_interval_sec(cfg.poll_interval_sec)
        self._test_page.set_bitrate(cfg.bitrate)
        self._test_page.set_length(cfg.length)
        self._test_page.set_tcp_window(cfg.tcp_window)
        # Load client rows
        client_dicts = [c.to_dict() for c in cfg.clients]
        self._model.load_from_config(client_dicts)

    def _collect_config(self) -> dict:
        """Collect current UI state into a config dict for the test runner."""
        clients = self._model.get_client_configs()
        cfg = {
            'server': {
                'agent': self._agents_page.server_url(),
            },
            'clients': clients,
            'mode': self._test_page.mode(),
            'duration_sec': self._test_page.duration(),
            'base_port': self._test_page.base_port(),
            'proto': self._test_page.proto(),
            'parallel': self._test_page.parallel(),
            'omit': self._test_page.omit(),
            'poll_interval_sec': self._test_page.poll_interval_sec(),
            'keep_servers_open': self._agents_page.keep_servers_open(),
        }
        api_key = self._agents_page.api_key()
        if api_key:
            cfg['api_key'] = api_key
            cfg['server']['api_key'] = api_key
        bind = self._agents_page.server_bind()
        if bind:
            cfg['server']['bind'] = bind
        bitrate = self._test_page.bitrate()
        if bitrate:
            cfg['bitrate'] = bitrate
        length = self._test_page.length()
        if length:
            cfg['length'] = length
        tcp_window = self._test_page.tcp_window()
        if tcp_window:
            cfg['tcp_window'] = tcp_window
        return cfg

    def _save_profile(self):
        """Save current config to last_profile.json."""
        try:
            cfg = self._collect_config()
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _PROFILE_PATH.write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8'
            )
        except Exception as e:
            self._log.append_log(f'Profile save failed: {e}')

    def _list_profiles(self) -> list[str]:
        """List saved profile names."""
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(p.stem for p in _PROFILES_DIR.glob('*.json'))

    def _refresh_profile_combo(self):
        """Update the profile dropdown."""
        self._agents_page.set_profile_list(self._list_profiles())

    def _on_save_named_profile(self, name: str):
        """Save current config as a named profile."""
        try:
            cfg = self._collect_config()
            _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
            path = _PROFILES_DIR / f'{name}.json'
            path.write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8'
            )
            self._log.append_log(f'Profile saved: {name}')
            self._refresh_profile_combo()
        except Exception as e:
            self._log.append_log(f'Profile save failed: {e}')

    def _on_load_named_profile(self, name: str):
        """Load a named profile."""
        path = _PROFILES_DIR / f'{name}.json'
        if not path.exists():
            QMessageBox.warning(self, 'Load Profile', f'Profile "{name}" not found.')
            return
        try:
            cfg = TestConfig.load_profile(path)
            self._apply_config(cfg)
            self._log.append_log(f'Profile loaded: {name}')
        except Exception as e:
            QMessageBox.warning(self, 'Load Profile', f'Failed: {e}')

    def _on_delete_named_profile(self, name: str):
        """Delete a named profile after confirmation."""
        path = _PROFILES_DIR / f'{name}.json'
        if not path.exists():
            QMessageBox.warning(self, 'Delete Profile', f'Profile "{name}" not found.')
            return
        reply = QMessageBox.question(
            self, 'Delete Profile',
            f'Delete profile "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                path.unlink()
                self._log.append_log(f'Profile deleted: {name}')
                self._refresh_profile_combo()
            except Exception as e:
                QMessageBox.warning(self, 'Delete Profile', f'Failed: {e}')

    # ── Agent Discovery ────────────────────────────────────────────────

    def _on_discover(self):
        self._discovered_agents.clear()
        self._log.append_log('Discovery started...')
        # Run discovery on its thread
        QTimer.singleShot(0, self._disco_worker.run_discovery)

    @Slot(dict)
    def _on_agent_found(self, agent: dict):
        self._discovered_agents.append(agent)

    @Slot(int)
    def _on_discovery_finished(self, count: int):
        self._log.append_log(f'Discovery finished: {count} agent(s) found')
        if not self._discovered_agents:
            QMessageBox.information(self, 'Discovery', 'No agents found.')
            return
        dlg = DiscoverDialog(self._discovered_agents, parent=self)
        dlg.server_selected.connect(self._on_server_selected)
        dlg.clients_selected.connect(self._on_clients_selected)
        dlg.exec()

    def _on_server_selected(self, ip: str, port: int):
        url = f'http://{ip}:{port}'
        self._agents_page.set_server_url(url)
        self._log.append_log(f'Server A set to {url}')

    def _on_clients_selected(self, agents: list):
        srv_url = self._agents_page.server_url()
        srv_ip, _ = extract_ip_port(srv_url) if srv_url else ('', 9001)
        for a in agents:
            ip = a.get('ip', '')
            port = a.get('port', 9001)
            name = a.get('name', ip)
            mgmt = a.get('mgmt', ip)
            non_mgmt = a.get('non_mgmt_ips', [])
            # Pick target: use non-mgmt IP if available, else mgmt
            target = non_mgmt[0] if non_mgmt else (srv_ip or 'A.ip')
            agent_url = f'http://{ip}:{port}'
            self._model.add_client(name=name, agent=agent_url, target=target)
        self._log.append_log(f'{len(agents)} client(s) added')

    def _on_test_server(self):
        url = self._agents_page.server_url()
        if not url:
            return
        try:
            import urllib.request
            headers = {}
            api_key = self._agents_page.api_key()
            if api_key:
                headers['X-API-Key'] = api_key
            req = urllib.request.Request(url.rstrip('/') + '/status', headers=headers)
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read().decode('utf-8', 'ignore'))
            QMessageBox.information(
                self, 'A /status', json.dumps(data, indent=2, ensure_ascii=False)
            )
        except Exception as e:
            QMessageBox.warning(self, 'A /status', f'Failed: {e}')

    # ── Client Table Operations ────────────────────────────────────────

    def _on_add_client(self):
        self._model.add_client()

    def _on_remove_client(self):
        rows = sorted(set(idx.row() for idx in self._table_view.selectedIndexes()), reverse=True)
        if rows:
            self._model.remove_rows(rows)

    def _on_clear_clients(self):
        self._model.clear_all()

    def _on_edit_client(self):
        idx = self._table_view.currentIndex()
        if not idx.isValid():
            return
        row = self._model.get_row(idx.row())
        if row is None:
            return
        current = {
            'proto': row.proto,
            'parallel': row.parallel,
            'reverse': row.reverse,
            'bidir': row.bidir,
            'bitrate': row.bitrate,
        }
        dlg = EditClientDialog(row.name, current, row.overrides, parent=self)

        def _on_saved(result: dict):
            # Apply quick fields
            for key in ('proto', 'parallel', 'reverse', 'bidir', 'bitrate'):
                if key in result:
                    col = COLUMNS.index(key)
                    self._model.setData(
                        self._model.index(idx.row(), col),
                        result[key],
                        Qt.ItemDataRole.EditRole,
                    )
            # Apply overrides
            overrides = result.get('overrides', {})
            for k, v in overrides.items():
                self._model.set_override(row.name, k, v)

        dlg.saved.connect(_on_saved)
        dlg.exec()

    def _on_show_log_changed(self, visible: bool):
        self._log.setVisible(visible)

    # ── Theme Toggle ──────────────────────────────────────────────────

    def _toggle_theme(self):
        self._is_dark_theme = not self._is_dark_theme
        name = 'dark' if self._is_dark_theme else 'light'
        try:
            from ui.theme import load_theme
            QApplication.instance().setStyleSheet(load_theme(name))
            self._chart.set_theme(self._is_dark_theme)
            label = 'Switch to Light Theme' if self._is_dark_theme else 'Switch to Dark Theme'
            self._theme_action.setText(label)
        except Exception as e:
            self._log.append_log(f'Theme switch failed: {e}')

    # ── Pre-flight Validation ─────────────────────────────────────────

    def _preflight_check(self, cfg: dict) -> str | None:
        """Validate config before starting test. Returns error message or None."""
        # Schema validation via TestConfig
        tc = TestConfig.from_dict(cfg)
        errors = tc.validate()
        if errors:
            return '\n'.join(errors)

        # Ping agents (parallel, 2s timeout)
        srv_cfg = cfg.get('server', {})
        global_api_key = str(cfg.get('api_key', '')).strip()
        checks: list[tuple[str, str, str]] = []
        srv_url = srv_cfg.get('agent', '')
        if srv_url:
            checks.append((
                'server',
                srv_url,
                str(srv_cfg.get('api_key') or global_api_key).strip(),
            ))
        for c in cfg.get('clients', []):
            checks.append((
                c.get('name') or c.get('agent') or 'client',
                c.get('agent', ''),
                str(c.get('api_key') or global_api_key).strip(),
            ))

        # deduplicate by (url, token) to avoid redundant checks
        dedup = []
        seen = set()
        for label, url, token in checks:
            key = (url, token)
            if not url or key in seen:
                continue
            seen.add(key)
            dedup.append((label, url, token))

        def _ping(check):
            label, url, token = check
            try:
                import urllib.request
                headers = {}
                if token:
                    headers['X-API-Key'] = token
                req = urllib.request.Request(url.rstrip('/') + '/status', headers=headers)
                with urllib.request.urlopen(
                    req, timeout=2
                ) as r:
                    r.read()
                return label, url, None
            except Exception as e:
                return label, url, str(e)

        unreachable = []
        with ThreadPoolExecutor(max_workers=max(1, min(len(dedup), 10))) as ex:
            for label, url, err in ex.map(_ping, dedup):
                if err:
                    unreachable.append(f'  {label}: {url} — {err}')

        if unreachable:
            return ('Agent(s) unreachable:\n' + '\n'.join(unreachable)
                    + '\n\nCheck that agents are running.')

        return None

    # ── Test Start / Stop ──────────────────────────────────────────────

    def _on_start_test(self):
        if self._running:
            return

        cfg = self._collect_config()

        # Pre-flight validation
        error = self._preflight_check(cfg)
        if error:
            QMessageBox.warning(self, 'Pre-flight Check Failed', error)
            return

        clients = cfg.get('clients', [])
        proto = cfg.get('proto', 'tcp')

        # Save profile
        self._save_profile()

        # Reset chart and series data
        self._series.clear()
        self._total['ts'].clear()
        self._total['up'].clear()
        self._total['dn'].clear()
        self._stats.clear()

        names = [c.get('name', f'client_{i}') for i, c in enumerate(clients)]
        self._chart.setup_agents(names)
        for name in names:
            self._series[name] = {
                'ts': deque(maxlen=8000),
                'up': deque(maxlen=8000),
                'dn': deque(maxlen=8000),
                'jit': deque(maxlen=8000),
                'loss': deque(maxlen=8000),
            }
            self._stats[name] = {
                'up_max': 0.0, 'up_min': float('inf'),
                'dn_max': 0.0, 'dn_min': float('inf'),
            }

        # Open CSV recorder
        self._run_base = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self._csv_recorder = CsvRecorder(
            data_dir=_DATA_DIR,
            run_base=self._run_base,
            agent_names=names,
            proto=proto,
            roll_minutes=self._view_page.roll_minutes(),
            zip_rolled=self._view_page.zip_rolled(),
        )
        try:
            csv_path = self._csv_recorder.open()
            self._log.append_log(f'CSV: {csv_path}')
        except Exception as e:
            self._log.append_log(f'CSV open failed: {e}')

        # Configure and start poller
        mode = cfg.get('mode', 'bidir')
        mode_hint = mode if mode in ('up_only', 'down_only') else None
        poll_interval_ms = int(max(0.2, float(cfg.get('poll_interval_sec', 1.0))) * 1000)
        self._poller_worker.configure(cfg, interval_ms=poll_interval_ms)
        self._poller_worker.set_mode_hint(mode_hint)
        self._poller_worker.start_polling()

        # Start test via runner
        self._runner_worker.start_test(cfg)

        # Start redraw timer
        self._redraw_timer.setInterval(self._view_page.redraw_ms())
        self._redraw_timer.start()

        self._test_start_time = time.time()
        self._test_duration = int(cfg.get('duration_sec', 30))
        self._log.append_log(f'Test started: mode={mode}, duration={self._test_duration}s')

    def _on_stop_test(self):
        if not self._running:
            return
        cfg = self._collect_config()
        self._runner_worker.stop_test(cfg)
        self._log.append_log('Stop requested...')

    @Slot()
    def _on_test_started(self):
        self._running = True
        self._test_page.set_running(True)

    @Slot(str)
    def _on_test_finished(self, reason: str):
        self._running = False
        self._test_page.set_running(False)
        self._poller_worker.stop_polling()
        self._redraw_timer.stop()

        # Finalize CSV
        if self._csv_recorder:
            self._csv_recorder.finalize()

        elapsed = time.time() - self._test_start_time if self._test_start_time else 0
        self._log.append_log(
            f'Test finished: {reason} (elapsed={elapsed:.1f}s)'
        )

        # Final chart redraw
        self._redraw_chart()

        # Auto report
        if self._view_page.auto_report():
            self._generate_report(auto_open=self._view_page.open_report())

        # Save profile
        self._save_profile()

    # ── Metrics Processing ─────────────────────────────────────────────

    @Slot(dict)
    def _on_metrics(self, snap: dict):
        """Process a metrics snapshot from PollerWorker."""
        t = snap.get('t', time.time())
        items = snap.get('items', [])
        has_udp = snap.get('has_udp', False)

        total_up = 0.0
        total_dn = 0.0

        for item in items:
            # item: (name, base, up, dn, jit, los, sent_mb, recv_mb)
            name, base, up, dn, jit, los, sent_mb, recv_mb = item
            total_up += up
            total_dn += dn

            # Accumulate series for chart
            s = self._series.get(name)
            if s:
                s['ts'].append(t)
                s['up'].append(up)
                s['dn'].append(dn)
                s['jit'].append(jit)
                s['loss'].append(los)

            # Update min/max stats
            st = self._stats.get(name)
            if st:
                if up > st['up_max']:
                    st['up_max'] = up
                if up > 0 and up < st['up_min']:
                    st['up_min'] = up
                if dn > st['dn_max']:
                    st['dn_max'] = dn
                if dn > 0 and dn < st['dn_min']:
                    st['dn_min'] = dn

            # Update table model
            up_min = st['up_min'] if st and st['up_min'] != float('inf') else 0.0
            dn_min = st['dn_min'] if st and st['dn_min'] != float('inf') else 0.0
            self._model.update_metrics(
                name,
                up_mbps=f'{up:.3f}',
                dn_mbps=f'{dn:.3f}',
                up_max=f'{st["up_max"]:.3f}' if st else '0.000',
                up_min=f'{up_min:.3f}',
                dn_max=f'{st["dn_max"]:.3f}' if st else '0.000',
                dn_min=f'{dn_min:.3f}',
                sent_mb=f'{sent_mb:.3f}',
                recv_mb=f'{recv_mb:.3f}',
                jitter_ms=f'{jit:.3f}',
                loss_pct=f'{los:.3f}',
            )

        # Accumulate totals
        self._total['ts'].append(t)
        self._total['up'].append(total_up)
        self._total['dn'].append(total_dn)

        # CSV recording
        if self._csv_recorder:
            wall = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            row = [f'{t:.3f}', wall, f'{total_up:.3f}', f'{total_dn:.3f}',
                   f'{total_up + total_dn:.3f}']
            for item in items:
                name, base, up, dn, jit, los, sent_mb, recv_mb = item
                row += [f'{up:.3f}', f'{dn:.3f}', f'{jit:.3f}', f'{los:.3f}',
                        f'{sent_mb:.3f}', f'{recv_mb:.3f}']
            self._csv_recorder.append_row(row)
            self._csv_recorder.check_rollover()

        # Check alert thresholds
        self._check_alerts(total_up, total_dn, items)

    def _check_alerts(self, total_up: float, total_dn: float, items: list):
        """Check threshold alerts."""
        thr_sum = self._view_page.threshold_sum_mbps()
        thr_jit = self._view_page.threshold_jitter_ms()
        thr_los = self._view_page.threshold_loss_pct()

        if thr_sum > 0 and (total_up + total_dn) >= thr_sum:
            self.statusBar().showMessage(
                f'ALERT: Sum {total_up + total_dn:.1f} >= {thr_sum:.1f} Mbps'
            )

        for item in items:
            name, _, _, _, jit, los, _, _ = item
            if thr_jit > 0 and jit > thr_jit:
                self._log.append_log(
                    f'[ALERT] {name} jitter {jit:.2f}ms > {thr_jit:.1f}ms'
                )
            if thr_los > 0 and los > thr_los:
                self._log.append_log(
                    f'[ALERT] {name} loss {los:.2f}% > {thr_los:.2f}%'
                )

    # ── Chart Redraw ───────────────────────────────────────────────────

    def _redraw_chart(self):
        """Push accumulated data to the chart widget."""
        self._chart.update_data(self._series, self._total)

    def _apply_chart_visibility(self):
        self._chart.set_visible(
            total=self._view_page.show_total(),
            agents=self._view_page.show_per_agent(),
            jitter=self._view_page.show_udp_jitter(),
            loss=self._view_page.show_udp_loss(),
        )

    def _apply_time_window(self):
        self._chart.set_time_window(self._view_page.window_seconds())

    # ── Report Generation ──────────────────────────────────────────────

    def _on_save_report(self):
        self._generate_report(auto_open=True)

    def _generate_report(self, auto_open: bool = False):
        """Generate HTML report with embedded PNG charts."""
        csv_path = self._csv_recorder.current_path if self._csv_recorder else None
        if not csv_path or not Path(csv_path).exists():
            self._log.append_log('No CSV data for report.')
            return

        try:
            from core.report import generate_report
            html_path = generate_report(
                csv_path,
                dpi=self._view_page.report_dpi(),
            )
            self._log.append_log(f'Report saved: {html_path}')
            if auto_open and html_path:
                webbrowser.open(str(html_path))
        except ImportError:
            self._log.append_log('report.py not found, skipping report generation.')
        except Exception as e:
            self._log.append_log(f'Report generation failed: {e}')

    # ── Status Bar ─────────────────────────────────────────────────────

    def _update_status_bar(self):
        if self._running:
            elapsed = time.time() - self._test_start_time
            elapsed_int = int(elapsed)
            dur = self._test_duration
            em, es = divmod(elapsed_int, 60)
            eh, em = divmod(em, 60)
            dm, ds = divmod(dur, 60)
            dh, dm = divmod(dm, 60)
            pct = min(100, int(elapsed / dur * 100)) if dur > 0 else 0
            total_up = self._total['up'][-1] if self._total['up'] else 0.0
            total_dn = self._total['dn'][-1] if self._total['dn'] else 0.0
            self.statusBar().showMessage(
                f'\u25b6 {eh:02d}:{em:02d}:{es:02d} / {dh:02d}:{dm:02d}:{ds:02d} ({pct}%)  |  '
                f'\u2191 {total_up:.1f}  \u2193 {total_dn:.1f} Mbps'
            )

    # ── Cleanup ────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Save profile and stop all workers on close."""
        self._save_profile()

        # Stop poller
        try:
            self._poller_worker.stop_polling()
        except Exception:
            pass

        # Stop test runner
        try:
            self._runner_worker.stop_test()
        except Exception:
            pass

        # Finalize CSV
        if self._csv_recorder:
            try:
                self._csv_recorder.finalize()
            except Exception:
                pass

        # Quit threads
        for thread in (self._poller_thread, self._runner_thread, self._disco_thread):
            thread.quit()
            thread.wait(2000)

        # Close HTTP pool
        try:
            from core.net_utils import close_pool
            close_pool()
        except Exception:
            pass

        event.accept()
