"""Local phone screen simulator. No calibrated light output or device brightness API."""
import argparse
import json
import math
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lightcue_multidim import DEFAULT_WEIGHTS, demo_history, read_history, recommend_multidim

ROOT = Path(__file__).resolve().parent
STRATEGIES = {
    "S1": {"name": "Stable", "kelvin": 4000, "brightness": 25, "color": "#ffe4ce"},
    "S2": {"name": "Focus Cue", "kelvin": 5000, "brightness": 40, "color": "#fff2e1"},
    "S3": {"name": "Creative Drift", "kelvin": 3800, "brightness": 25, "color": "#ffdfc3"},
    "S4": {"name": "Creative Cue", "kelvin": 4300, "brightness": 35, "color": "#ffe9d5"},
}


class ScreenState:
    def __init__(self):
        self.lock = threading.Lock()
        self.seq = 0
        self.strategy = None
        self.decision = "尚未发送"
        self.result = None
        self.clients = {}

    def apply(self, strategy, decision, result=None):
        if strategy is not None and strategy not in STRATEGIES:
            raise ValueError("Unknown strategy")
        with self.lock:
            # A withheld prediction never changes the existing screen setting.
            if strategy is not None and strategy != self.strategy:
                self.seq += 1
                self.strategy = strategy
            self.decision, self.result = decision, result

    def snapshot(self, client=None, ack=None):
        with self.lock:
            now = time.monotonic()
            if client is not None:
                if not isinstance(client, str) or not 1 <= len(client) <= 64:
                    raise ValueError("Invalid client id")
                if ack is not None and (type(ack) is not int or ack != self.seq):
                    raise ValueError("Acknowledgement is stale or invalid")
                entry = self.clients.setdefault(client, {"ack": None})
                entry["seen"] = now
                if ack is not None:
                    entry["ack"] = ack
            self.clients = {cid: entry for cid, entry in self.clients.items() if now - entry["seen"] < 60}
            live = [entry for entry in self.clients.values() if now - entry["seen"] < 5]
            return {"seq": self.seq, "strategy": self.strategy,
                    "light": STRATEGIES.get(self.strategy), "decision": self.decision,
                    "result": self.result, "connected_screens": len(live),
                    "render_confirmed": bool(self.strategy and any(e["ack"] == self.seq for e in live)),
                    "transition_seconds": 3, "simulator": True}


def infer(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected object")
    hrv = payload.get("hrv")
    if isinstance(hrv, bool) or not isinstance(hrv, (int, float)) or not math.isfinite(hrv):
        raise ValueError("HRV must be a finite number")
    task, mode = payload.get("task"), payload.get("mode")
    if not isinstance(task, str) or not isinstance(mode, str):
        raise ValueError("Task and mode must be strings")
    source = payload.get("source", "demo")
    if source not in ("demo", "real"):
        raise ValueError("Unknown preference source")
    weights = json.loads(DEFAULT_WEIGHTS.read_text(encoding="utf-8-sig"))
    rows = demo_history() if source == "demo" else read_history()
    return recommend_multidim(rows, hrv, task, mode, weights)


def handler_for(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body, mime="application/json; charset=utf-8"):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/state":
                return self.respond(200, state.snapshot())
            paths = {"/": "controller.html", "/screen": "screen.html"}
            if self.path not in paths:
                return self.respond(404, {"error": "Not found"})
            return self.respond(200, (ROOT / "phone_web" / paths[self.path]).read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            # Require a same-origin browser request when Origin is present.
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self.respond(403, {"error": "Origin mismatch"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid request size")
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    raise ValueError("JSON required")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected object")
                if self.path == "/api/recommend":
                    result = infer(payload)
                    state.apply(result["recommendation"], result["reason"] or "模型推荐", result)
                elif self.path == "/api/manual":
                    strategy = payload.get("strategy")
                    if not isinstance(strategy, str) or strategy not in STRATEGIES:
                        raise ValueError("Unknown strategy")
                    state.apply(strategy, "手动测试，并非 AI 推荐")
                elif self.path == "/api/screen":
                    return self.respond(200, state.snapshot(payload.get("client"), payload.get("ack")))
                else:
                    return self.respond(404, {"error": "Not found"})
                return self.respond(200, state.snapshot())
            except (ValueError, TypeError, OSError) as error:
                return self.respond(400, {"error": str(error)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(ScreenState()))
    print(f"Computer controller: http://127.0.0.1:{args.port}/", flush=True)
    print(f"Phone: http://<computer connection IP>:{args.port}/screen", flush=True)
    print("Local screen simulation only; CSS dimming does not change system brightness.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
