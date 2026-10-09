#!/usr/bin/env python3
"""Test-only language-executing HTTP worker for generation-tree end-to-end proofs.

At startup, Rust is compiled with rustc and executed, or the Java/Graal
Oreslang runtime checks and executes a .ores entry. The resulting response
is served by an isolated loopback worker; the source is NEVER merely echoed.
Not a production HTTP middleware/actor implementation or a sandbox.
"""
import argparse
import http.client
import http.server
import os
import pathlib
import subprocess
import sys
import tempfile

def execute_source(source, language):
    if not source.is_file() or source.is_symlink():
        raise ValueError("source must be a regular non-symlink file")
    if source.suffix != (".rs" if language == "rust" else ".ores"):
        raise ValueError("language and source suffix mismatch")
    if language == "rust":
        with tempfile.TemporaryDirectory(prefix="ores-dev-rust-worker-") as tmp:
            executable = pathlib.Path(tmp) / "route-worker"
            build = subprocess.run(["rustc", "--edition=2024", "-O", str(source),
                                    "-o", str(executable)], capture_output=True,
                                   text=True, timeout=90)
            if build.returncode:
                raise ValueError("rustc refused route source: " + build.stderr[-1000:])
            command = [str(executable)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    else:
        compiler = os.environ.get("ORESLANG_BIN", "oreslang")
        check = subprocess.run([compiler, "--check", str(source)],
                               capture_output=True, text=True, timeout=30)
        if check.returncode:
            raise ValueError("Oreslang compiler refused source: " + check.stderr[-1000:])
        result = subprocess.run([compiler, str(source)],
                                capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError("guest route process failed: " + result.stderr[-1000:])
    value = result.stdout.strip()
    if len(value.encode()) > 65536:
        raise ValueError("guest output exceeded 64 KiB")
    return value

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self): self.respond()
    def do_POST(self): self.respond()
    def do_PUT(self): self.respond()
    def do_PATCH(self): self.respond()
    def do_DELETE(self): self.respond()
    def do_OPTIONS(self): self.respond()
    def do_HEAD(self): self.respond()
    def output(self, code, body, extras=None):
        self.send_response(code)
        for k, v in (extras or {}).items(): self.send_header(k,v)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)
    def respond(self):
        token = os.environ["ORES_DEV_HEALTH_TOKEN"]
        if self.headers.get("X-Ores-Dev-Token") != token:
            return self.output(403,b"worker not admitted")
        if self.path == "/__ores_health":
            return self.output(200,b"OK")
        if self.server.role == "child":
            return self.output(200,self.server.value.encode(),
                {"X-Ores-Child-PID":str(os.getpid())})
        child_port = self.headers.get("X-Ores-Dev-Target-Port", "")
        if not child_port.isascii() or not child_port.isdecimal() or not 1024 <= int(child_port) <= 65535:
            return self.output(400,b"unadmitted child target")
        conn = http.client.HTTPConnection("127.0.0.1",int(child_port),timeout=3)
        try:
            conn.request(self.command,self.path,headers={"X-Ores-Dev-Token":token})
            response = conn.getresponse()
            body = response.read(65537)
            if len(body)>65536:
                return self.output(502,b"response too large")
            extra = {"X-Ores-Daddy-PID":str(os.getpid()),
                     "X-Ores-Middleware-Version":self.server.value}
            child_pid = response.getheader("X-Ores-Child-PID")
            if child_pid: extra["X-Ores-Child-PID"]=child_pid
            return self.output(response.status,body,extra)
        finally:
            conn.close()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=["daddy","child"],required=True)
    ap.add_argument("--language",choices=["rust","oreslang"],required=True)
    ap.add_argument("--source",required=True)
    args=ap.parse_args()
    source=pathlib.Path(args.source).resolve(strict=True)
    value=execute_source(source,args.language)
    port=int(os.environ["ORES_DEV_PORT"])
    if not 1024<=port<=65535 or not os.environ.get("ORES_DEV_HEALTH_TOKEN"):
        raise ValueError("worker missing admission capability")
    s=Server(("127.0.0.1",port),Handler)
    s.role=args.mode
    s.value=value
    s.serve_forever()

if __name__=="__main__":
    try: main()
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as err:
        print("ores real-source worker:",err,file=sys.stderr)
        sys.exit(2)
