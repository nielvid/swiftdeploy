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


def _apply_chaos():
    """Returns True if request should be a 500 error."""
    with _chaos_lock:
        m = _chaos["mode"]
        if m == "slow":
            time.sleep(_chaos["duration"])
        elif m == "error":
            if random.random() < _chaos["rate"]:
                return True
    return False


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
            if self.path != "/healthz" and MODE == "canary" and _apply_chaos():
                _json(self, 500, {"error": "chaos error injection"})
                return
            method = getattr(self, "do_" + self.command, None)
            if method:
                method()
            else:
                self.send_error(405)
        except Exception:
            self.close_connection = True


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"SwiftDeploy service running on port {PORT} [{MODE}]", flush=True)
    server.serve_forever()
