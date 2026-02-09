# -*- coding: utf-8 -*-
"""
Integration test: 2 agents + 1 dashboard, full end-to-end verification.

Does NOT modify data/last_profile.json (uses temp files only).
Tests: agent /status, /server/start, /client/start, /metrics,
       dashboard profile save/load, test start/stop, CSV recording.
"""
import sys, os, json, time, threading, tempfile, traceback, shutil
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

# ── Test framework ──
PASS = FAIL = 0
ERRORS = []

def ok(section, name):
    global PASS; PASS += 1
    print(f'  [PASS] {section}: {name}')

def fail(section, name, detail=''):
    global FAIL; FAIL += 1
    msg = f'  [FAIL] {section}: {name}'
    if detail:
        msg += f'\n         {detail}'
    print(msg)
    ERRORS.append(f'{section}: {name} - {detail}')

def section(title):
    print(f'\n{"="*60}\n  {title}\n{"="*60}')


# ═══════════════════════════════════════════════════════════════
#  PHASE 1: Start 2 Agents
# ═══════════════════════════════════════════════════════════════
section('Phase 1: Start 2 Agent Services')

from core.agent_service import AgentService

IPERF3_BIN = str((PROJECT / 'iperf3.exe').resolve())
AGENT_A_PORT = 19001  # server agent
AGENT_B_PORT = 19002  # client agent
print(f'  iperf3: {IPERF3_BIN} (exists={Path(IPERF3_BIN).exists()})')

agent_a = AgentService(
    host='127.0.0.1', port=AGENT_A_PORT,
    iperf3_bin=IPERF3_BIN, advertise_ip='127.0.0.1',
)
agent_b = AgentService(
    host='127.0.0.1', port=AGENT_B_PORT,
    iperf3_bin=IPERF3_BIN, advertise_ip='127.0.0.1',
)

try:
    agent_a.start()
    ok('Phase1', f'Agent A started on port {AGENT_A_PORT}')
except Exception as e:
    fail('Phase1', f'Agent A start', traceback.format_exc())
    print('FATAL: cannot continue without agents')
    sys.exit(1)

try:
    agent_b.start()
    ok('Phase1', f'Agent B started on port {AGENT_B_PORT}')
except Exception as e:
    fail('Phase1', f'Agent B start', traceback.format_exc())
    agent_a.stop()
    sys.exit(1)

time.sleep(0.3)  # let HTTP servers bind


# ═══════════════════════════════════════════════════════════════
#  PHASE 2: Agent REST API tests
# ═══════════════════════════════════════════════════════════════
section('Phase 2: Agent REST API')

import urllib.request

def http_get(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))

def http_post(url, data, timeout=3):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body,
                                headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))

A_URL = f'http://127.0.0.1:{AGENT_A_PORT}'
B_URL = f'http://127.0.0.1:{AGENT_B_PORT}'

# 2a. /status
try:
    st_a = http_get(f'{A_URL}/status')
    assert 'servers' in st_a, f'no servers key: {st_a.keys()}'
    ok('Phase2', 'Agent A /status')
except Exception as e:
    fail('Phase2', 'Agent A /status', str(e))

try:
    st_b = http_get(f'{B_URL}/status')
    assert 'servers' in st_b, f'no servers key: {st_b.keys()}'
    ok('Phase2', 'Agent B /status')
except Exception as e:
    fail('Phase2', 'Agent B /status', str(e))

# 2b. /server/start on Agent A
TEST_PORT = 15211
try:
    resp = http_post(f'{A_URL}/server/start', {'ports': [TEST_PORT]})
    ok('Phase2', f'Agent A /server/start port={TEST_PORT}')
except Exception as e:
    fail('Phase2', 'Agent A /server/start', str(e))

time.sleep(0.5)

# 2c. Verify server is alive
try:
    st = http_get(f'{A_URL}/status')
    alive_ports = [s['port'] for s in st.get('servers', []) if s.get('alive')]
    assert TEST_PORT in alive_ports, f'port {TEST_PORT} not alive: {alive_ports}'
    ok('Phase2', f'Server port {TEST_PORT} alive')
except Exception as e:
    fail('Phase2', 'Server alive check', str(e))

# 2d. /client/start on Agent B → target 127.0.0.1
try:
    resp = http_post(f'{B_URL}/client/start', {
        'target': '127.0.0.1',
        'port': TEST_PORT,
        'duration': 3,
        'proto': 'tcp',
        'parallel': 1,
    })
    ok('Phase2', 'Agent B /client/start')
except Exception as e:
    fail('Phase2', 'Agent B /client/start', str(e))

time.sleep(1.5)

# 2e. /metrics on Agent B (wait for iperf3 to produce interval output)
try:
    m = http_get(f'{B_URL}/metrics')
    metrics = m.get('metrics', [])
    ok('Phase2', f'/metrics returned {len(metrics)} entries')
    if metrics:
        first = metrics[0]
        print(f'    metric keys: {sorted(first.keys())}')
        j = first.get('json') or {}
        up = j.get('interval_up_mbps', 0) or 0
        dn = j.get('interval_dn_mbps', 0) or 0
        print(f'    up={up:.1f} dn={dn:.1f} Mbps')
except Exception as e:
    fail('Phase2', '/metrics', str(e))

# Wait for short test to finish
time.sleep(3)

# 2f. /client/stop, /server/stop
try:
    http_post(f'{B_URL}/client/stop', {})
    ok('Phase2', 'Agent B /client/stop')
except Exception as e:
    fail('Phase2', 'Agent B /client/stop', str(e))

try:
    http_post(f'{A_URL}/server/stop', {})
    ok('Phase2', 'Agent A /server/stop')
except Exception as e:
    fail('Phase2', 'Agent A /server/stop', str(e))


# ═══════════════════════════════════════════════════════════════
#  PHASE 3: Dashboard Profile Save/Load
# ═══════════════════════════════════════════════════════════════
section('Phase 3: Dashboard Profile Save/Load')

from core.config_model import TestConfig, ClientConfig

# Redirect _PROFILE_PATH to temp BEFORE importing DashboardWindow
# so _save_profile() / _auto_load_profile() never touch real data/last_profile.json
TEMP_DATA = Path(tempfile.mkdtemp(prefix='ipm_test_'))
_fake_profile = TEMP_DATA / 'last_profile.json'
_fake_profile.write_text('{}', 'utf-8')

import ui.dashboard_window as _dw_mod
_dw_mod._PROFILE_PATH = _fake_profile

from ui.dashboard_window import DashboardWindow

win = DashboardWindow()

# 3a. Apply config → collect → verify round-trip
tc = TestConfig(
    server_agent=A_URL,
    server_bind='127.0.0.1',
    keep_servers_open=False,
    mode='bidir',
    duration_sec=5,
    base_port=15211,
    proto='tcp',
    parallel=1,
    omit=0,
    bitrate='',
    poll_interval_sec=0.5,
    clients=[
        ClientConfig(name='testB', agent=B_URL, target='127.0.0.1'),
    ],
)
win._apply_config(tc)

cfg = win._collect_config()
errs = []
if cfg['server']['agent'] != A_URL:
    errs.append(f"server.agent={cfg['server']['agent']}")
if cfg.get('mode') != 'bidir':
    errs.append(f"mode={cfg.get('mode')}")
if cfg.get('duration_sec') != 5:
    errs.append(f"duration_sec={cfg.get('duration_sec')}")
if cfg.get('proto') != 'tcp':
    errs.append(f"proto={cfg.get('proto')}")
if cfg.get('keep_servers_open') is not False:
    errs.append(f"keep_servers_open={cfg.get('keep_servers_open')}")
if abs(cfg.get('poll_interval_sec', 0) - 0.5) > 0.01:
    errs.append(f"poll_interval_sec={cfg.get('poll_interval_sec')}")
clients = cfg.get('clients', [])
if len(clients) != 1:
    errs.append(f"clients count={len(clients)}")
elif clients[0].get('name') != 'testB':
    errs.append(f"client name={clients[0].get('name')}")

if errs:
    fail('Phase3', 'apply→collect round-trip', '; '.join(errs))
else:
    ok('Phase3', 'apply→collect round-trip')

# 3b. Save to temp file, reload, verify
tmp_profile = TEMP_DATA / 'test_profile.json'
tmp_profile.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
tc2 = TestConfig.load_profile(tmp_profile)
assert tc2.server_agent == A_URL
assert tc2.mode == 'bidir'
assert tc2.duration_sec == 5
assert tc2.keep_servers_open is False
assert abs(tc2.poll_interval_sec - 0.5) < 0.01
assert len(tc2.clients) == 1
assert tc2.clients[0].name == 'testB'
ok('Phase3', 'save→load_profile round-trip')

# 3c. Re-apply loaded config, verify UI state
win._apply_config(tc2)
cfg2 = win._collect_config()
diffs = []
for key in ('mode', 'duration_sec', 'base_port', 'proto', 'parallel', 'omit',
            'poll_interval_sec', 'keep_servers_open'):
    if str(cfg.get(key)) != str(cfg2.get(key)):
        diffs.append(f'{key}: {cfg.get(key)!r}→{cfg2.get(key)!r}')
if cfg['server']['agent'] != cfg2['server']['agent']:
    diffs.append(f"server.agent mismatch")
if diffs:
    fail('Phase3', 'load→apply→collect consistency', '; '.join(diffs))
else:
    ok('Phase3', 'load→apply→collect consistency')

# 3d. Named profile save/load
named_dir = TEMP_DATA / 'profiles'
named_dir.mkdir(exist_ok=True)
named_path = named_dir / 'my_test.json'
named_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
tc3 = TestConfig.load_profile(named_path)
assert tc3.server_agent == A_URL
assert tc3.duration_sec == 5
ok('Phase3', 'Named profile save/load')

# 3e. All modes round-trip
for mode in ('bidir', 'up_only', 'down_only'):
    tc_mode = TestConfig(
        server_agent=A_URL, server_bind='127.0.0.1',
        mode=mode, duration_sec=3, base_port=15211, proto='tcp',
        clients=[ClientConfig(name='c', agent=B_URL, target='127.0.0.1')],
    )
    win._apply_config(tc_mode)
    c = win._collect_config()
    if c.get('mode') != mode:
        fail('Phase3', f'mode={mode} round-trip', f"got {c.get('mode')}")
    else:
        ok('Phase3', f'mode={mode} round-trip')


# ═══════════════════════════════════════════════════════════════
#  PHASE 4: Full Test Run (bidir, 5 seconds)
# ═══════════════════════════════════════════════════════════════
section('Phase 4: Full Test Run (bidir, 5s)')

# Set up config for a real test
test_cfg = TestConfig(
    server_agent=A_URL,
    server_bind='127.0.0.1',
    keep_servers_open=False,
    mode='bidir',
    duration_sec=5,
    base_port=15300,
    proto='tcp',
    parallel=1,
    omit=0,
    poll_interval_sec=0.5,
    clients=[
        ClientConfig(name='agentB', agent=B_URL, target='127.0.0.1'),
    ],
)
win._apply_config(test_cfg)

# Track signals
test_signals = {'started': False, 'finished': False, 'reason': '',
                'logs': [], 'errors': [], 'metrics_count': 0}

def on_started():
    test_signals['started'] = True
def on_finished(reason):
    test_signals['finished'] = True
    test_signals['reason'] = reason
def on_log(msg):
    test_signals['logs'].append(msg)
def on_error(msg):
    test_signals['errors'].append(msg)
def on_metrics(snap):
    test_signals['metrics_count'] += 1

win._runner_worker.test_started.connect(on_started)
win._runner_worker.test_finished.connect(on_finished)
win._runner_worker.log_message.connect(on_log)
win._runner_worker.error_occurred.connect(on_error)
win._poller_worker.metrics_received.connect(on_metrics)

# Start test via dashboard
print('  Starting test...')
win._on_start_test()

# Process events and wait for test to complete
t0 = time.time()
max_wait = 15  # 5s test + buffer
while time.time() - t0 < max_wait:
    app.processEvents()
    if test_signals['finished']:
        break
    time.sleep(0.1)

elapsed = time.time() - t0

# 4a. Test started signal
if test_signals['started']:
    ok('Phase4', 'test_started signal received')
else:
    fail('Phase4', 'test_started signal', 'never received')

# 4b. Test finished signal
if test_signals['finished']:
    ok('Phase4', f'test_finished signal: {test_signals["reason"]} ({elapsed:.1f}s)')
else:
    fail('Phase4', 'test_finished signal', f'never received after {elapsed:.1f}s')

# 4c. Log messages
log_count = len(test_signals['logs'])
print(f'  Log messages: {log_count}')
for m in test_signals['logs'][:10]:
    print(f'    {m}')
if log_count > 0:
    ok('Phase4', f'{log_count} log messages received')
else:
    fail('Phase4', 'log messages', 'no logs received')

# 4d. Errors
if test_signals['errors']:
    for e in test_signals['errors']:
        print(f'  ERROR: {e}')
    fail('Phase4', 'errors', '; '.join(test_signals['errors']))
else:
    ok('Phase4', 'no errors during test')

# 4e. Metrics received
mc = test_signals['metrics_count']
print(f'  Metrics snapshots: {mc}')
if mc > 0:
    ok('Phase4', f'{mc} metrics snapshots received')
else:
    fail('Phase4', 'metrics', 'no metrics received')

# 4f. CSV recording
if win._csv_recorder and win._csv_recorder.current_path:
    csv_path = win._csv_recorder.current_path
    if Path(csv_path).exists():
        csv_size = Path(csv_path).stat().st_size
        ok('Phase4', f'CSV file created: {csv_size} bytes')
    else:
        fail('Phase4', 'CSV file', f'{csv_path} does not exist')
else:
    fail('Phase4', 'CSV recorder', 'no recorder or no path')

# 4g. Chart data accumulated
total_ts = len(win._total['ts'])
if total_ts > 0:
    max_up = max(win._total['up']) if win._total['up'] else 0
    max_dn = max(win._total['dn']) if win._total['dn'] else 0
    ok('Phase4', f'Chart data: {total_ts} points, max up={max_up:.1f} dn={max_dn:.1f}')
    if max_up > 0 or max_dn > 0:
        ok('Phase4', 'Non-zero throughput detected')
    else:
        fail('Phase4', 'throughput', 'all zeros in chart data')
else:
    fail('Phase4', 'chart data', 'no total data accumulated')

# 4h. Verify server was stopped (keep_servers_open=False)
time.sleep(0.5)
try:
    st = http_get(f'{A_URL}/status')
    alive = [s for s in st.get('servers', []) if s.get('alive')]
    if len(alive) == 0:
        ok('Phase4', 'servers stopped (keep_servers_open=False)')
    else:
        fail('Phase4', 'servers stopped', f'{len(alive)} still alive: {alive}')
except Exception as e:
    fail('Phase4', 'server status check', str(e))


# ═══════════════════════════════════════════════════════════════
#  PHASE 5: Test up_only mode (3 seconds)
# ═══════════════════════════════════════════════════════════════
section('Phase 5: Test up_only mode (3s)')

test_signals2 = {'started': False, 'finished': False, 'reason': '',
                 'logs': [], 'errors': [], 'metrics_count': 0}

# Disconnect old handlers, connect new
win._runner_worker.test_started.disconnect(on_started)
win._runner_worker.test_finished.disconnect(on_finished)
win._runner_worker.log_message.disconnect(on_log)
win._runner_worker.error_occurred.disconnect(on_error)
win._poller_worker.metrics_received.disconnect(on_metrics)

def on_started2():
    test_signals2['started'] = True
def on_finished2(r):
    test_signals2['finished'] = True
    test_signals2['reason'] = r
def on_log2(m):
    test_signals2['logs'].append(m)
def on_error2(m):
    test_signals2['errors'].append(m)
def on_metrics2(s):
    test_signals2['metrics_count'] += 1

win._runner_worker.test_started.connect(on_started2)
win._runner_worker.test_finished.connect(on_finished2)
win._runner_worker.log_message.connect(on_log2)
win._runner_worker.error_occurred.connect(on_error2)
win._poller_worker.metrics_received.connect(on_metrics2)

up_cfg = TestConfig(
    server_agent=A_URL, server_bind='127.0.0.1',
    keep_servers_open=True,
    mode='up_only', duration_sec=3, base_port=15400,
    proto='tcp', parallel=1, omit=0, poll_interval_sec=0.5,
    clients=[ClientConfig(name='agentB', agent=B_URL, target='127.0.0.1')],
)
win._apply_config(up_cfg)
win._on_start_test()

t0 = time.time()
while time.time() - t0 < 12:
    app.processEvents()
    if test_signals2['finished']:
        break
    time.sleep(0.1)

if test_signals2['finished']:
    ok('Phase5', f'up_only finished: {test_signals2["reason"]} ({time.time()-t0:.1f}s)')
else:
    fail('Phase5', 'up_only finished', 'timeout')

if test_signals2['errors']:
    fail('Phase5', 'errors', '; '.join(test_signals2['errors']))
else:
    ok('Phase5', 'no errors')

mc2 = test_signals2['metrics_count']
if mc2 > 0:
    ok('Phase5', f'{mc2} metrics received')
else:
    fail('Phase5', 'metrics', 'none received')


# ═══════════════════════════════════════════════════════════════
#  PHASE 6: Test down_only mode (3 seconds)
# ═══════════════════════════════════════════════════════════════
section('Phase 6: Test down_only mode (3s)')

test_signals3 = {'started': False, 'finished': False, 'reason': '',
                 'logs': [], 'errors': [], 'metrics_count': 0}

win._runner_worker.test_started.disconnect(on_started2)
win._runner_worker.test_finished.disconnect(on_finished2)
win._runner_worker.log_message.disconnect(on_log2)
win._runner_worker.error_occurred.disconnect(on_error2)
win._poller_worker.metrics_received.disconnect(on_metrics2)

def on_started3(): test_signals3['started'] = True
def on_finished3(r): test_signals3['finished'] = True; test_signals3['reason'] = r
def on_log3(m): test_signals3['logs'].append(m)
def on_error3(m): test_signals3['errors'].append(m)
def on_metrics3(s): test_signals3['metrics_count'] += 1

win._runner_worker.test_started.connect(on_started3)
win._runner_worker.test_finished.connect(on_finished3)
win._runner_worker.log_message.connect(on_log3)
win._runner_worker.error_occurred.connect(on_error3)
win._poller_worker.metrics_received.connect(on_metrics3)

dn_cfg = TestConfig(
    server_agent=A_URL, server_bind='127.0.0.1',
    keep_servers_open=True,
    mode='down_only', duration_sec=3, base_port=15500,
    proto='tcp', parallel=1, omit=0, poll_interval_sec=0.5,
    clients=[ClientConfig(name='agentB', agent=B_URL, target='127.0.0.1')],
)
win._apply_config(dn_cfg)
win._on_start_test()

t0 = time.time()
while time.time() - t0 < 12:
    app.processEvents()
    if test_signals3['finished']:
        break
    time.sleep(0.1)

if test_signals3['finished']:
    ok('Phase6', f'down_only finished: {test_signals3["reason"]} ({time.time()-t0:.1f}s)')
else:
    fail('Phase6', 'down_only finished', 'timeout')

if test_signals3['errors']:
    fail('Phase6', 'errors', '; '.join(test_signals3['errors']))
else:
    ok('Phase6', 'no errors')

mc3 = test_signals3['metrics_count']
if mc3 > 0:
    ok('Phase6', f'{mc3} metrics received')
else:
    fail('Phase6', 'metrics', 'none received')


# ═══════════════════════════════════════════════════════════════
#  PHASE 7: Validation & Config Edge Cases
# ═══════════════════════════════════════════════════════════════
section('Phase 7: Validation & Edge Cases')

# 7a. Preflight check with bad server URL
bad_cfg = {
    'server': {'agent': 'http://192.0.2.1:9999'},
    'clients': [{'name': 'x', 'agent': 'http://192.0.2.2:9999', 'target': '192.0.2.1'}],
    'mode': 'bidir', 'duration_sec': 5, 'base_port': 5211,
    'proto': 'tcp', 'parallel': 1, 'omit': 0,
}
err = win._preflight_check(bad_cfg)
if err and 'unreachable' in err.lower():
    ok('Phase7', 'preflight detects unreachable agents')
else:
    fail('Phase7', 'preflight unreachable', f'got: {err}')

# 7b. Validation: empty server
tc_bad = TestConfig(server_agent='', clients=[])
errs = tc_bad.validate()
if any('Server' in e for e in errs):
    ok('Phase7', 'validation: empty server detected')
else:
    fail('Phase7', 'validation: empty server', str(errs))

# 7c. Validation: UDP + bidir
tc_udp = TestConfig(
    server_agent=A_URL, mode='bidir', proto='udp',
    clients=[ClientConfig(name='c', agent=B_URL, target='127.0.0.1', bidir=True)],
)
errs = tc_udp.validate()
if any('UDP' in e and 'bidir' in e for e in errs):
    ok('Phase7', 'validation: UDP+bidir rejected')
else:
    fail('Phase7', 'validation: UDP+bidir', str(errs))

# 7d. Multiple clients
multi_cfg = TestConfig(
    server_agent=A_URL, server_bind='127.0.0.1',
    mode='bidir', duration_sec=3, base_port=15600, proto='tcp',
    clients=[
        ClientConfig(name='c1', agent=B_URL, target='127.0.0.1'),
        ClientConfig(name='c2', agent=B_URL, target='127.0.0.1'),
    ],
)
win._apply_config(multi_cfg)
c = win._collect_config()
if len(c.get('clients', [])) == 2:
    ok('Phase7', '2-client config round-trip')
else:
    fail('Phase7', '2-client config', f'got {len(c.get("clients",[]))} clients')

# 7e. poll_interval_sec values
for pval in (0.2, 0.5, 1.0, 2.0, 5.0):
    tc_p = TestConfig(
        server_agent=A_URL, mode='bidir', duration_sec=3,
        poll_interval_sec=pval,
        clients=[ClientConfig(name='c', agent=B_URL, target='127.0.0.1')],
    )
    win._apply_config(tc_p)
    got = win._collect_config().get('poll_interval_sec', -1)
    if abs(got - pval) < 0.01:
        ok('Phase7', f'poll_interval_sec={pval} round-trip')
    else:
        fail('Phase7', f'poll_interval_sec={pval}', f'got {got}')


# ═══════════════════════════════════════════════════════════════
#  PHASE 8: Report Generation
# ═══════════════════════════════════════════════════════════════
section('Phase 8: Report Generation')

# Find the CSV from Phase 4
if win._csv_recorder and win._csv_recorder.current_path:
    csv_p = win._csv_recorder.current_path
    if Path(csv_p).exists():
        try:
            from core.report import generate_report
            html_path = generate_report(csv_p, dpi=72)
            if html_path and Path(html_path).exists():
                html_size = Path(html_path).stat().st_size
                ok('Phase8', f'Report generated: {html_size} bytes')
                # Check for PNG images
                html_content = Path(html_path).read_text('utf-8', errors='ignore')
                if '<img src=' in html_content:
                    # Check that referenced PNG files exist
                    import re as _re
                    pngs = _re.findall(r'<img src="([^"]+\.png)"', html_content)
                    html_dir = Path(html_path).parent
                    missing = [p for p in pngs if not (html_dir / p).exists()]
                    if missing:
                        fail('Phase8', 'Report PNG files', f'missing: {missing}')
                    else:
                        ok('Phase8', f'Report references {len(pngs)} PNG files, all exist')
                else:
                    fail('Phase8', 'Report images', 'no <img src=> tags found')
            else:
                fail('Phase8', 'Report file', f'{html_path} not created')
        except Exception as e:
            fail('Phase8', 'Report generation', traceback.format_exc())
    else:
        fail('Phase8', 'CSV for report', 'CSV file not found')
else:
    fail('Phase8', 'CSV recorder', 'no recorder available')


# ═══════════════════════════════════════════════════════════════
#  CLEANUP
# ═══════════════════════════════════════════════════════════════
section('Cleanup')

# Disconnect remaining signals (avoid double-fire)
try:
    win._runner_worker.test_started.disconnect(on_started3)
    win._runner_worker.test_finished.disconnect(on_finished3)
    win._runner_worker.log_message.disconnect(on_log3)
    win._runner_worker.error_occurred.disconnect(on_error3)
    win._poller_worker.metrics_received.disconnect(on_metrics3)
except Exception:
    pass

# Stop agents
try:
    agent_a.stop()
    ok('Cleanup', 'Agent A stopped')
except Exception as e:
    fail('Cleanup', 'Agent A stop', str(e))

try:
    agent_b.stop()
    ok('Cleanup', 'Agent B stopped')
except Exception as e:
    fail('Cleanup', 'Agent B stop', str(e))

# Clean temp
try:
    shutil.rmtree(TEMP_DATA, ignore_errors=True)
    ok('Cleanup', 'Temp data cleaned')
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════
print(f'\n{"="*60}')
print(f'  INTEGRATION TEST SUMMARY')
print(f'{"="*60}')
print(f'  Total: {PASS+FAIL}  |  PASS: {PASS}  |  FAIL: {FAIL}')
if ERRORS:
    print(f'\n  Failures:')
    for e in ERRORS:
        print(f'    - {e}')
print(f'{"="*60}\n')

sys.exit(0 if FAIL == 0 else 1)
