import os
import socket
import tempfile
import unittest

from core import net_utils
from core.agent_service import AgentService, find_openssl

WRONG_PIN = ':'.join(['00'] * 32)


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@unittest.skipUnless(find_openssl(), 'openssl CLI not available')
class TlsPinningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        os.environ['AGENT_LOGDIR'] = cls._dir.name
        cls.svc = AgentService(host='127.0.0.1', port=_free_port(), api_token='secret', tls_dir=cls._dir.name)
        cls.svc.DISCOVER_PORT = _free_port()
        cls.svc.start()
        cls.base = f'https://127.0.0.1:{cls.svc.port}'

    @classmethod
    def tearDownClass(cls):
        net_utils.set_tls_pin(cls.base, None)
        cls.svc.stop()
        os.environ.pop('AGENT_LOGDIR', None)
        cls._dir.cleanup()

    def tearDown(self):
        net_utils.set_tls_pin(self.base, None)

    def test_unpinned_https_connect_records_observed_fingerprint(self):
        st = net_utils.http_get_json(self.base, '/status', api_key='secret')
        self.assertIsNotNone(st)
        self.assertEqual(net_utils.observed_tls_fingerprint(self.base), self.svc.tls_fingerprint)

    def test_matching_pin_returns_data(self):
        net_utils.set_tls_pin(self.base, self.svc.tls_fingerprint)
        self.assertIsNotNone(net_utils.http_get_json(self.base, '/status', api_key='secret'))
        rsp = net_utils.http_post_json(self.base, '/client/stop', {}, api_key='secret')
        self.assertEqual(rsp, {'stopped_clients': 0})

    def test_mismatched_pin_blocks_get_and_reports_new_fingerprint(self):
        net_utils.set_tls_pin(self.base, WRONG_PIN)
        self.assertIsNone(net_utils.http_get_json(self.base, '/status', api_key='secret'))
        self.assertEqual(net_utils.observed_tls_fingerprint(self.base), self.svc.tls_fingerprint)

    def test_mismatched_pin_blocks_post_without_fallback(self):
        net_utils.set_tls_pin(self.base, WRONG_PIN)
        with self.assertRaises(net_utils.TlsPinError):
            net_utils.http_post_json(self.base, '/client/stop', {}, api_key='secret')


if __name__ == '__main__':
    unittest.main()
