# -*- coding: utf-8 -*-
"""
core.csv_recorder - Wide-format CSV recording for iperf3 metrics.

Extracted from the dashboard's _open_ui_csv / _csv_append_row / _csv_ensure_rollover.
No UI dependencies.
"""
from __future__ import annotations

import csv
import time
import zipfile
from pathlib import Path
from typing import Any


class CsvRecorder:
    """Records iperf3 metrics to wide-format CSV files.

    Supports automatic rollover and zip compression of old files.
    """

    def __init__(
        self,
        data_dir: str | Path,
        run_base: str,
        agent_names: list[str],
        proto: str = 'tcp',
        roll_minutes: int = 0,
        zip_rolled: bool = True,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.run_base = run_base
        self.agent_names = list(agent_names)
        self.proto = proto
        self.roll_minutes = roll_minutes
        self.zip_rolled = zip_rolled

        self._current_path: str | None = None
        self._open_ts: float | None = None
        self._buffer: list[list[Any]] = []
        self._rolled_files: list[str] = []
        self._part_index: int = 0

    @property
    def current_path(self) -> str | None:
        """Path of the currently open CSV file."""
        return self._current_path

    @property
    def rolled_files(self) -> list[str]:
        """List of paths that were rolled over."""
        return list(self._rolled_files)

    def open(self) -> str:
        """Create and open a new CSV file. Returns the file path."""
        path = self._build_path(self._part_index)
        header = ['ts', 'wall', 'total_up', 'total_dn', 'total_sum']
        for a in self.agent_names:
            header += [f'{a}_up', f'{a}_dn', f'{a}_jit_ms', f'{a}_loss_pct', f'{a}_sent_mb', f'{a}_recv_mb']
        with open(path, 'w', newline='', encoding='utf-8') as fp:
            w = csv.writer(fp)
            w.writerow(['# schema', 'wide_v1', 'units: ts=epoch(s), up/dn(Mbps), jit(ms), loss(%)', 'proto', self.proto])
            w.writerow(header)
        self._current_path = str(path)
        self._open_ts = time.time()
        self._flush_buffer()
        return self._current_path

    def append_row(self, row: list[Any]):
        """Append a single data row to the current CSV."""
        if not self._current_path:
            self._buffer.append(row)
            return
        try:
            with open(self._current_path, 'a', newline='', encoding='utf-8') as fp:
                w = csv.writer(fp)
                w.writerow(row)
        except PermissionError:
            self._buffer.append(row)

    def check_rollover(self) -> bool:
        """Check if rollover is needed and perform it.

        Returns True if a rollover occurred.
        """
        if not self.roll_minutes or not self._current_path or not self._open_ts:
            return False
        if (time.time() - self._open_ts) < self.roll_minutes * 60:
            return False

        old = Path(self._current_path)
        if self.zip_rolled and old.exists():
            zpath = old.with_suffix(old.suffix + '.zip')
            try:
                with zipfile.ZipFile(zpath, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(old, arcname=old.name)
            except Exception:
                pass

        self._rolled_files.append(str(old))
        self._part_index += 1
        self.open()
        return True

    def finalize(self):
        """Flush any buffered rows and close the recorder."""
        self._flush_buffer()

    def _flush_buffer(self):
        """Write buffered rows to the current CSV."""
        if not self._current_path or not self._buffer:
            return
        try:
            with open(self._current_path, 'a', newline='', encoding='utf-8') as fp:
                w = csv.writer(fp)
                for row in self._buffer:
                    w.writerow(row)
            self._buffer.clear()
        except PermissionError:
            pass

    def _build_path(self, part_index: int) -> Path:
        """Build deterministic CSV path for each rollover segment."""
        if part_index <= 0:
            return self.data_dir / f'{self.run_base}_ui.csv'
        return self.data_dir / f'{self.run_base}_ui_p{part_index:03d}.csv'
