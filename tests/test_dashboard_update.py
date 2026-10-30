import io
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from core.agent_service import AgentService
from core.constants import AGENT_VERSION


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class DashboardUpdateTest(unittest.TestCase):
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
        self.launches = []
        self.agents = []
        self._orig_state_file = self.app.AGENTS_STATE_FILE
        self.app.AGENTS_STATE_FILE = Path(self._dir.name) / 'agents.json'
        with self.app._agents_lock:
            self.app._agents.clear()
        self.client = self.app.app.test_client()

    def tearDown(self):
        for svc in self.agents:
            svc.stop()
        with self.app._agents_lock:
            self.app._agents.clear()
        self.app.AGENTS_STATE_FILE = self._orig_state_file
        os.environ.pop('AGENT_LOGDIR', None)
        self._dir.cleanup()

    def _add_agent(self, allow_remote_update=True):
        port = _free_port()
        svc = AgentService(host='127.0.0.1', port=port, api_token='secret', advertise_ip='127.0.0.1',
                           allow_remote_update=allow_remote_update,
                           update_launcher=lambda: self.launches.append(1))
        svc.DISCOVER_PORT = _free_port()
        svc.update_state_file = Path(self._dir.name) / f'update-{port}.json'
        svc.start()
        self.agents.append(svc)
        rsp = self.client.post('/api/agents', json={'url': f'http://127.0.0.1:{port}', 'api_key': 'secret'})
        self.assertEqual(rsp.status_code, 201)
        return rsp.get_json()

    def test_agent_list_shows_version_and_update_settings(self):
        agent = self._add_agent()
        details = agent['details']
        self.assertEqual((details['version'], details['remote_update'], details['update']),
                         (AGENT_VERSION, True, {}))

    def test_update_route_starts_the_agent_updater(self):
        agent = self._add_agent()
        rsp = self.client.post(f"/api/agents/{agent['id']}/update")
        self.assertEqual((rsp.status_code, rsp.get_json()), (202, {'state': 'requested'}))
        self.assertEqual(self.launches, [1])

    def test_update_route_passes_agent_refusal_through(self):
        agent = self._add_agent(allow_remote_update=False)
        rsp = self.client.post(f"/api/agents/{agent['id']}/update")
        self.assertEqual((rsp.status_code, rsp.get_json()), (403, {'error': 'remote update disabled'}))
        self.assertEqual(self.launches, [])

    def test_update_route_passes_agent_conflict_through(self):
        agent = self._add_agent()
        self.assertEqual(self.client.post(f"/api/agents/{agent['id']}/update").status_code, 202)
        rsp = self.client.post(f"/api/agents/{agent['id']}/update")
        self.assertEqual((rsp.status_code, rsp.get_json()), (409, {'error': 'update already in progress'}))

    def test_agent_error_answer_is_not_sent_again(self):
        agent = self._add_agent()
        svc = self.agents[-1]

        def fail():
            self.launches.append(1)
            raise RuntimeError('boom')

        svc.update_launcher = fail
        with redirect_stdout(io.StringIO()):
            rsp = self.client.post(f"/api/agents/{agent['id']}/update")
        self.assertEqual((rsp.status_code, rsp.get_json()), (500, {'error': 'updater start failed'}))
        self.assertEqual(self.launches, [1])

    def test_agent_list_refreshes_only_the_requested_agents(self):
        with self.app._agents_lock:
            self.app._agents.update({'a': {'url': 'http://a'}, 'b': {'url': 'http://b'}, 'c': {'url': 'http://c'}})
        with mock.patch.object(self.app, '_refresh_agent') as refresh:
            rsp = self.client.get('/api/agents?refresh_ids=a,c,unknown')
        self.assertEqual(rsp.status_code, 200)
        self.assertEqual(sorted(call.args[0] for call in refresh.call_args_list), ['a', 'c'])

    def test_update_route_unknown_agent(self):
        self.assertEqual(self.client.post('/api/agents/nope/update').status_code, 404)

    def test_update_route_requires_login_when_auth_is_on(self):
        with mock.patch.object(self.app, '_AUTH_DISABLED', False):
            self.assertEqual(self.client.post('/api/agents/nope/update').status_code, 401)


class LatestReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['DASHBOARD_AUTH_DISABLE'] = '1'
        import web.app
        cls.app = web.app

    def setUp(self):
        self.app._latest_release_cache.clear()
        self.client = self.app.app.test_client()

    def _get(self):
        rsp = self.client.get('/api/meta/agent-release')
        self.assertEqual(rsp.status_code, 200)
        return rsp.get_json()['latest']

    def test_latest_release_is_fetched_once_and_cached(self):
        with mock.patch.object(self.app, '_fetch_latest_release_tag', return_value='v1.3.0') as fetch:
            self.assertEqual((self._get(), self._get()), ('1.3.0', '1.3.0'))
        self.assertEqual(fetch.call_count, 1)

    def test_unreachable_github_or_odd_tag_gives_null(self):
        for side_effect in (OSError('blocked'), ['main']):
            with self.subTest(side_effect=side_effect):
                self.app._latest_release_cache.clear()
                with mock.patch.object(self.app, '_fetch_latest_release_tag', side_effect=side_effect):
                    self.assertIsNone(self._get())


if __name__ == '__main__':
    unittest.main()
