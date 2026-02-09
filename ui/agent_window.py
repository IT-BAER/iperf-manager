# -*- coding: utf-8 -*-
"""
AgentWindow - PySide6 GUI for the iperf3 Agent service.

Replaces the Tkinter AgentGUI class with a QMainWindow.
Supports --headless mode (no window, just service).
"""
from __future__ import annotations

import os
import threading
import webbrowser

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFormLayout, QHBoxLayout, QVBoxLayout,
    QLineEdit, QSpinBox, QPushButton, QLabel, QListWidget, QMessageBox,
    QApplication,
)

from core.agent_service import AgentService, load_agent_cfg, save_agent_cfg


class AgentWindow(QMainWindow):
    """Agent service configuration and control window."""

    _start_succeeded = Signal()
    _start_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('iperf3 Agent (UI) v6.0.2')
        self.resize(560, 400)

        self.service: AgentService | None = None
        self._build_ui()
        self._load_config()
        self._setup_timer()
        self._start_succeeded.connect(self._on_start_succeeded)
        self._start_failed.connect(self._on_start_failed)
        # Auto-start after short delay
        QTimer.singleShot(120, self._auto_start)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)

        form = QFormLayout()

        # Bind Host + Port
        host_row = QHBoxLayout()
        self.edit_host = QLineEdit('0.0.0.0')
        self.edit_host.setMaximumWidth(160)
        host_row.addWidget(self.edit_host)
        host_row.addWidget(QLabel('Port'))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(9001)
        host_row.addWidget(self.spin_port)
        host_row.addStretch()
        form.addRow('Bind Host', host_row)

        # Advertise MGMT IP
        adv_row = QHBoxLayout()
        self.edit_adv_ip = QLineEdit(os.environ.get('AGENT_MGMT_IP', ''))
        self.edit_adv_ip.setPlaceholderText('auto-detect')
        self.edit_adv_ip.setMaximumWidth(160)
        adv_row.addWidget(self.edit_adv_ip)
        adv_row.addWidget(QLabel('(Discover/Status에 표시됨)'))
        adv_row.addStretch()
        form.addRow('Advertise MGMT IP', adv_row)

        # iperf3 path
        self.edit_iperf3 = QLineEdit()
        self.edit_iperf3.setPlaceholderText('auto-detect')
        form.addRow('iperf3 경로', self.edit_iperf3)

        # Autostart ports
        self.edit_autostart = QLineEdit('5211,5212')
        form.addRow('Autostart Ports', self.edit_autostart)

        # API Token
        self.edit_api_token = QLineEdit()
        self.edit_api_token.setEchoMode(QLineEdit.Password)
        self.edit_api_token.setPlaceholderText('blank = no auth')
        form.addRow('API Token', self.edit_api_token)

        layout.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton('Start Service')
        self.btn_start.clicked.connect(self.start_service)
        btn_row.addWidget(self.btn_start)
        self.btn_stop = QPushButton('Stop Service')
        self.btn_stop.clicked.connect(self.stop_service)
        btn_row.addWidget(self.btn_stop)
        self.btn_status = QPushButton('Open Status')
        self.btn_status.clicked.connect(self.open_status)
        btn_row.addWidget(self.btn_status)
        self.btn_copy = QPushButton('Copy Base URL')
        self.btn_copy.clicked.connect(self.copy_base_url)
        btn_row.addWidget(self.btn_copy)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Status label
        self.lbl_status = QLabel('Service: stopped')
        self.lbl_status.setStyleSheet('color: #f38ba8; font-weight: bold;')
        layout.addWidget(self.lbl_status)

        # Info listbox
        self.list_info = QListWidget()
        self.list_info.setMaximumHeight(120)
        layout.addWidget(self.list_info, 1)

    def _load_config(self):
        try:
            cfg = load_agent_cfg()
            if cfg.get('bind_host'):
                self.edit_host.setText(cfg['bind_host'])
            if cfg.get('port'):
                self.spin_port.setValue(int(cfg['port']))
            if cfg.get('advertise_ip'):
                self.edit_adv_ip.setText(cfg['advertise_ip'])
            if cfg.get('iperf3_path'):
                self.edit_iperf3.setText(cfg['iperf3_path'])
            if cfg.get('autostart'):
                self.edit_autostart.setText(cfg['autostart'])
            if cfg.get('api_token'):
                self.edit_api_token.setText(cfg['api_token'])
        except Exception:
            pass

    def _ui_cfg(self) -> dict:
        return {
            'bind_host': self.edit_host.text().strip(),
            'port': self.spin_port.value(),
            'advertise_ip': self.edit_adv_ip.text().strip(),
            'iperf3_path': self.edit_iperf3.text().strip(),
            'autostart': self.edit_autostart.text().strip(),
            'api_token': self.edit_api_token.text().strip(),
        }

    def _setup_timer(self):
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)

    def _tick(self):
        if self.service:
            base = self.service.base_url()
            servers = self.service.current_servers()
            log_ok = getattr(self.service, '_log_dir_ok', True)
            if not log_ok:
                self.lbl_status.setText(
                    f'Service: running at {base} (LOG DIR ERR)'
                )
                self.lbl_status.setStyleSheet('color: #fab387; font-weight: bold;')
            else:
                self.lbl_status.setText(
                    f'Service: running at {base} servers={servers or "-"}'
                )
                self.lbl_status.setStyleSheet('color: #a6e3a1; font-weight: bold;')
            self.list_info.clear()
            self.list_info.addItem(f'Base URL: {base}')
            self.list_info.addItem(f'Running Servers: {servers or "None"}')
            if self.service.version_str:
                self.list_info.addItem(f'iperf3: {self.service.version_str}')
            self.list_info.addItem(f'Log Dir: {getattr(self.service, "LOG_DIR", "?")}')
        else:
            self.lbl_status.setText('Service: stopped')
            self.lbl_status.setStyleSheet('color: #f38ba8; font-weight: bold;')

    def _auto_start(self):
        if self.service:
            return
        self._save_and_start()

    def _save_and_start(self):
        try:
            save_agent_cfg(self._ui_cfg())
        except Exception:
            pass
        try:
            ports = [int(p) for p in self.edit_autostart.text().split(',') if p.strip()]
        except Exception:
            ports = []

        # Disable button and show starting status
        self.btn_start.setEnabled(False)
        self.lbl_status.setText('Service: starting...')
        self.lbl_status.setStyleSheet('color: #f9e2af; font-weight: bold;')

        svc = AgentService(
            host=self.edit_host.text().strip(),
            port=self.spin_port.value(),
            iperf3_bin=self.edit_iperf3.text().strip() or 'iperf3',
            autostart_ports=ports,
            advertise_ip=self.edit_adv_ip.text().strip(),
            api_token=self.edit_api_token.text().strip(),
        )

        def _bg_start():
            try:
                svc.start()
                self.service = svc
                self._start_succeeded.emit()
            except Exception as e:
                self._start_failed.emit(str(e))

        threading.Thread(target=_bg_start, daemon=True).start()

    def _on_start_succeeded(self):
        self.btn_start.setEnabled(True)

    def _on_start_failed(self, msg: str):
        self.service = None
        self.btn_start.setEnabled(True)
        self.lbl_status.setText('Service: stopped')
        self.lbl_status.setStyleSheet('color: #f38ba8; font-weight: bold;')
        QMessageBox.critical(self, 'Start Failed', msg)

    def start_service(self):
        if self.service:
            QMessageBox.information(self, 'Info', '이미 실행 중입니다.')
            return
        self._save_and_start()

    def stop_service(self):
        if not self.service:
            return
        try:
            save_agent_cfg(self._ui_cfg())
        except Exception:
            pass
        try:
            self.service.stop()
        finally:
            self.service = None
        QMessageBox.information(self, 'Agent', 'Service stopped')

    def open_status(self):
        if not self.service:
            QMessageBox.warning(self, 'Agent', '먼저 Start Service를 실행하세요.')
            return
        webbrowser.open(self.service.base_url() + '/status')

    def copy_base_url(self):
        if self.service:
            url = self.service.base_url()
        else:
            host = self.edit_adv_ip.text().strip() or self.edit_host.text().strip() or '127.0.0.1'
            url = f'http://{host}:{self.spin_port.value()}'
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(url)
        QMessageBox.information(self, 'Clipboard', f'복사됨: {url}')

    def closeEvent(self, event):
        try:
            save_agent_cfg(self._ui_cfg())
        except Exception:
            pass
        if self.service:
            try:
                self.service.stop()
            except Exception:
                pass
            self.service = None
        event.accept()
