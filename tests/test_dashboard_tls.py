import json
import os
import socket
import tempfile
import unittest
from pathlib import Path

from core.agent_service import AgentService, find_openssl


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@unittest.skipUnless(find_openssl(), 'openssl CLI not available')
class DashboardTlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._state = tempfile.TemporaryDirectory()
        os.environ.setdefault('IPERF_MANAGER_STATE_DIR', cls._state.name)
        os.environ['DASHBOARD_AUTH_DISABLE'] = '1'
        import web.app
        cls.app = web.app

    @classmethod
    def tearDownClass(cls):
        cls._state.cleanup()

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        os.environ['AGENT_LOGDIR'] = self._dir.name
        self.port = _free_port()
        self.agents = []
        self.svc = self._start_agent('cert-a')
        self._orig_state_file = self.app.AGENTS_STATE_FILE
        self.app.AGENTS_STATE_FILE = Path(self._dir.name) / 'agents.json'
        with self.app._agents_lock:
            self.app._agents.clear()
        self.client = self.app.app.test_client()
        self.http_url = f'http://127.0.0.1:{self.port}'
        self.https_url = f'https://127.0.0.1:{self.port}'

    def tearDown(self):
        for svc in self.agents:
            svc.stop()
        with self.app._agents_lock:
            self.app._agents.clear()
        self.app.AGENTS_STATE_FILE = self._orig_state_file
        os.environ.pop('AGENT_LOGDIR', None)
        self._dir.cleanup()

    def _start_agent(self, cert_subdir, discover_port=None):
        cert_dir = Path(self._dir.name) / cert_subdir
        cert_dir.mkdir(exist_ok=True)
        svc = AgentService(host='127.0.0.1', port=self.port, api_token='secret',
                           advertise_ip='127.0.0.1', tls_dir=str(cert_dir))
        svc.DISCOVER_PORT = discover_port or _free_port()
        svc.start()
        self.agents.append(svc)
        return svc

    def _restart_agent(self, cert_subdir, discover_port=None):
        self.agents.pop().stop()
        return self._start_agent(cert_subdir, discover_port)

    def _agent_list(self):
        rsp = self.client.get('/api/agents?refresh=1')
        self.assertEqual(rsp.status_code, 200)
        return rsp.get_json()

    def test_http_agent_offering_tls_is_upgraded_pinned_and_keeps_its_id(self):
        rsp = self.client.post('/api/agents', json={'url': self.http_url, 'api_key': 'secret'})
        self.assertEqual(rsp.status_code, 201)
        agent = rsp.get_json()
        self.assertEqual(agent['id'], self.app._agent_id(self.http_url))
        self.assertEqual(agent['url'], self.https_url)
        self.assertEqual(agent['status'], 'online')
        self.assertEqual(agent['tls_fingerprint'], self.svc.tls_fingerprint)

        saved = json.loads(self.app.AGENTS_STATE_FILE.read_text(encoding='utf-8'))
        self.assertEqual(saved[0]['id'], agent['id'])
        self.assertEqual(saved[0]['url'], self.https_url)
        self.assertEqual(saved[0]['tls_fingerprint'], self.svc.tls_fingerprint)

        with self.app._agents_lock:
            self.app._agents.clear()
        self.app._load_agents_state()
        [reloaded] = self._agent_list()
        self.assertEqual(reloaded['id'], agent['id'])
        self.assertEqual(reloaded['status'], 'online')

    def test_changed_certificate_blocks_agent_until_new_fingerprint_is_trusted(self):
        agent = self.client.post('/api/agents', json={'url': self.https_url, 'api_key': 'secret'}).get_json()
        self.assertEqual(agent['tls_fingerprint'], self.svc.tls_fingerprint)

        new_svc = self._restart_agent('cert-b')
        [blocked] = self._agent_list()
        self.assertEqual(blocked['status'], 'offline')
        self.assertTrue(blocked['tls_error'])
        self.assertEqual(blocked['tls_new_fingerprint'], new_svc.tls_fingerprint)

        rsp = self.client.patch(f"/api/agents/{agent['id']}",
                                json={'trust_fingerprint': blocked['tls_new_fingerprint']})
        trusted = rsp.get_json()
        self.assertEqual(trusted['status'], 'online')
        self.assertEqual(trusted['tls_fingerprint'], new_svc.tls_fingerprint)
        self.assertFalse(trusted['tls_error'])

    def test_discovered_https_agent_updates_existing_http_entry(self):
        # No key: the dashboard cannot read /status, so the entry stays http:// until discovery.
        agent = self.client.post('/api/agents', json={'url': self.http_url}).get_json()
        self.assertEqual(agent['url'], self.http_url)
        disc_port = _free_port()
        self._restart_agent('cert-a', discover_port=disc_port)
        orig_port = self.app.DISCOVER_PORT
        self.app.DISCOVER_PORT = disc_port
        os.environ['DASHBOARD_DISCOVERY_CIDRS'] = '127.0.0.1'
        try:
            rsp = self.client.post('/api/agents/discover', json={'timeout': 1})
        finally:
            self.app.DISCOVER_PORT = orig_port
            os.environ.pop('DASHBOARD_DISCOVERY_CIDRS', None)
        self.assertEqual(rsp.get_json()['discovered'], 1)
        with self.app._agents_lock:
            entries = list(self.app._agents.values())
        self.assertEqual([(e['id'], e['url']) for e in entries], [(agent['id'], self.https_url)])


if __name__ == '__main__':
    unittest.main()
