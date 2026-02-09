# -*- coding: utf-8 -*-
"""
AgentsPage - Server URL, bind, discover, client table controls.

Corresponds to the "Agents & Servers" tab in the Tkinter dashboard.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QCheckBox, QLabel, QComboBox,
)


class AgentsPage(QWidget):
    """Tab page for server and client agent configuration.

    Signals:
        discover_requested(): User clicked Discover button.
        test_server_requested(): User clicked Test A /status.
        add_client_requested(): User clicked + Add.
        remove_client_requested(): User clicked - Remove.
        clear_clients_requested(): User clicked Clear.
        edit_client_requested(): User clicked Edit Selected.
        server_url_changed(str): Server agent URL changed.
        server_bind_changed(str): Server bind IP changed.
        keep_servers_changed(bool): Keep servers open checkbox toggled.
    """

    discover_requested = Signal()
    test_server_requested = Signal()
    add_client_requested = Signal()
    remove_client_requested = Signal()
    clear_clients_requested = Signal()
    edit_client_requested = Signal()
    server_url_changed = Signal(str)
    server_bind_changed = Signal(str)
    keep_servers_changed = Signal(bool)
    show_log_changed = Signal(bool)
    save_profile_requested = Signal(str)
    load_profile_requested = Signal(str)
    delete_profile_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)

        # Server section
        srv_group = QGroupBox('A (Server)')
        srv_layout = QFormLayout()

        # Server URL row
        url_row = QHBoxLayout()
        self.server_url_edit = QLineEdit('http://A-IP:9001')
        self.server_url_edit.setMinimumWidth(300)
        self.server_url_edit.textChanged.connect(self.server_url_changed.emit)
        url_row.addWidget(self.server_url_edit, 1)
        self.btn_discover = QPushButton('Discover')
        self.btn_discover.clicked.connect(self.discover_requested.emit)
        url_row.addWidget(self.btn_discover)
        self.btn_test_a = QPushButton('Test A /status')
        self.btn_test_a.clicked.connect(self.test_server_requested.emit)
        url_row.addWidget(self.btn_test_a)
        self.chk_keep_servers = QCheckBox('Keep iperf3 servers open')
        self.chk_keep_servers.setChecked(True)
        self.chk_keep_servers.toggled.connect(self.keep_servers_changed.emit)
        url_row.addWidget(self.chk_keep_servers)
        srv_layout.addRow('A(Server) URL', url_row)

        # Server bind row
        self.server_bind_edit = QLineEdit()
        self.server_bind_edit.setMaximumWidth(200)
        self.server_bind_edit.setPlaceholderText('optional')
        self.server_bind_edit.textChanged.connect(self.server_bind_changed.emit)
        srv_layout.addRow('Server Bind IP', self.server_bind_edit)

        # API token row (optional)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText('optional (X-API-Key)')
        self.api_key_edit.setMaximumWidth(260)
        srv_layout.addRow('API Key', self.api_key_edit)

        srv_group.setLayout(srv_layout)
        layout.addWidget(srv_group)

        # Profile row
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel('Profile:'))
        self.combo_profile = QComboBox()
        self.combo_profile.setMinimumWidth(160)
        self.combo_profile.setEditable(True)
        self.combo_profile.setPlaceholderText('Enter profile name...')
        prof_row.addWidget(self.combo_profile)
        self.btn_save_profile = QPushButton('Save')
        self.btn_save_profile.setFixedWidth(60)
        self.btn_save_profile.clicked.connect(self._on_save_profile)
        prof_row.addWidget(self.btn_save_profile)
        self.btn_load_profile = QPushButton('Load')
        self.btn_load_profile.setFixedWidth(60)
        self.btn_load_profile.clicked.connect(self._on_load_profile)
        prof_row.addWidget(self.btn_load_profile)
        self.btn_delete_profile = QPushButton('Delete')
        self.btn_delete_profile.setFixedWidth(70)
        self.btn_delete_profile.clicked.connect(self._on_delete_profile)
        prof_row.addWidget(self.btn_delete_profile)
        prof_row.addStretch()
        layout.addLayout(prof_row)

        # Client controls row
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton('+ Add')
        self.btn_add.clicked.connect(self.add_client_requested.emit)
        btn_row.addWidget(self.btn_add)
        self.btn_remove = QPushButton('- Remove')
        self.btn_remove.clicked.connect(self.remove_client_requested.emit)
        btn_row.addWidget(self.btn_remove)
        self.btn_clear = QPushButton('Clear')
        self.btn_clear.clicked.connect(self.clear_clients_requested.emit)
        btn_row.addWidget(self.btn_clear)
        self.btn_edit = QPushButton('Edit Selected')
        self.btn_edit.clicked.connect(self.edit_client_requested.emit)
        btn_row.addWidget(self.btn_edit)
        self.chk_show_log = QCheckBox('Show Log')
        self.chk_show_log.setChecked(True)
        self.chk_show_log.toggled.connect(self.show_log_changed.emit)
        btn_row.addWidget(self.chk_show_log)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # ── Accessors ──

    def server_url(self) -> str:
        return self.server_url_edit.text().strip()

    def set_server_url(self, url: str):
        self.server_url_edit.setText(url)

    def server_bind(self) -> str:
        return self.server_bind_edit.text().strip()

    def set_server_bind(self, ip: str):
        self.server_bind_edit.setText(ip)

    def keep_servers_open(self) -> bool:
        return self.chk_keep_servers.isChecked()

    def set_keep_servers_open(self, val: bool):
        self.chk_keep_servers.setChecked(val)

    def api_key(self) -> str:
        return self.api_key_edit.text().strip()

    def set_api_key(self, value: str):
        self.api_key_edit.setText(value or '')

    def set_profile_list(self, names: list[str]):
        current = self.combo_profile.currentText()
        self.combo_profile.clear()
        self.combo_profile.addItems(names)
        if current in names:
            self.combo_profile.setCurrentText(current)

    def _on_save_profile(self):
        name = self.combo_profile.currentText().strip()
        if name:
            self.save_profile_requested.emit(name)

    def _on_load_profile(self):
        name = self.combo_profile.currentText().strip()
        if name:
            self.load_profile_requested.emit(name)

    def _on_delete_profile(self):
        name = self.combo_profile.currentText().strip()
        if name:
            self.delete_profile_requested.emit(name)
