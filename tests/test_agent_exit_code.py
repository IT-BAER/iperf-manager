import os
import subprocess
import sys
import tempfile
import time
import unittest

from core.agent_service import AgentService

# Closes its output before exiting, so stdout EOF arrives while the process is still alive.
FAKE_IPERF3 = (
    "import os, sys, time\n"
    "print('iperf Done.', flush=True)\n"
    "os.close(1); os.close(2)\n"
    "time.sleep(0.5)\n"
    "sys.exit(3)\n"
)


class ClientExitCodeTest(unittest.TestCase):
    def setUp(self):
        self._logdir = tempfile.TemporaryDirectory()
        os.environ['AGENT_LOGDIR'] = self._logdir.name
        self.svc = AgentService()
        self.svc.supports_forceflush = False
        self.svc._popen = lambda args, **kw: subprocess.Popen(
            [sys.executable, '-c', FAKE_IPERF3],
            stdout=kw['stdout'], stderr=kw['stderr'], text=kw['text'],
        )

    def tearDown(self):
        os.environ.pop('AGENT_LOGDIR', None)
        self._logdir.cleanup()

    def test_exit_code_recorded_when_stdout_closes_before_exit(self):
        key = self.svc._start_client({'target': '127.0.0.1', 'port': 5201, 'duration': 1})
        deadline = time.time() + 10
        while time.time() < deadline:
            with self.svc.LOCK:
                info = self.svc.CLIENT_PROCS[key]
                if 'finished_ts' in info:
                    break
            time.sleep(0.05)
        self.assertIn('finished_ts', info)
        self.assertEqual(info['exit_code'], 3)


if __name__ == '__main__':
    unittest.main()
