import os
import time
import json
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

MODE = os.environ.get("MODE", "stable")
VERSION = os.environ.get("APP_VERSION", "1.0.0")
PORT = int(os.environ.get("APP_PORT", 3000))
START_TIME = time.time()

_chaos = {"mode": None, "duration": 0, "rate": 0.0}
_chaos_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Metrics state
# ---------------------------------------------------------------------------
_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
_metrics_lock = threading.Lock()
# {(method, path, status_code): count}
_req_total = {}
# histogram: {le: count}  plus _sum and _count
_hist_buckets = {le: 0 for le in _BUCKETS}
_hist_inf = 0
_hist_sum = 0.0
_hist_count = 0


def _record(method, path, status, duration):
    key = (method, path, str(status))
    with _metrics_lock:
        _req_total[key] = _req_total.get(key, 0) + 1
        global _hist_sum, _hist_count, _hist_inf
        _hist_sum += duration
        _hist_count += 1
        for le in _BUCKETS:
            if duration <= le:
                _hist_buckets[le] += 1
        _hist_inf += 1


def _metrics_text():
    lines = []
    with _metrics_lock:
        # http_requests_total
        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        for (method, path, status), count in _req_total.items():
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status_code="{status}"}} {count}'
            )

        # http_request_duration_seconds
        lines.append("# HELP http_request_duration_seconds Request latency histogram")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for le in _BUCKETS:
            lines.append(
                f'http_request_duration_seconds_bucket{{le="{le}"}} {_hist_buckets[le]}'
            )
        lines.append(f'http_request_duration_seconds_bucket{{le="+Inf"}} {_hist_inf}')
        lines.append(f"http_request_duration_seconds_sum {_hist_sum:.6f}")
        lines.append(f"http_request_duration_seconds_count {_hist_count}")

        # app_uptime_seconds
        lines.append("# HELP app_uptime_seconds Seconds since process start")
        lines.append("# TYPE app_uptime_seconds gauge")
        lines.append(f"app_uptime_seconds {round(time.time() - START_TIME, 2)}")

        # app_mode
        lines.append("# HELP app_mode Current deployment mode (0=stable 1=canary)")
        lines.append("# TYPE app_mode gauge")
        lines.append(f"app_mode {1 if MODE == 'canary' else 0}")

        # chaos_active
        chaos_val = {"slow": 1, "error": 2}.get(_chaos["mode"], 0)
        lines.append("# HELP chaos_active Active chaos state (0=none 1=slow 2=error)")
        lines.append("# TYPE chaos_active gauge")
        lines.append(f"chaos_active {chaos_val}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Chaos helpers
# ---------------------------------------------------------------------------
def _apply_chaos():
    with _chaos_lock:
        m = _chaos["mode"]
        if m == "slow":
            time.sleep(_chaos["duration"])
        elif m == "error":
            if random.random() < _chaos["rate"]:
                return True
    return False


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
def _json(handler, status, body, extra_headers=None):
    data = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    if MODE == "canary":
        handler.send_header("X-Mode", "canary")
    if extra_headers:
        for k, v in extra_headers.items():
            handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(data)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/healthz":
            _json(self, 200, {"status": "ok", "uptime": round(time.time() - START_TIME, 2)})
        elif self.path == "/":
            _json(self, 200, {
                "message": f"Welcome to SwiftDeploy [{MODE}]",
                "mode": MODE,
                "version": VERSION,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        elif self.path == "/metrics":
            data = _metrics_text().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            _json(self, 404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/chaos":
            _json(self, 404, {"error": "not found"})
            return
        if MODE != "canary":
            _json(self, 403, {"error": "chaos only available in canary mode"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            _json(self, 400, {"error": "invalid JSON"})
            return

        m = body.get("mode")
        with _chaos_lock:
            if m == "slow":
                _chaos["mode"] = "slow"
                _chaos["duration"] = int(body.get("duration", 1))
            elif m == "error":
                _chaos["mode"] = "error"
                _chaos["rate"] = float(body.get("rate", 0.5))
            elif m == "recover":
                _chaos["mode"] = None
                _chaos["duration"] = 0
                _chaos["rate"] = 0.0
            else:
                _json(self, 400, {"error": "unknown chaos mode"})
                return

        _json(self, 200, {"chaos": _chaos["mode"], "active": _chaos["mode"] is not None})

    def handle_one_request(self):
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = True
                return
            if not self.parse_request():
                return

            t0 = time.time()

            # Apply chaos (skip for /healthz and /metrics)
            if self.path not in ("/healthz", "/metrics") and MODE == "canary" and _apply_chaos():
                _json(self, 500, {"error": "chaos error injection"})
                _record(self.command, self.path, 500, time.time() - t0)
                return

            method = getattr(self, "do_" + self.command, None)
            if method:
                method()
            else:
                self.send_error(405)

            # Record metrics — status code is already sent, approximate from path
            status = 200
            if self.path not in ("/", "/healthz", "/metrics", "/chaos"):
                status = 404
            _record(self.command, self.path, status, time.time() - t0)

        except Exception:
            self.close_connection = True


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"SwiftDeploy service running on port {PORT} [{MODE}]", flush=True)
    server.serve_forever()
