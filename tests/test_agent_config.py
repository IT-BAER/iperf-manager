import json
import os
import tempfile
import unittest
from pathlib import Path

from core.agent_config import merge_config, update_config_file


class MergeConfigTest(unittest.TestCase):
    def test_rerun_keeps_custom_settings_and_applies_only_passed_values(self):
        existing = {'autostart': '5301,5302', 'bind_host': '10.0.0.5', 'port': 9101,
                    'iperf3_path': '/usr/bin/iperf3', 'advertise_ip': '10.0.0.5',
                    'api_token': 'old', 'allow_remote_update': True, 'tls': False}
        merged = merge_config(existing, {'port': None, 'autostart': None, 'api_token': 'new'})
        self.assertEqual(merged, {**existing, 'api_token': 'new'})

    def test_first_install_gets_defaults_with_remote_update_off(self):
        self.assertEqual(merge_config({}, {'api_token': 't'}), {
            'autostart': '5211,5212', 'bind_host': '0.0.0.0', 'port': 9001, 'iperf3_path': 'iperf3',
            'advertise_ip': '', 'api_token': 't', 'allow_remote_update': False,
        })

    def test_update_config_file_reads_bom_file_and_writes_merged_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.json'
            path.write_text(json.dumps({'port': 9101, 'api_token': 'x'}), encoding='utf-8-sig')
            update_config_file(path, {'allow_remote_update': True})
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual((data['port'], data['api_token'], data['allow_remote_update']), (9101, 'x', True))
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
