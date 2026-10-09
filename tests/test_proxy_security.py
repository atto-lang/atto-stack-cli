#!/usr/bin/env python3
"""Security regressions for the dev HTTP proxy's two trust boundaries."""
import email.message
import http.server
import importlib.util
import io
import os
import pathlib
import threading
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ores_generation_tree", ROOT / "bin/generation-tree.py")
TREE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TREE)

class Upstream(http.server.BaseHTTPRequestHandler):
    received = []
    def log_message(self, *args): pass
    def do_GET(self):
        type(self).received.append(self.headers)
        self.send_response(200)
        self.send_header("Connection", "X-Upstream-Private")
        self.send_header("X-Upstream-Private", "internal-only")
        self.send_header("X-Ores-Dev-Token", "upstream-leaked-bearer")
        self.send_header("X-Ores-Dev-Target-Port", "54321")
        self.send_header("Proxy-Authenticate", "secret")
        self.send_header("X-Public", "safe")
        self.end_headers()
        self.wfile.write(b"hello")

def request(headers=None, path="/hello", body=b""):
    values = email.message.Message()
    for k,v in headers or []:
        values.add_header(k,v)
    return types.SimpleNamespace(headers=values,
                                 rfile=io.BytesIO(body),
                                 path=path,command="GET")

class ProxyAdmission(unittest.TestCase):
    def test_internal_headers_never_escape_to_client(self):
        Upstream.received.clear()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            supplied = [
                ("X-Ores-Dev-Token", "attacker-controlled"),
                ("X-Ores-Dev-Target-Port", "1234"),
                ("Connection", "X-Sent-Private"),
                ("X-Sent-Private", "do-not-forward"),
                ("Proxy-Authorization", "Basic sensitive"),
                ("X-Public-Request", "allowed"),
            ]
            status,headers,body = TREE.forwarded(
                server.server_port, request(supplied), "internal-trusted-token", 45678)
            self.assertEqual(status, 200)
            self.assertEqual(body, b"hello")
            keys = {k.lower() for k in headers}
            self.assertEqual(headers["X-Public"],"safe")
            self.assertNotIn("x-upstream-private",keys)
            self.assertNotIn("connection",keys)
            self.assertNotIn("proxy-authenticate",keys)
            self.assertFalse(any(k.startswith("x-ores-dev-") for k in keys))
            recorded = Upstream.received[-1]
            self.assertEqual(recorded.get("X-Ores-Dev-Token"),"internal-trusted-token")
            self.assertEqual(recorded.get("X-Ores-Dev-Target-Port"),"45678")
            self.assertIsNone(recorded.get("X-Sent-Private"))
            self.assertIsNone(recorded.get("Proxy-Authorization"))
            self.assertEqual(recorded.get("X-Public-Request"),"allowed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_worker_environment_drops_unrelated_parent_settings(self):
        with mock.patch.dict(os.environ, {
            "UNRELATED_PRIVATE_SETTING": "should-not-be-visible",
            "ORESLANG_BIN": "/opt/test-interpreter",
        }):
            with mock.patch.object(TREE.subprocess, "Popen") as launch:
                with mock.patch.object(TREE, "await_ready"):
                    TREE.spawn_worker(ROOT / "bin/generation-tree.py", ROOT,
                                      None, "child", "example", "local-admission")
                    env = launch.call_args.kwargs["env"]
        self.assertNotIn("UNRELATED_PRIVATE_SETTING", env)
        self.assertEqual(env["ORESLANG_BIN"], "/opt/test-interpreter")
        self.assertEqual(env["ORES_DEV_HEALTH_TOKEN"], "local-admission")
        self.assertEqual(env["ORES_DEV_ROOT"], str(ROOT))

    def test_unambiguous_request_framing_and_target(self):
        invalid=[
            (request([("Transfer-Encoding","")]), 400),
            (request([("Transfer-Encoding","chunked")]), 400),
            (request([("Content-Length","0"),("Content-Length","0")]), 400),
            (request([("Content-Length","0, 0")]), 400),
            (request([("Content-Length","-1")]), 400),
            (request([("Content-Length","262145")]), 413),
            (request(path="http://example.invalid/private"), 400),
            (request(path="//example.invalid/private"), 400),
        ]
        for fake,status in invalid:
            with self.subTest(headers=fake.headers.items(),target=fake.path):
                returned,headers,body=TREE.forwarded(9,fake,"secret")
                self.assertEqual(returned,status)
                self.assertFalse(headers)
                self.assertTrue(body)

if __name__=="__main__":
    unittest.main()
