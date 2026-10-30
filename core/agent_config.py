# -*- coding: utf-8 -*-
"""
core.agent_config - Agent config.json merge used by the installers.

Reruns (manual or remote update) keep every existing setting and change only
the values passed on the installer command line.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    'autostart': '5211,5212',
    'bind_host': '0.0.0.0',
    'port': 9001,
    'iperf3_path': 'iperf3',
    'advertise_ip': '',
    'api_token': '',
    'allow_remote_update': False,
}


def merge_config(existing: dict, overrides: dict) -> dict:
    """Return defaults < existing < overrides; None in overrides means 'not passed'."""
    merged = {**DEFAULTS, **existing}
    merged.update({k: v for k, v in overrides.items() if v is not None})
    return merged


def update_config_file(path, overrides: dict) -> dict:
    """Merge overrides into the config file at path and write it back (mode 600 on POSIX)."""
    path = Path(path)
    try:
        existing = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        existing = {}
    merged = merge_config(existing if isinstance(existing, dict) else {}, overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
    if os.name != 'nt':
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return merged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Merge installer settings into the agent config.json')
    parser.add_argument('config')
    parser.add_argument('--port', type=int)
    parser.add_argument('--autostart')
    parser.add_argument('--iperf3-path')
    parser.add_argument('--remote-update', choices=('yes', 'no'))
    args = parser.parse_args(argv)
    overrides = {
        'port': args.port,
        'autostart': args.autostart,
        'iperf3_path': args.iperf3_path,
        'allow_remote_update': None if args.remote_update is None else args.remote_update == 'yes',
        # Passed through the environment so the key never shows up in a process listing.
        'api_token': os.environ.get('AGENT_CONFIG_API_TOKEN') or None,
    }
    update_config_file(args.config, overrides)
    return 0


if __name__ == '__main__':
    sys.exit(main())
