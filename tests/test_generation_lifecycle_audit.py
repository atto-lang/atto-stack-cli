#!/usr/bin/env python3
"""Reload identity and teardown regression tests for the shared development supervisor."""
import http.client
import importlib.util
import json
import os
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "generation-tree.py"
SPEC = importlib.util.spec_from_file_location("generation_lifecycle_supervisor", SCRIPT)
TREE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TREE)


class IdempotentProcessGroupStop(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX-only process groups")
    def test_stopping_the_same_exited_leader_twice_never_resignals_its_group(self):
        proc = types.SimpleNamespace(pid=999001, wait=lambda timeout: 0)
        with mock.patch.object(TREE.os, "killpg") as kill:
            TREE.stop(proc)
            TREE.stop(proc)
        self.assertEqual(kill.call_args_list, [
            mock.call(999001, signal.SIGTERM),
            mock.call(999001, signal.SIGKILL),
        ])

    @unittest.skipUnless(os.name == "posix", "POSIX-only process groups")
    def test_retirement_and_shutdown_race_still_signal_group_only_once(self):
        proc = types.SimpleNamespace(pid=999002, wait=lambda timeout: 0)
        barrier = threading.Barrier(12)
        errors = []
        def retire():
            try:
                barrier.wait(timeout=4)
                TREE.stop(proc)
            except Exception as exc:
                errors.append(exc)
        with mock.patch.object(TREE.os, "killpg") as kill:
            threads = [threading.Thread(target=retire) for _ in range(12)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=5)
        self.assertFalse(errors, errors)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(kill.call_count, 2, "concurrent callers signaled a recycled group")



class ErrorIncarnationContract(unittest.TestCase):
    def test_proxy_transport_failure_still_reports_admitted_generation(self):
        handler = object.__new__(TREE.Worker)
        handler.path = "/a"
        handler.server = types.SimpleNamespace(state={
            "mode": "grandaddy", "token": "test-token",
            "lock": threading.Lock(),
            "daddy": (types.SimpleNamespace(), 8123),
            "children": {"/a": (types.SimpleNamespace(), 8124)},
            "daddy_generation": 3,
            "child_generations": {"/a": 7}
        })
        handler.send = mock.Mock()
        with mock.patch.object(TREE, "forwarded", side_effect=ConnectionRefusedError):
            handler.dispatch()
        status, headers, body = handler.send.call_args.args
        self.assertEqual(status, 502)
        self.assertEqual(headers["X-Ores-Generation"], "d3:c7")
        self.assertEqual(headers["X-Ores-Grandaddy-PID"], str(os.getpid()))
        self.assertEqual(body, b"middleware unavailable")



@unittest.skipUnless(os.name == "posix", "supervisor requires POSIX")
class SettledGenerationContract(unittest.TestCase):
    def exercise(self, language):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            middleware = root / "src/middleware/middleware.txt"
            route = root / "src/routes/a" / ("route.ores" if language == "oreslang" else "route.rs")
            sibling = root / "src/routes/b" / route.name
            for f in (middleware, route, sibling):
                f.parent.mkdir(parents=True, exist_ok=True)
            middleware.write_text("middleware-v1")
            route.write_text("a-v1")
            sibling.write_text("b-v1")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            (root / "dev-tree.json").write_text(json.dumps({
                "schema": "ores.dev.generations/v1",
                "port": port,
                "fixture_echo": True,
                "middleware": "src/middleware",
                "routes": [
                    {"path": "/a", "dir": "src/routes/a"},
                    {"path": "/b", "dir": "src/routes/b"}
                ]
            }))
            proc = subprocess.Popen(
                [sys.executable, str(SCRIPT), "--root", str(root), "--language", language],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True
            )
            errors = ""
            try:
                ready = proc.stdout.readline()
                self.assertTrue(ready, "grandaddy failed startup")
                self.assertEqual(json.loads(ready)["grandaddy_pid"], proc.pid)

                def query(path):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                    try:
                        connection.request("GET", path)
                        response = connection.getresponse()
                        body = response.read()
                        return response.status, dict(response.getheaders()), body
                    finally:
                        connection.close()

                def snapshot(path):
                    status, headers, body = query(path)
                    self.assertEqual(status, 200)
                    return (
                        headers["X-Ores-Generation"],
                        headers["X-Ores-Grandaddy-PID"],
                        headers["X-Ores-Daddy-PID"],
                        headers["X-Ores-Child-PID"],
                        body
                    )

                a0, b0 = snapshot("/a"), snapshot("/b")
                self.assertEqual(a0[0], "d0:c0")
                self.assertEqual(b0[0], "d0:c0")

                # This specifically guards against the previously observed
                # unexpected *second* route-child restart without another edit.
                for _ in range(12):
                    time.sleep(.15)
                    self.assertEqual(snapshot("/a"), a0)
                    self.assertEqual(snapshot("/b"), b0)

                for value, expected in (("a-v2", "d0:c1"), ("a-v3", "d0:c2")):
                    route.write_text(value)
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        time.sleep(.15)
                        candidate = snapshot("/a")
                        if candidate[4] == value.encode():
                            break
                    else:
                        self.fail("edited route never admitted " + value)
                    self.assertEqual(candidate[0], expected)
                    self.assertEqual(candidate[1:3], a0[1:3])
                    self.assertNotEqual(candidate[3], a0[3])
                    self.assertEqual(snapshot("/b"), b0)
                    a0 = candidate

                # Keep polling *past* retirement's four-second drain window;
                # a delayed extra restart changes both PID and incarnation.
                deadline = time.monotonic() + 5.2
                while time.monotonic() < deadline:
                    self.assertEqual(snapshot("/a"), a0,
                        "child restarted without a source change")
                    self.assertEqual(snapshot("/b"), b0,
                        "unrelated child or middleware restarted")
                    time.sleep(.15)

                middleware.write_text("middleware-v2")
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    time.sleep(.15)
                    updated_a = snapshot("/a")
                    if updated_a[0] == "d1:c2":
                        break
                else:
                    self.fail("middleware never admitted its new generation")
                updated_b = snapshot("/b")
                self.assertEqual(updated_b[0], "d1:c0")
                self.assertEqual(updated_a[1], a0[1])
                self.assertNotEqual(updated_a[2], a0[2])
                self.assertEqual(updated_a[3], a0[3])
                self.assertEqual(updated_b[3], b0[3])
                self.assertIsNone(proc.poll())
            finally:
                proc.terminate()
                try:
                    _, errors = proc.communicate(timeout=7)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, errors = proc.communicate()
                if sys.exc_info()[0] is not None:
                    print("generation lifecycle diagnostics:", errors[-5000:],
                          file=sys.stderr)
            self.assertEqual(proc.returncode, 0, errors[-3000:])

    def test_rust_idle_and_consecutive_edits_remain_stable(self):
        self.exercise("rust")

    def test_oreslang_idle_and_consecutive_edits_remain_stable(self):
        self.exercise("oreslang")


if __name__ == "__main__":
    unittest.main()
