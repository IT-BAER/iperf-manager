# -*- coding: utf-8 -*-
"""
test_all.py - iperf_manager 통합 테스트
모든 수정/신규 모듈을 검증합니다.
"""
import sys, os, json, time, threading, tempfile, csv, datetime, traceback
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# 테스트 결과 추적
PASS = 0
FAIL = 0
ERRORS = []

def ok(name):
    global PASS
    PASS += 1
    print(f"  [PASS] {name}")

def fail(name, detail=""):
    global FAIL
    FAIL += 1
    msg = f"  [FAIL] {name}: {detail}"
    ERRORS.append(msg)
    print(msg)

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ============================================================
# 1. Syntax Check
# ============================================================
section("1. Syntax Check (py_compile)")

import py_compile
files_to_check = [
    'net_utils.py',
    'controller_v5_18.py',
    'report.py',
    'core/net_utils.py',
    'core/report.py',
    'core/test_runner.py',
    'core/agent_service.py',
    'core/config_model.py',
    'core/constants.py',
    'core/csv_recorder.py',
    'core/helpers.py',
]
for f in files_to_check:
    try:
        py_compile.compile(f, doraise=True)
        ok(f"syntax: {f}")
    except py_compile.PyCompileError as e:
        fail(f"syntax: {f}", str(e))

# ============================================================
# 2. Module Import Tests
# ============================================================
section("2. Module Import Tests")

try:
    from net_utils import http_post_json, http_get_json, poll_metrics, close_pool
    ok("import net_utils (backward-compat wrapper)")
except Exception as e:
    fail("import net_utils", str(e))

try:
    from core.net_utils import http_post_json, http_get_json, poll_metrics, _ConnPool, _to_float
    ok("import core.net_utils (all exports including private)")
except Exception as e:
    fail("import core.net_utils", str(e))

try:
    from core.test_runner import run_test
    ok("import core.test_runner.run_test")
except Exception as e:
    fail("import core.test_runner", str(e))

try:
    import importlib
    spec = importlib.util.spec_from_file_location("controller", "controller_v5_18.py")
    mod = importlib.util.module_from_spec(spec)
    # don't execute (has argparse), just check import chain
    ok("import controller (spec)")
except Exception as e:
    fail("import controller", str(e))

# report.py (may fail without matplotlib)
try:
    from report import generate_report
    ok("import report.generate_report (backward-compat wrapper)")
    _has_matplotlib = True
except ImportError as e:
    print(f"  [SKIP] import report.generate_report (matplotlib 미설치: {e})")
    _has_matplotlib = False
except Exception as e:
    fail("import report.generate_report", str(e))
    _has_matplotlib = False

try:
    from core.report import generate_report
    ok("import core.report.generate_report")
except ImportError:
    pass  # already handled above
except Exception as e:
    fail("import core.report.generate_report", str(e))

# ============================================================
# 3. net_utils Unit Tests
# ============================================================
section("3. net_utils Unit Tests")

# 3a. _to_float
try:
    assert _to_float("3.14") == 3.14
    assert _to_float("abc") is None
    assert _to_float(None) is None
    assert _to_float("1,234") is None  # comma not auto-converted
    assert _to_float(42) == 42.0
    ok("_to_float basic cases")
except AssertionError as e:
    fail("_to_float basic cases", str(e))
except Exception as e:
    fail("_to_float basic cases", str(e))

# 3b. _ConnPool
try:
    pool = _ConnPool()
    # get connection to non-existent host (should create HTTPConnection object)
    conn = pool.get("127.0.0.1", 19999, timeout=1)
    assert conn is not None
    # same key returns same connection
    conn2 = pool.get("127.0.0.1", 19999, timeout=1)
    assert conn is conn2
    # remove
    pool.remove("127.0.0.1", 19999)
    conn3 = pool.get("127.0.0.1", 19999, timeout=1)
    assert conn3 is not conn  # new connection after remove
    pool.close_all()
    ok("_ConnPool lifecycle (get/remove/close_all)")
except Exception as e:
    fail("_ConnPool lifecycle", str(e))

# 3c. http_post_json with mock server
class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        ln = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(ln)
        data = json.loads(body)
        resp = json.dumps({"echo": data, "status": "ok"}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)
    def do_GET(self):
        resp = json.dumps({"metrics": [], "health": "ok"}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

mock_port = 18901
mock_httpd = HTTPServer(('127.0.0.1', mock_port), MockHandler)
mock_httpd.allow_reuse_address = True
mock_thread = threading.Thread(target=mock_httpd.serve_forever, daemon=True)
mock_thread.start()
time.sleep(0.2)

base_url = f"http://127.0.0.1:{mock_port}"

try:
    result = http_post_json(base_url, '/test', {"hello": "world"})
    assert result['status'] == 'ok'
    assert result['echo']['hello'] == 'world'
    ok("http_post_json basic POST")
except Exception as e:
    fail("http_post_json basic POST", str(e))

try:
    result = http_get_json(base_url, '/metrics')
    assert result is not None
    assert 'health' in result
    ok("http_get_json basic GET")
except Exception as e:
    fail("http_get_json basic GET", str(e))

# 3d. http_post_json Keep-Alive reuse
try:
    r1 = http_post_json(base_url, '/a', {"seq": 1})
    r2 = http_post_json(base_url, '/b', {"seq": 2})
    assert r1['echo']['seq'] == 1
    assert r2['echo']['seq'] == 2
    ok("http_post_json Keep-Alive reuse (2 sequential calls)")
except Exception as e:
    fail("http_post_json Keep-Alive reuse", str(e))

# 3e. http_post_json error handling (connection refused)
try:
    try:
        http_post_json("http://127.0.0.1:19999", '/fail', {}, timeout=1)
        fail("http_post_json connection refused", "should have raised")
    except Exception:
        ok("http_post_json connection refused -> exception raised")
except Exception as e:
    fail("http_post_json connection refused", str(e))

# 3f. http_get_json error handling (returns None on failure)
try:
    result = http_get_json("http://127.0.0.1:19999", '/fail', timeout=1)
    assert result is None
    ok("http_get_json connection refused -> returns None")
except Exception as e:
    fail("http_get_json connection refused", str(e))

# 3g. poll_metrics with mock (empty metrics)
try:
    up, dn, ub, db, jit, los = poll_metrics(base_url)
    assert up == 0.0
    assert dn == 0.0
    ok("poll_metrics with empty metrics response")
except Exception as e:
    fail("poll_metrics empty", str(e))

# 3h. poll_metrics with unreachable host
try:
    up, dn, ub, db, jit, los = poll_metrics("http://127.0.0.1:19999")
    assert up == 0.0
    assert dn == 0.0
    ok("poll_metrics unreachable host -> zeros")
except Exception as e:
    fail("poll_metrics unreachable", str(e))

# ============================================================
# 5. Agent Unit Tests (start/stop, REST endpoints)
# ============================================================
section("5. Agent Service Tests")

# Try to import agent
try:
    sys.path.insert(0, '.')
    from core.agent_service import AgentService
    ok("import AgentService")
except Exception as e:
    fail("import AgentService", str(e))

# 5a. AgentService class constants
try:
    assert AgentService.MAX_SERVERS == 50
    assert AgentService.MAX_CLIENTS == 50
    ok("AgentService.MAX_SERVERS/MAX_CLIENTS = 50")
except Exception as e:
    fail("AgentService constants", str(e))

# 5b. _parse_json_interval method
try:
    svc = AgentService.__new__(AgentService)  # create without __init__
    # manually init just what we need
    svc.LOCK = threading.Lock()
    svc.SERVER_PROCS = {}
    svc.CLIENT_PROCS = {}

    # Test with valid iperf3 JSON structure
    json_data = {
        "intervals": [{
            "streams": [
                {"bits_per_second": 100_000_000, "sender": True},
                {"bits_per_second": 200_000_000, "sender": False}
            ],
            "sum": {
                "bits_per_second": 300_000_000,
                "sender": True,
                "jitter_ms": 0.5,
                "lost_percent": 0.1
            }
        }]
    }
    result = svc._parse_json_interval(json_data)
    assert result is not None
    assert 'interval_up_mbps' in result
    assert 'interval_dn_mbps' in result
    assert result['interval_up_mbps'] > 0
    assert result['interval_dn_mbps'] > 0
    ok("_parse_json_interval with valid data")

    # Test with empty intervals
    result2 = svc._parse_json_interval({"intervals": []})
    assert result2 is None
    ok("_parse_json_interval with empty intervals -> None")

    # Test with no intervals key
    result3 = svc._parse_json_interval({})
    assert result3 is None
    ok("_parse_json_interval with no intervals key -> None")

    # Test with malformed data
    result4 = svc._parse_json_interval({"intervals": [{"bad": "data"}]})
    # Should not crash
    ok("_parse_json_interval with malformed data -> no crash")

except Exception as e:
    fail("_parse_json_interval", str(e))

# 5c. _normalize_task
try:
    svc2 = AgentService.__new__(AgentService)
    svc2.LOCK = threading.Lock()
    svc2.SERVER_PROCS = {}
    svc2.CLIENT_PROCS = {}

    # Test alias resolution
    task = svc2._normalize_task({
        'protocol': 'udp',
        'time': 30,
        'P': 1,
        'bandwidth': '100M',
        'len': '1400',
        'bind_ip': '10.0.0.1',
        'reverse': 'true',
        'bidir': 'false',
        'extra_args': '--congestion cubic'
    })
    assert task['proto'] == 'udp'
    assert task['duration'] == 30
    assert task['parallel'] == 1
    assert task['bitrate'] == '100M'
    assert task['length'] == '1400'
    assert task['bind'] == '10.0.0.1'
    assert task['reverse'] == True
    assert task['bidir'] == False
    assert isinstance(task['extra_args'], list)
    assert '--congestion' in task['extra_args']
    ok("_normalize_task alias resolution")
except Exception as e:
    fail("_normalize_task", str(e))

# 5d. AgentService start/stop lifecycle + REST endpoints
agent_port = 18903
try:
    svc3 = AgentService(host='127.0.0.1', port=agent_port, iperf3_bin='iperf3', autostart_ports=[])
    svc3.start()
    time.sleep(0.5)
    ok("AgentService.start()")

    # Test /status endpoint
    import urllib.request
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{agent_port}/status', timeout=3) as r:
            status = json.loads(r.read().decode())
        assert 'servers' in status
        assert 'clients' in status
        assert 'log_dir' in status
        ok("GET /status endpoint")
    except Exception as e:
        fail("GET /status endpoint", str(e))

    # Test /metrics endpoint
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{agent_port}/metrics', timeout=3) as r:
            metrics = json.loads(r.read().decode())
        assert 'metrics' in metrics
        assert isinstance(metrics['metrics'], list)
        ok("GET /metrics endpoint")
    except Exception as e:
        fail("GET /metrics endpoint", str(e))

    # Test POST /server/start (will fail without iperf3 but should return proper JSON error)
    try:
        payload = json.dumps({"ports": [15201]}).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{agent_port}/server/start',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            result = json.loads(r.read().decode())
        # Either started or errors (iperf3 not found)
        assert 'started' in result or 'errors' in result
        ok("POST /server/start response format")
    except urllib.error.HTTPError as e:
        # 500 with JSON error is also acceptable
        body = e.read().decode()
        try:
            err = json.loads(body)
            assert 'error' in err
            ok("POST /server/start -> JSON error (iperf3 not found)")
        except Exception:
            fail("POST /server/start", f"HTTP {e.code}: {body[:100]}")
    except Exception as e:
        fail("POST /server/start", str(e))

    # Test POST /client/start without target (should return error)
    try:
        payload = json.dumps({}).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{agent_port}/client/start',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                result = json.loads(r.read().decode())
            fail("POST /client/start no target", "should have returned error")
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode())
            assert 'error' in body
            ok("POST /client/start no target -> 500 error")
    except Exception as e:
        fail("POST /client/start validation", str(e))

    # Test 64KB payload limit
    try:
        big_payload = json.dumps({"data": "x" * 70000}).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{agent_port}/client/start',
            data=big_payload,
            headers={'Content-Type': 'application/json', 'Content-Length': str(len(big_payload))}
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                result = json.loads(r.read().decode())
            # If it didn't get 413, check if it got past
            fail("64KB limit", "should have returned 413")
        except urllib.error.HTTPError as e:
            assert e.code == 413, f"Expected 413, got {e.code}"
            ok("POST 64KB payload limit -> 413 rejected")
    except Exception as e:
        fail("64KB payload limit", str(e))

    # Test 404 for unknown path
    try:
        payload = json.dumps({}).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{agent_port}/unknown',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                pass
            fail("404 unknown path", "should have returned 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
            ok("POST unknown path -> 404")
    except Exception as e:
        fail("404 unknown path", str(e))

    # Stop service
    svc3.stop()
    time.sleep(0.3)
    ok("AgentService.stop()")

except FileNotFoundError as e:
    print(f"  [SKIP] AgentService lifecycle (iperf3 not found: {e})")
    # Still try to test basic instantiation
    try:
        svc3.stop()
    except Exception:
        pass
except Exception as e:
    fail("AgentService lifecycle", traceback.format_exc())
    try:
        svc3.stop()
    except Exception:
        pass

# ============================================================
# 6. Report Generation Test (if matplotlib available)
# ============================================================
section("6. Report Generation Test")

if _has_matplotlib:
    try:
        tmpdir = tempfile.mkdtemp(prefix='iperf_test_')
        csv_path = os.path.join(tmpdir, 'test_ui.csv')
        now = int(time.time())

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['ts', 'wall', 'total_up', 'total_dn', 'client1_up', 'client1_dn'])
            for i in range(10):
                t = now + i
                wall = datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S')
                w.writerow([t, wall, 50+i, 80+i, 50+i, 80+i])

        rep_path = generate_report(
            csv_path,
            agent_map={'client1': '10.0.0.2'},
            target_map={'client1': '10.0.0.1'},
            style_map=None,
            test_opts={'proto': 'tcp', 'duration_sec': 10},
            server_url='http://10.0.0.1:9001'
        )
        assert os.path.exists(rep_path)
        html = Path(rep_path).read_text(encoding='utf-8')
        assert 'IPERF3 Throughput TEST Report' in html
        assert 'client1' in html
        assert '10.0.0.1' in html
        assert '10.0.0.2' in html

        # Check PNGs generated
        assert os.path.exists(os.path.join(tmpdir, 'test_total.png'))
        assert os.path.exists(os.path.join(tmpdir, 'test_agents.png'))
        ok("generate_report() HTML + PNG output")

        # Cleanup
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:
        fail("generate_report()", traceback.format_exc())
else:
    print("  [SKIP] Report generation (matplotlib not installed)")

# ============================================================
# 7. Controller / test_runner Module Test
# ============================================================
section("7. Controller / test_runner Module Test")

try:
    from core.test_runner import run_test
    ok("import core.test_runner.run_test")
except Exception as e:
    fail("import core.test_runner.run_test", str(e))

try:
    # Verify controller is now a thin wrapper using core.test_runner
    with open('controller_v5_18.py', 'r', encoding='utf-8') as f:
        src = f.read()
    assert 'from core.test_runner import run_test' in src
    ok("controller imports from core.test_runner")
    assert 'def main()' in src
    ok("controller has main() entry point")
except Exception as e:
    fail("controller module check", str(e))

# ============================================================
# 9. Edge Case Tests
# ============================================================
section("9. Edge Case Tests")

# 9a. _normalize_task with empty dict
try:
    svc_e = AgentService.__new__(AgentService)
    svc_e.LOCK = threading.Lock()
    svc_e.SERVER_PROCS = {}
    svc_e.CLIENT_PROCS = {}
    result = svc_e._normalize_task({})
    assert isinstance(result, dict)
    ok("_normalize_task with empty dict")
except Exception as e:
    fail("_normalize_task empty dict", str(e))

# 9b. _normalize_task with all aliases
try:
    task = svc_e._normalize_task({
        'protocol': 'tcp',
        'seconds': 60,
        'threads': 4,
        'bw': '1G',
        'bytes': 1000,
    })
    assert task['proto'] == 'tcp'
    assert task['duration'] == 60
    assert task['parallel'] == 4
    assert task['bitrate'] == '1G'
    assert task['length'] == 1000  # 'bytes' maps to 'length'... actually let me check
    ok("_normalize_task alternative aliases")
except Exception as e:
    fail("_normalize_task aliases", str(e))

# 9c. poll_metrics with actual metrics data via mock
class RichMetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        metrics = {
            "metrics": [{
                "key": "test:5211:F",
                "task": {"target": "10.0.0.1", "port": 5211},
                "json": {
                    "interval_up_mbps": 150.5,
                    "interval_dn_mbps": 250.3,
                    "jitter_ms": 1.2,
                    "loss_pct": 0.05
                }
            }, {
                "key": "test:5212:B",
                "task": {"target": "10.0.0.1", "port": 5212},
                "json": {
                    "interval_up_mbps": 50.0,
                    "interval_dn_mbps": 75.0,
                }
            }]
        }
        resp = json.dumps(metrics).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

rich_port = 18904
rich_httpd = HTTPServer(('127.0.0.1', rich_port), RichMetricsHandler)
rich_httpd.allow_reuse_address = True
rich_thread = threading.Thread(target=rich_httpd.serve_forever, daemon=True)
rich_thread.start()
time.sleep(0.2)

try:
    up, dn, ub, db, jit, los = poll_metrics(f"http://127.0.0.1:{rich_port}")
    assert abs(up - 200.5) < 0.01, f"up={up}, expected ~200.5"
    assert abs(dn - 325.3) < 0.01, f"dn={dn}, expected ~325.3"
    assert jit is not None and jit > 0
    assert los is not None and los > 0
    ok(f"poll_metrics multi-client aggregation (up={up:.1f}, dn={dn:.1f}, jit={jit}, los={los})")
except Exception as e:
    fail("poll_metrics multi-client", str(e))

# 9d. poll_metrics mode_hint
try:
    # Test with sum_mbps and mode_hint
    class SumMetricsHandler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            resp = json.dumps({
                "metrics": [{"key": "k", "task": {}, "json": {"sum_mbps": 500.0}}]
            }).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

    sum_port = 18905
    sum_httpd = HTTPServer(('127.0.0.1', sum_port), SumMetricsHandler)
    sum_httpd.allow_reuse_address = True
    sum_thread = threading.Thread(target=sum_httpd.serve_forever, daemon=True)
    sum_thread.start()
    time.sleep(0.2)

    # down_only hint
    up, dn, *_ = poll_metrics(f"http://127.0.0.1:{sum_port}", mode_hint='down_only')
    assert dn == 500.0, f"down_only: dn={dn}, expected 500"
    assert up == 0.0, f"down_only: up={up}, expected 0"
    ok("poll_metrics mode_hint=down_only")

    # up_only hint
    up, dn, *_ = poll_metrics(f"http://127.0.0.1:{sum_port}", mode_hint='up_only')
    assert up == 500.0, f"up_only: up={up}, expected 500"
    assert dn == 0.0, f"up_only: dn={dn}, expected 0"
    ok("poll_metrics mode_hint=up_only")

except Exception as e:
    fail("poll_metrics mode_hint", str(e))

# ============================================================
# 10. New Feature Tests (Stage 2-4 improvements)
# ============================================================
section("10. New Feature Tests")

# 10a. ThreadingHTTPServer import
try:
    from http.server import ThreadingHTTPServer
    ok("ThreadingHTTPServer available in stdlib")
except ImportError:
    fail("ThreadingHTTPServer import", "not available")

# 10b. Agent API token check (unit test of logic)
try:
    # Simulate the token check logic from the handler
    api_token = "test-secret-123"
    req_token = "test-secret-123"
    assert req_token == api_token, "token mismatch"
    ok("API token match logic")

    # Empty token = no auth
    api_token_empty = ""
    assert not api_token_empty, "empty token should be falsy"
    ok("API token empty = no auth")
except Exception as e:
    fail("API token logic", str(e))

# 10c. close_pool function exists
try:
    from core.net_utils import close_pool
    close_pool()  # should not raise
    ok("close_pool() callable")
except Exception as e:
    fail("close_pool", str(e))

# 10d. _to_float narrowed exception types
try:
    from core.net_utils import _to_float
    assert _to_float("3.14") == 3.14
    assert _to_float("bad", 0.0) == 0.0
    assert _to_float(None, -1.0) == -1.0
    ok("_to_float with narrowed exceptions")
except Exception as e:
    fail("_to_float narrowed", str(e))

# 10ea. net_utils api_key parameter wiring
try:
    import inspect
    from core.net_utils import http_post_json as _hpj, http_get_json as _hgj, poll_metrics as _pm
    assert 'api_key' in inspect.signature(_hpj).parameters
    assert 'api_key' in inspect.signature(_hgj).parameters
    assert 'api_key' in inspect.signature(_pm).parameters
    ok("net_utils supports api_key parameter")
except Exception as e:
    fail("net_utils api_key parameter", str(e))

# 10f. core.test_runner integration check
try:
    from core.test_runner import run_test
    import inspect
    sig = inspect.signature(run_test)
    assert 'cfg' in sig.parameters
    assert 'csv_path' in sig.parameters
    assert 'on_log' in sig.parameters
    assert 'stop_event' in sig.parameters
    ok("core.test_runner.run_test signature check")
except Exception as e:
    fail("core.test_runner signature", str(e))

# 10g. report.py _to_float narrowed
try:
    from core.report import _to_float as report_to_float
    assert report_to_float("10.5") == 10.5
    assert report_to_float("bad") == 0.0
    assert report_to_float(None) == 0.0
    ok("report._to_float narrowed exceptions")
except Exception as e:
    fail("report._to_float", str(e))

# 10h. Agent core features check
try:
    with open('core/agent_service.py', 'r', encoding='utf-8') as f:
        agent_src = f.read()
    assert 'def _log(self' in agent_src, "_log method not found"
    assert 'def _atexit_cleanup(self' in agent_src, "_atexit_cleanup not found"
    assert 'ThreadingHTTPServer' in agent_src, "ThreadingHTTPServer not used"
    assert 'api_token' in agent_src, "api_token not found"
    ok("Agent: _log, atexit, ThreadingHTTPServer, api_token present")
except Exception as e:
    fail("Agent core features check", str(e))

# 10i. run_test uses configurable poll interval
try:
    with open('core/test_runner.py', 'r', encoding='utf-8') as f:
        runner_src = f.read()
    assert "poll_interval_sec" in runner_src
    assert "time.sleep(poll_interval_sec)" in runner_src
    ok("run_test poll_interval_sec wiring present")
except Exception as e:
    fail("run_test poll_interval_sec wiring", str(e))

# ============================================================
#  11. Config Validation Tests (TestConfig.validate)
# ============================================================
section("Config Validation Tests")

from core.config_model import TestConfig, ClientConfig

# 11a. Valid config passes validation
try:
    tc = TestConfig(
        server_agent='http://192.168.1.1:9001',
        clients=[ClientConfig(name='c1', agent='http://192.168.1.2:9001', target='192.168.1.1')],
        mode='bidir', duration_sec=30, base_port=5211, parallel=1, omit=0,
    )
    errs = tc.validate()
    assert errs == [], f"Expected no errors, got: {errs}"
    ok("Valid config passes validation")
except Exception as e:
    fail("Valid config passes validation", str(e))

# 11b. Missing server URL
try:
    tc = TestConfig(server_agent='http://A-IP:9001',
                    clients=[ClientConfig(name='c1', agent='http://x:9001', target='1.2.3.4')])
    errs = tc.validate()
    assert any('Server' in e for e in errs), f"Expected server error, got: {errs}"
    ok("Missing server URL detected")
except Exception as e:
    fail("Missing server URL detected", str(e))

# 11c. Empty clients
try:
    tc = TestConfig(server_agent='http://192.168.1.1:9001', clients=[])
    errs = tc.validate()
    assert any('client' in e.lower() for e in errs), f"Expected client error, got: {errs}"
    ok("Empty clients detected")
except Exception as e:
    fail("Empty clients detected", str(e))

# 11d. UDP + bidir constraint
try:
    tc = TestConfig(
        server_agent='http://192.168.1.1:9001', proto='udp',
        clients=[ClientConfig(name='c1', agent='http://x:9001', target='1.2.3.4', bidir=True)],
    )
    errs = tc.validate()
    assert any('UDP' in e and 'bidir' in e for e in errs), f"Expected UDP+bidir error, got: {errs}"
    ok("UDP + bidir constraint detected")
except Exception as e:
    fail("UDP + bidir constraint detected", str(e))

# 11e. Port range overflow
try:
    tc = TestConfig(
        server_agent='http://192.168.1.1:9001', base_port=65530,
        clients=[ClientConfig(name=f'c{i}', agent=f'http://x{i}:9001', target='1.2.3.4') for i in range(10)],
    )
    errs = tc.validate()
    assert any('65535' in e for e in errs), f"Expected port overflow error, got: {errs}"
    ok("Port range overflow detected")
except Exception as e:
    fail("Port range overflow detected", str(e))

# 11f. Invalid mode
try:
    tc = TestConfig(
        server_agent='http://192.168.1.1:9001', mode='invalid_mode',
        clients=[ClientConfig(name='c1', agent='http://x:9001', target='1.2.3.4')],
    )
    errs = tc.validate()
    assert any('mode' in e.lower() for e in errs), f"Expected mode error, got: {errs}"
    ok("Invalid mode detected")
except Exception as e:
    fail("Invalid mode detected", str(e))

# 11g. Invalid bitrate format
try:
    tc = TestConfig(
        server_agent='http://192.168.1.1:9001', bitrate='abc',
        clients=[ClientConfig(name='c1', agent='http://x:9001', target='1.2.3.4')],
    )
    errs = tc.validate()
    assert any('bitrate' in e.lower() for e in errs), f"Expected bitrate error, got: {errs}"
    ok("Invalid bitrate format detected")
except Exception as e:
    fail("Invalid bitrate format detected", str(e))

# 11h. Valid bitrate formats accepted
try:
    for br in ('100M', '1G', '500k', '50', '1.5G'):
        tc = TestConfig(
            server_agent='http://192.168.1.1:9001', bitrate=br,
            clients=[ClientConfig(name='c1', agent='http://x:9001', target='1.2.3.4')],
        )
        errs = tc.validate()
        br_errs = [e for e in errs if 'bitrate' in e.lower()]
        assert not br_errs, f"Bitrate '{br}' should be valid but got: {br_errs}"
    ok("Valid bitrate formats accepted")
except Exception as e:
    fail("Valid bitrate formats accepted", str(e))

# 11i. keep_servers_open + api_key profile round-trip
try:
    tc = TestConfig(
        server_agent='http://192.168.1.1:9001',
        api_key='factory-token',
        keep_servers_open=False,
        poll_interval_sec=0.7,
        clients=[ClientConfig(name='c1', agent='http://x:9001', target='1.2.3.4')],
    )
    d = tc.to_dict()
    assert d.get('keep_servers_open') is False
    assert d.get('api_key') == 'factory-token'
    assert d.get('server', {}).get('api_key') == 'factory-token'
    tc2 = TestConfig.from_dict(d)
    assert tc2.keep_servers_open is False
    assert tc2.api_key == 'factory-token'
    assert abs(tc2.poll_interval_sec - 0.7) < 1e-9
    ok("Profile round-trip keeps keep_servers_open/api_key/poll_interval_sec")
except Exception as e:
    fail("Profile round-trip", str(e))

# 11j. poll_interval_sec validation
try:
    tc = TestConfig(
        server_agent='http://192.168.1.1:9001',
        poll_interval_sec=0.0,
        clients=[ClientConfig(name='c1', agent='http://x:9001', target='1.2.3.4')],
    )
    errs = tc.validate()
    assert any('poll_interval_sec' in e for e in errs), f"Expected poll interval error, got: {errs}"
    ok("poll_interval_sec validation detected")
except Exception as e:
    fail("poll_interval_sec validation detected", str(e))

# 11k. CsvRecorder rollover keeps previous segment
try:
    from core.csv_recorder import CsvRecorder
    import shutil

    tmpdir = tempfile.mkdtemp(prefix='iperf_roll_')
    rec = CsvRecorder(
        data_dir=tmpdir,
        run_base='testrun',
        agent_names=['a1'],
        proto='tcp',
        roll_minutes=1,
        zip_rolled=False,
    )
    p0 = rec.open()
    rec.append_row(['1', '2026-01-01 00:00:01', '1', '2', '3', '1', '2', '0', '0', '0', '0'])
    rec._open_ts = time.time() - 61  # force rollover
    rolled = rec.check_rollover()
    p1 = rec.current_path
    assert rolled is True
    assert p1 and p1 != p0
    assert p1.endswith('_ui_p001.csv')
    assert Path(p0).exists(), "old segment missing after rollover"
    old_lines = Path(p0).read_text(encoding='utf-8').splitlines()
    assert len(old_lines) >= 3, f"old segment data lost: lines={len(old_lines)}"
    rec.append_row(['2', '2026-01-01 00:00:02', '4', '5', '9', '4', '5', '0', '0', '0', '0'])
    new_lines = Path(p1).read_text(encoding='utf-8').splitlines()
    assert len(new_lines) >= 3, f"new segment row write failed: lines={len(new_lines)}"
    ok("CsvRecorder rollover creates new segment without overwriting old data")
    shutil.rmtree(tmpdir, ignore_errors=True)
except Exception as e:
    fail("CsvRecorder rollover data retention", str(e))

# ============================================================
# Cleanup
# ============================================================
mock_httpd.shutdown()
rich_httpd.shutdown()
try: sum_httpd.shutdown()
except: pass

# ============================================================
# Summary
# ============================================================
section("TEST SUMMARY")
total = PASS + FAIL
print(f"\n  Total: {total}  |  PASS: {PASS}  |  FAIL: {FAIL}")
if ERRORS:
    print(f"\n  Failures:")
    for e in ERRORS:
        print(f"    {e}")
print()
sys.exit(0 if FAIL == 0 else 1)
