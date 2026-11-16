import hashlib
import json
import os
import socket
import ssl
import subprocess
import tempfile
import unittest
from http.client import HTTPSConnection
from unittest import mock

from core.agent_service import AgentService, ensure_agent_cert, find_openssl

_OPENSSL = find_openssl()


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class AgentWithoutOpensslTest(unittest.TestCase):
    """Agents on hosts without the openssl CLI (Windows without Git) still serve HTTPS."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._patch = mock.patch('core.agent_service.find_openssl', return_value=None)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._dir.cleanup()

    def test_agent_serves_https_with_pinnable_certificate(self):
        os.environ['AGENT_LOGDIR'] = self._dir.name
        port = _free_port()
        svc = AgentService(host='127.0.0.1', port=port, api_token='secret', tls_dir=self._dir.name)
        svc.DISCOVER_PORT = _free_port()
        svc.start()
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = HTTPSConnection('127.0.0.1', port, timeout=5, context=ctx)
            conn.request('GET', '/status', headers={'X-API-Key': 'secret'})
            der = conn.sock.getpeercert(binary_form=True)
            resp = conn.getresponse()
            body = json.loads(resp.read())
            conn.close()
        finally:
            svc.stop()
            os.environ.pop('AGENT_LOGDIR', None)
        self.assertEqual(resp.status, 200)
        self.assertTrue(body['tls']['enabled'])
        self.assertEqual(body['tls']['fingerprint'], ':'.join(f'{b:02X}' for b in hashlib.sha256(der).digest()))

    @unittest.skipIf(os.name == 'nt', 'POSIX file modes')
    def test_private_key_is_owner_only(self):
        _cert, key = ensure_agent_cert(self._dir.name)
        self.assertEqual(os.stat(key).st_mode & 0o777, 0o600)

    @unittest.skipUnless(_OPENSSL, 'openssl CLI not available for the independent check')
    def test_openssl_accepts_certificate_signature_and_key(self):
        cert, key = ensure_agent_cert(self._dir.name)
        verify = subprocess.run([_OPENSSL, 'verify', '-CAfile', cert, cert], capture_output=True, text=True)
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        check = subprocess.run([_OPENSSL, 'ec', '-in', key, '-check', '-noout'], capture_output=True, text=True)
        self.assertIn('EC Key valid', check.stdout + check.stderr)
        text = subprocess.run([_OPENSSL, 'x509', '-in', cert, '-noout', '-text'], capture_output=True, text=True).stdout
        self.assertIn('ecdsa-with-SHA256', text)
        self.assertIn('prime256v1', text)


if __name__ == '__main__':
    unittest.main()
