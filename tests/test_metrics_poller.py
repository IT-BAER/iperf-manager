import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ZERO_ON_REQUEST = 3


class _FakeAgent(BaseHTTPRequestHandler):
    hits = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        type(self).hits += 1
        mbps = 0.0 if type(self).hits == ZERO_ON_REQUEST else 100.0
        body = json.dumps({'metrics': [{'key': 'k', 'json': {'interval_mbps': mbps}}]}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MetricsPollerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._state = tempfile.TemporaryDirectory()
        os.environ['IPERF_MANAGER_STATE_DIR'] = cls._state.name
        os.environ['DASHBOARD_AUTH_DISABLE'] = '1'
        import web.app
        cls.app = web.app

    @classmethod
    def tearDownClass(cls):
        cls._state.cleanup()

    def test_stream_continues_after_zero_throughput_interval(self):
        _FakeAgent.hits = 0
        srv = ThreadingHTTPServer(('127.0.0.1', 0), _FakeAgent)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        emits = []
        orig_emit = self.app.socketio.emit
        self.app.socketio.emit = lambda event, data=None, **kw: emits.append((event, data))
        stop = threading.Event()
        cfg = {
            'clients': [{'name': 'c1', 'agent': f'http://127.0.0.1:{srv.server_port}'}],
            'poll_interval_sec': 0.5,
            'mode': 'up_only',
        }
        poller = threading.Thread(target=self.app._metrics_poller, args=(cfg, stop), daemon=True)
        try:
            poller.start()
            # Test is still running: requests 1-2 carry data, 3 is a 0 Mbit/s interval, 4+ carry data again.
            deadline = time.time() + 10
            while _FakeAgent.hits < ZERO_ON_REQUEST + 2 and time.time() < deadline and poller.is_alive():
                time.sleep(0.1)
            self.assertTrue(poller.is_alive(), 'poller exited while the test was still running')
        finally:
            stop.set()
            poller.join(timeout=5)
            srv.shutdown()
            self.app.socketio.emit = orig_emit
        totals = [d['total_up'] for e, d in emits if e == 'metrics']
        self.assertIn(0, totals)
        self.assertEqual(totals[-1], 100.0)


if __name__ == '__main__':
    unittest.main()
