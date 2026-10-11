import threading
import time
import json
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from phone_demo import ScreenState, handler_for, infer


class PhoneDemoChecks(unittest.TestCase):
    def test_withhold_and_same_strategy_preserve_screen(self):
        state = ScreenState()
        state.apply("S3", "manual")
        before = state.snapshot()
        state.apply(None, "insufficient history")
        self.assertEqual(state.snapshot()["seq"], before["seq"])
        self.assertEqual(state.snapshot()["strategy"], "S3")
        state.apply("S3", "model")
        self.assertEqual(state.snapshot()["seq"], before["seq"])

    def test_receipt_and_connection_are_separate(self):
        state = ScreenState()
        state.apply("S4", "manual")
        self.assertFalse(state.snapshot()["render_confirmed"])
        state.snapshot("phone")
        self.assertFalse(state.snapshot()["render_confirmed"])
        self.assertTrue(state.snapshot("phone", 1)["render_confirmed"])
        state.apply("S3", "manual")
        with self.assertRaises(ValueError):
            state.snapshot("phone", 1)
        state.clients["phone"]["seen"] = time.monotonic()-6
        self.assertEqual(state.snapshot()["connected_screens"], 0)

    def test_model_is_connected_to_screen_decision(self):
        result = infer({"hrv": 10, "task": "Ideation", "mode": "Creative", "source": "demo"})
        self.assertEqual(result["recommendation"], "S4")
        self.assertIsNone(infer({"hrv": 50, "task": "Ideation", "mode": "Creative", "source": "demo"})["recommendation"])

    def test_http_pipeline_and_invalid_commands(self):
        state = ScreenState()
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(state))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        def post(path, data, origin=None):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            with urlopen(Request(base+path, data=json.dumps(data).encode(), headers=headers), timeout=3) as response:
                return json.load(response)
        try:
            with urlopen(base+"/screen", timeout=3) as response:
                self.assertIn("LightCue", response.read().decode())
            payload = {"hrv": 10, "task": "Ideation", "mode": "Creative", "source": "demo"}
            result = post("/api/recommend", payload)
            self.assertEqual(result["strategy"], "S4")
            self.assertEqual(result["light"]["brightness"], 35)
            self.assertFalse(result["render_confirmed"])
            self.assertTrue(post("/api/screen", {"client": "test-phone", "ack": result["seq"]})["render_confirmed"])
            withheld = post("/api/recommend", dict(payload, hrv=50))
            self.assertEqual(withheld["strategy"], "S4")
            self.assertIsNone(withheld["result"]["recommendation"])
            for path, data, origin, status in [("/api/manual", {"strategy": "S9"}, None, 400),
                    ("/api/manual", {"strategy": "S3"}, "http://other.example", 403)]:
                with self.assertRaises(HTTPError) as error:
                    post(path, data, origin)
                self.assertEqual(error.exception.code, status)
            self.assertEqual(state.snapshot()["strategy"], "S4")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
