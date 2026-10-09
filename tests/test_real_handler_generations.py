#!/usr/bin/env python3
"""Prove modified Rust binaries/Oreslang guest source, not echoed text, hot-load."""
import http.client
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "bin/generation-tree.py"
WORKER = ROOT / "tests/source_worker_fixture.py"

def source_for(lang, value):
    if lang == "rust":
        return 'fn main() { println!("' + value + '"); }\n'
    return 'pub routine main(): void { stdio.println("' + value + '"); return; }\n'

class RealLanguageWorkerContract(unittest.TestCase):
    def exercise(self, language):
        suffix = "rs" if language == "rust" else "ores"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            for folder in ("src/routes/a","src/routes/b","src/middleware","tools"):
                (root / folder).mkdir(parents=True,exist_ok=True)
            shutil.copyfile(WORKER,root/"tools/worker.py")
            route_a=root/"src/routes/a"/("route."+suffix)
            route_b=root/"src/routes/b"/("route."+suffix)
            middleware=root/"src/middleware"/("middleware."+suffix)
            route_a.write_text(source_for(language,"a-v1"))
            route_b.write_text(source_for(language,"b-v1"))
            middleware.write_text(source_for(language,"middleware-v1"))
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port=sock.getsockname()[1]
            def argv(role, basename):
                return [sys.executable,"tools/worker.py","--mode",role,
                        "--language",language,"--source","{source_dir}/"+basename]
            config={
                "schema":"ores.dev.generations/v1","port":port,
                "middleware":"src/middleware",
                "daddy_argv":argv("daddy","middleware."+suffix),
                "routes":[
                    {"path":"/a","dir":"src/routes/a","argv":argv("child","route."+suffix)},
                    {"path":"/b","dir":"src/routes/b","argv":argv("child","route."+suffix)},
                ],
            }
            (root/"dev-tree.json").write_text(json.dumps(config))
            process=subprocess.Popen([sys.executable,str(SUPERVISOR),"--root",str(root),
                                      "--language",language],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
            try:
                initial=process.stdout.readline().strip()
                if not initial:
                    try: process.wait(timeout=4)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=4)
                    self.fail("language worker supervisor failed: " + process.stderr.read()[-3000:])
                admission=json.loads(initial)
                self.assertFalse(admission["fixture_echo"])
                self.assertEqual(admission["grandaddy_pid"],process.pid)
                def request(path):
                    conn=http.client.HTTPConnection("127.0.0.1",port,timeout=3)
                    try:
                        conn.request("GET",path)
                        response=conn.getresponse()
                        return response.status,dict(response.getheaders()),response.read()
                    finally: conn.close()
                def snap(path):
                    status,headers,body=request(path)
                    self.assertEqual(status,200)
                    return (
                        (headers["X-Ores-Grandaddy-PID"],
                         headers["X-Ores-Daddy-PID"],headers["X-Ores-Child-PID"]),
                        body,headers["X-Ores-Middleware-Version"]
                    )
                a,v,m=snap("/a")
                b,w,n=snap("/b")
                self.assertEqual(v,b"a-v1")
                self.assertEqual(w,b"b-v1")
                self.assertEqual(m,"middleware-v1")
                self.assertEqual(a[:2],b[:2])
                # Invalid guest code must never replace the working child.
                route_a.write_text("this is not valid " + language + " source\n")
                time.sleep(1.4)
                still,body,_=snap("/a")
                self.assertEqual(still,a)
                self.assertEqual(body,b"a-v1")
                self.assertEqual(snap("/b")[0],b)
                # Recovery compiles/executes new code and swaps only route A.
                route_a.write_text(source_for(language,"a-v2"))
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    time.sleep(.2)
                    current,body,_=snap("/a")
                    if body==b"a-v2": break
                else: self.fail("valid changed source never produced a new route child")
                self.assertEqual(current[:2],a[:2])
                self.assertNotEqual(current[2],a[2])
                self.assertEqual(snap("/b")[0],b)
                # Wait beyond the old-generation drain period; this is a
                # stability assertion, not a way to ignore a second restart.
                time.sleep(1.1)
                settled, settled_body, _ = snap("/a")
                self.assertEqual(settled, current,
                    "route child restarted a second time without new source")
                self.assertEqual(settled_body,b"a-v2")
                # Middleware change recompiles/reexecutes only daddy source.
                middleware.write_text(source_for(language,"middleware-v2"))
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    time.sleep(.2)
                    now,_,label=snap("/a")
                    if label=="middleware-v2": break
                else: self.fail("changed middleware source never replaced daddy")
                self.assertEqual(now[0],a[0])
                self.assertNotEqual(now[1],a[1])
                self.assertEqual(now[2],current[2])
                self.assertEqual(snap("/b")[0][2],b[2])
                self.assertEqual(request("/missing")[0],404)
            finally:
                process.terminate()
                try: _,stderr=process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    _,stderr=process.communicate()
                if sys.exc_info()[0] is not None:
                    print("generation diagnostics:", stderr[-8000:], file=sys.stderr)
            self.assertEqual(process.returncode,0,stderr[-1500:])

    @unittest.skipUnless(shutil.which("rustc"),"rustc required for real Rust binaries")
    def test_compiled_rust_worker_reload(self):
        self.exercise("rust")

    @unittest.skipUnless(os.environ.get("ORESLANG_BIN"),"ORESLANG_BIN real Java/Graal launcher required")
    def test_executed_oreslang_worker_reload(self):
        self.exercise("oreslang")

if __name__=="__main__":
    unittest.main()
