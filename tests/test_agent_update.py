import json
import os
import socket
import tempfile
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

from core.agent_service import AgentService
from core.constants import AGENT_VERSION


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class AgentUpdateTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        os.environ['AGENT_LOGDIR'] = self._dir.name
        self.launches = []
        self.svc = None

    def tearDown(self):
        if self.svc:
            self.svc.stop()
        os.environ.pop('AGENT_LOGDIR', None)
        self._dir.cleanup()

    def _start(self, api_token='secret', allow_remote_update=True):
        self.port = _free_port()
        self.svc = AgentService(host='127.0.0.1', port=self.port, api_token=api_token,
                                allow_remote_update=allow_remote_update,
                                update_launcher=lambda: self.launches.append(1))
        self.svc.DISCOVER_PORT = _free_port()
        self.svc.update_state_file = Path(self._dir.name) / 'update-state.json'
        self.svc.start()

    def _request(self, method, path, key='secret'):
        conn = HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request(method, path, headers={'X-API-Key': key} if key else {})
        resp = conn.getresponse()
        body = json.loads(resp.read() or b'{}')
        conn.close()
        return resp.status, body

    def test_status_reports_release_version_and_update_settings(self):
        self._start()
        self.svc.update_state_file.write_text(json.dumps({'state': 'failed', 'error': 'boom'}), encoding='utf-8')
        status, body = self._request('GET', '/status')
        self.assertEqual(status, 200)
        self.assertEqual(body['version'], AGENT_VERSION)
        self.assertIs(body['remote_update'], True)
        self.assertEqual(body['update'], {'state': 'failed', 'error': 'boom'})

    def test_update_refused_unless_opted_in_and_token_set(self):
        for token, allowed in (('secret', False), ('', True)):
            with self.subTest(token=token, allowed=allowed):
                self._start(api_token=token, allow_remote_update=allowed)
                status, body = self._request('POST', '/update', key=token)
                self.svc.stop()
                self.svc = None
                self.assertEqual((status, body), (403, {'error': 'remote update disabled'}))
        self.assertEqual(self.launches, [])

    def test_update_starts_updater_once_and_reports_requested(self):
        self._start()
        status, body = self._request('POST', '/update')
        self.assertEqual((status, body), (202, {'state': 'requested'}))
        self.assertEqual(self.launches, [1])
        _status, st = self._request('GET', '/status')
        self.assertEqual(st['update']['state'], 'requested')

    def test_update_refused_while_another_update_is_pending(self):
        self._start()
        self.assertEqual(self._request('POST', '/update')[0], 202)
        self.assertEqual(self._request('POST', '/update'), (409, {'error': 'update already in progress'}))
        self.assertEqual(self.launches, [1])

    def test_stale_pending_update_does_not_block_a_new_one(self):
        self._start()
        self.svc.update_state_file.write_text(
            json.dumps({'state': 'running', 'started': time.time() - 16 * 60}), encoding='utf-8')
        self.assertEqual(self._request('POST', '/update')[0], 202)

    def test_update_refused_while_a_client_test_runs(self):
        self._start()
        with self.svc.LOCK:
            self.svc.CLIENT_PROCS['k'] = {'proc': mock.Mock(), 'exit_code': None, 'last_json': None}
        self.assertEqual(self._request('POST', '/update'), (409, {'error': 'test running'}))
        self.assertEqual(self.launches, [])


if __name__ == '__main__':
    unittest.main()
