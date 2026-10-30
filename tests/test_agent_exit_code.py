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


class ClientLogfileTest(unittest.TestCase):
    def setUp(self):
        # The agent may still hold the client log open on Windows when cleanup runs.
        self._logdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.environ['AGENT_LOGDIR'] = self._logdir.name
        self.svc = AgentService()
        self.svc.supports_forceflush = False
        self.args = []

        def fake_popen(args, **kw):
            self.args.append(args)
            return subprocess.Popen([sys.executable, '-c', 'pass'],
                                    stdout=kw['stdout'], stderr=kw['stderr'], text=kw['text'])
        self.svc._popen = fake_popen

    def tearDown(self):
        os.environ.pop('AGENT_LOGDIR', None)
        self._logdir.cleanup()

    def _logfile_args(self, extra):
        self.svc._start_client({'target': '127.0.0.1', 'port': 5201, 'duration': 1, 'extra_args': extra})
        return [a for a in self.args[-1] if a.startswith('--logfile')]

    def test_logfile_name_is_placed_in_agent_log_dir(self):
        expected = '--logfile=' + os.path.join(self.svc.LOG_DIR, 'run1.log')
        self.assertEqual(self._logfile_args(['--logfile=run1.log']), [expected])

    def test_logfile_path_outside_log_dir_is_blocked(self):
        for value in ('/etc/crontab', '../escape.log', r'C:\Windows\x.log', '..', ''):
            with self.subTest(value=value):
                self.assertEqual(self._logfile_args([f'--logfile={value}']), [])


if __name__ == '__main__':
    unittest.main()
