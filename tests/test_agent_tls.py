import hashlib
import json
import os
import socket
import ssl
import tempfile
import unittest
from http.client import HTTPConnection, HTTPSConnection

from core.agent_service import AgentService, find_openssl


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _fingerprint(der):
    return ':'.join(f'{b:02X}' for b in hashlib.sha256(der).digest())


@unittest.skipUnless(find_openssl(), 'openssl CLI not available')
class AgentTlsTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        os.environ['AGENT_LOGDIR'] = self._dir.name
        self.port = _free_port()
        self.svc = AgentService(host='127.0.0.1', port=self.port, api_token='secret', tls_dir=self._dir.name)
        self.svc.DISCOVER_PORT = _free_port()
        self.svc.start()

    def tearDown(self):
        self.svc.stop()
        os.environ.pop('AGENT_LOGDIR', None)
        self._dir.cleanup()

    def _https_status(self, key):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = HTTPSConnection('127.0.0.1', self.port, timeout=5, context=ctx)
        conn.request('GET', '/status', headers={'X-API-Key': key} if key else {})
        der = conn.sock.getpeercert(binary_form=True)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body, der

    def test_https_status_reports_peer_certificate_fingerprint(self):
        status, body, der = self._https_status('secret')
        self.assertEqual(status, 200)
        tls = json.loads(body)['tls']
        self.assertTrue(tls['enabled'])
        self.assertEqual(tls['fingerprint'], _fingerprint(der))

    def test_https_without_key_is_forbidden(self):
        status, _body, _der = self._https_status('')
        self.assertEqual(status, 403)

    def test_plain_http_still_served_on_same_port(self):
        conn = HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('GET', '/status', headers={'X-API-Key': 'secret'})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 200)

    def test_advertised_base_url_uses_https(self):
        self.assertTrue(self.svc.base_url().startswith('https://'))

    def test_certificate_survives_restart(self):
        _s, _b, first = self._https_status('secret')
        self.svc.stop()
        self.svc = AgentService(host='127.0.0.1', port=self.port, api_token='secret', tls_dir=self._dir.name)
        self.svc.DISCOVER_PORT = _free_port()
        self.svc.start()
        _s, _b, second = self._https_status('secret')
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
