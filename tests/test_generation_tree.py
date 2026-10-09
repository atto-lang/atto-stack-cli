#!/usr/bin/env python3
"""Real HTTP/PID contract for the opt-in Oreslang/Rust three-generation host."""
import http.client
import json
import os
import signal
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "bin" / "generation-tree.py"

class GenerationalReloadContract(unittest.TestCase):
    def exercise(self, language):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "src/middleware").mkdir(parents=True)
            (root / "src/routes/one").mkdir(parents=True)
            (root / "src/routes/two").mkdir(parents=True)
            (root / "src/middleware/middleware.txt").write_text("alpha")
            ext = "ores" if language == "oreslang" else "rs"
            first = root / "src/routes/one" / ("route." + ext)
            second = root / "src/routes/two" / ("route." + ext)
            first.write_text("one-v1")
            second.write_text("two-v1")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            settings = {
                "schema": "ores.dev.generations/v1",
                "port": port,
                "middleware": "src/middleware",
                "fixture_echo": True,
                "routes": [
                    {"path": "/one", "dir": "src/routes/one"},
                    {"path": "/two", "dir": "src/routes/two"},
                ]
            }
            (root / "dev-tree.json").write_text(json.dumps(settings))
            proc = subprocess.Popen(
                [sys.executable, str(SCRIPT), "--root", str(root), "--language", language],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                header = proc.stdout.readline().strip()
                self.assertTrue(header, "grandaddy failed to start")
                admission = json.loads(header)
                self.assertEqual(admission["schema"], "ores.dev.generations/v1")
                self.assertEqual(admission["grandaddy_pid"], proc.pid)
                self.assertTrue(admission["fixture_echo"])
                def request(path):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                    try:
                        connection.request("GET", path)
                        response = connection.getresponse()
                        return response.status, dict(response.getheaders()), response.read()
                    finally:
                        connection.close()
                def snap(path):
                    status, hdr, body = request(path)
                    self.assertEqual(status, 200)
                    pids = tuple(hdr.get(k) for k in (
                        "X-Ores-Grandaddy-PID", "X-Ores-Daddy-PID", "X-Ores-Child-PID"))
                    self.assertTrue(all(pids))
                    return pids, body, hdr.get("X-Ores-Middleware-Hash")
                p1, body1, m1 = snap("/one")
                p2, body2, m2 = snap("/two")
                self.assertEqual(body1, b"one-v1")
                self.assertEqual(body2, b"two-v1")
                self.assertEqual(p1[:2], p2[:2])
                self.assertEqual(request("/unknown")[0], 404)
                # Ambiguous request framing must fail before proxying to daddy.
                with socket.create_connection(("127.0.0.1", port), timeout=2) as raw:
                    raw.sendall(
                        b"GET /one HTTP/1.1\r\nHost: localhost\r\n"
                        b"Content-Length: 1\r\nContent-Length: 2\r\n\r\n"
                    )
                    self.assertIn(b" 400 ", raw.recv(128))
                with socket.create_connection(("127.0.0.1", port), timeout=2) as raw:
                    raw.sendall(
                        b"GET /one HTTP/1.1\r\nHost: localhost\r\n"
                        b"Transfer-Encoding: chunked\r\n\r\n"
                    )
                    self.assertIn(b" 400 ", raw.recv(128))
                self.assertEqual(request("/" + "x" * 3000)[0], 414)
                self.assertEqual(snap("/one")[0], p1)
                # Only the directly affected route child rotates.
                first.write_text("one-v2")
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    time.sleep(.15)
                    changed, body, middleware = snap("/one")
                    if body == b"one-v2":
                        break
                else:
                    self.fail("route child did not reload")
                self.assertEqual(changed[:2], p1[:2], "grandaddy or daddy restarted on route edit")
                self.assertNotEqual(changed[2], p1[2], "route child PID never changed")
                unchanged, old_body, old_hash = snap("/two")
                self.assertEqual(unchanged, p2)
                self.assertEqual(old_body, b"two-v1")
                self.assertEqual(old_hash, m2)
                # Middleware rotates daddy, not grandaddy or either child.
                (root / "src/middleware/middleware.txt").write_text("beta")
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    time.sleep(.15)
                    after, _, new_hash = snap("/one")
                    if after[1] != changed[1]:
                        break
                else:
                    self.fail("middleware daddy never reloaded")
                self.assertEqual(after[0], p1[0])
                self.assertEqual(after[2], changed[2])
                self.assertEqual(snap("/two")[0][2], p2[2])
                self.assertNotEqual(m1, new_hash)
                # OTP-style child failure restarts only the failed leaf.
                os.kill(int(after[2]), signal.SIGKILL)
                deadline = time.monotonic() + 9
                while time.monotonic() < deadline:
                    time.sleep(.15)
                    status, hdr, body = request("/one")
                    recovered = (
                        hdr.get("X-Ores-Grandaddy-PID"),
                        hdr.get("X-Ores-Daddy-PID"),
                        hdr.get("X-Ores-Child-PID"))
                    if status == 200 and recovered[2] != after[2]:
                        break
                else:
                    self.fail("crashed route child did not restart")
                self.assertEqual(recovered[:2], after[:2])
                self.assertEqual(body, b"one-v2")
                self.assertEqual(snap("/two")[0][2], p2[2])
                # Daddy crash likewise preserves both route worker PIDs.
                os.kill(int(recovered[1]), signal.SIGKILL)
                deadline = time.monotonic() + 9
                while time.monotonic() < deadline:
                    time.sleep(.15)
                    status, hdr, body = request("/one")
                    restarted = (
                        hdr.get("X-Ores-Grandaddy-PID"),
                        hdr.get("X-Ores-Daddy-PID"),
                        hdr.get("X-Ores-Child-PID"))
                    if status == 200 and restarted[1] != recovered[1]:
                        break
                else:
                    self.fail("crashed middleware daddy did not restart")
                self.assertEqual(restarted[0], recovered[0])
                self.assertEqual(restarted[2], recovered[2])
                self.assertEqual(snap("/two")[0][2], p2[2])
                self.assertEqual(proc.poll(), None)
            finally:
                proc.terminate()
                try:
                    _, errors = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, errors = proc.communicate()
            self.assertEqual(proc.returncode, 0, errors[-1000:])

    def test_oreslang_route_local_replacement(self):
        self.exercise("oreslang")
    def test_rust_route_local_replacement(self):
        self.exercise("rust")
    def test_refuses_unadmitted_real_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root/"src/middleware").mkdir(parents=True)
            (root/"src/routes/x").mkdir(parents=True)
            (root/"src/routes/x/route.ores").write_text("pub fnc x(): void {}")
            (root/"dev-tree.json").write_text(json.dumps({
                "schema": "ores.dev.generations/v1", "port": 8123,
                "middleware": "src/middleware",
                "routes": [{"path":"/x","dir":"src/routes/x"}],
            }))
            p = subprocess.run([sys.executable,str(SCRIPT),"--root",str(root),
                                "--language","oreslang"],capture_output=True,text=True,timeout=4)
            self.assertNotEqual(p.returncode,0)
            self.assertIn("requires explicit",p.stderr)
    def test_refuses_symlinked_route_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            (root/"src/middleware").mkdir(parents=True)
            (root/"src/routes").mkdir(parents=True)
            (root/"escape").mkdir()
            (root/"escape/route.rs").write_text("source")
            (root/"src/routes/link").symlink_to(root/"escape",target_is_directory=True)
            (root/"dev-tree.json").write_text(json.dumps({
                "schema":"ores.dev.generations/v1","port":8123,
                "middleware":"src/middleware","fixture_echo":True,
                "routes":[{"path":"/x","dir":"src/routes/link"}]}))
            p=subprocess.run([sys.executable,str(SCRIPT),"--root",str(root),
                              "--language","rust"],capture_output=True,text=True,timeout=4)
            self.assertNotEqual(p.returncode,0)
            self.assertIn("symlink",p.stderr)

    def test_demo_method_file_get_ores_reloads_without_grandaddy_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            route = root / "src/routes/rest/health"
            route.mkdir(parents=True)
            (root / "src/middleware").mkdir(parents=True)
            (root / "src/middleware/auth.ores").write_text("middleware-v1")
            source = route / "get.ores"
            source.write_text("health-v1")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port = sock.getsockname()[1]
            (root/"dev-tree.json").write_text(json.dumps({
                "schema":"ores.dev.generations/v1", "port":port,
                "middleware":"src/middleware", "fixture_echo":True,
                "routes":[{"path":"/health", "dir":"src/routes/rest/health",
                           "source_file":"get.ores"}]
            }))
            proc=subprocess.Popen([sys.executable,str(SCRIPT),"--root",str(root),
                                   "--language","oreslang"],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                                   start_new_session=True)
            try:
                first_line=proc.stdout.readline()
                self.assertTrue(first_line)
                def query():
                    conn=http.client.HTTPConnection("127.0.0.1",port,timeout=3)
                    try:
                        conn.request("GET","/health")
                        resp=conn.getresponse()
                        return dict(resp.getheaders()),resp.read()
                    finally:conn.close()
                one,b=query()
                self.assertEqual(b,b"health-v1")
                source.write_text("health-v2")
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    time.sleep(.15)
                    two,body=query()
                    if body==b"health-v2":break
                else:self.fail("get.ores method source did not reload")
                self.assertEqual(one["X-Ores-Grandaddy-PID"],two["X-Ores-Grandaddy-PID"])
                self.assertEqual(one["X-Ores-Daddy-PID"],two["X-Ores-Daddy-PID"])
                self.assertNotEqual(one["X-Ores-Child-PID"],two["X-Ores-Child-PID"])
            finally:
                proc.terminate()
                try:proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.communicate()

if __name__=="__main__":
    unittest.main()
