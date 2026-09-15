"""The panel: loopback, token-gated writes, no traversal."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from helpers import cleanup, construct_example, make_home

from taos_core import decisions as decisions_mod
from taos_core import panel as panel_mod


class TestPanel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)
        self.token = "testtoken"
        self.server = panel_mod.make_server(self.paths, 0, self.token)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:{0}".format(self.port)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        cleanup(self.tmp)

    def get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, response.read()

    def post(self, path: str, body: dict, token: str = None):
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Origin", "http://127.0.0.1:{0}".format(self.port))
        if token:
            request.add_header("X-TAOS-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def test_health_state_and_page(self) -> None:
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        status, body = self.get("/api/state")
        state = json.loads(body)
        self.assertEqual(len(state["tasks"]), 3)
        self.assertTrue(state["doctor"]["ok"])
        status, body = self.get("/")
        self.assertIn(b"testtoken", body)
        self.assertNotIn(b"__TAOS_TOKEN__", body)
        self.assertNotIn(b"cdn.", body)

    def test_writes_need_token(self) -> None:
        decision = decisions_mod.ask(self.paths, task_id="CMP-1", question="q", options=["a"], agent="codex")
        status, _ = self.post("/api/decide", {"id": decision["id"], "choice": "a"})
        self.assertEqual(status, 403)
        status, body = self.post("/api/decide", {"id": decision["id"], "choice": "a"}, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["decision"]["answer"], "a")
        status, body = self.post("/api/task/hot", {"id": "CMP-1", "hot": True, "reason": "panel"}, token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(body["task"]["hot"])

    def test_not_found_and_traversal(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/nope")
        self.assertEqual(caught.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/handoff?path=../../AGENTS.md")
        self.assertEqual(caught.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/etc/passwd")
        self.assertEqual(caught.exception.code, 404)

    def test_on_off_status(self) -> None:
        import socket

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()
        result = panel_mod.on(self.paths, port=free_port, open_browser=False)
        try:
            self.assertTrue(result["running"])
            self.assertTrue(panel_mod.status(self.paths)["running"])
        finally:
            off = panel_mod.off(self.paths)
        self.assertFalse(off["running"])
        self.assertFalse(panel_mod.status(self.paths)["running"])


if __name__ == "__main__":
    unittest.main()
