#!/usr/bin/env python3
"""Opt-in loopback grandaddy/daddy/child process tree for .rs and .ores routes.

Runs configured HTTP worker commands. fixture_echo deliberately DOES NOT
interpret Rust or Oreslang source; it tests PID/generation/HTTP isolation.
No shell=True and no external host binding. Not a hostile-tenant sandbox.
"""
import argparse
import hashlib
import http.client
import http.server
import json
import os
import pathlib
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.parse

SCHEMA = "ores.dev.generations/v1"
POLL = .15
MAX_FILES = 4000
MAX_BYTES = 4 * 1024 * 1024

def fail(s):
    raise ValueError(s)

def safe_relative(root, rel, directory=False):
    if not isinstance(rel, str) or not rel or "\\" in rel or "\x00" in rel:
        fail("invalid relative path")
    p = pathlib.PurePosixPath(rel)
    if p.is_absolute() or any(x in (".", "..") for x in p.parts):
        fail("path must remain within project")
    current = root
    for part in p.parts:
        current /= part
        if stat.S_ISLNK(current.lstat().st_mode):
            fail("symlinked source path: " + rel)
    if directory and not current.is_dir():
        fail("source directory missing: " + rel)
    return current

def digest_tree(root, rel, recursive=True):
    base = safe_relative(root, rel, True)
    entries = []
    count = 0
    for directory, dirs, files in os.walk(base, followlinks=False):
        if not recursive:
            dirs.clear()
        for name in dirs:
            if (pathlib.Path(directory) / name).is_symlink():
                fail("symlinked source directory")
        for name in sorted(files):
            p = pathlib.Path(directory) / name
            if not stat.S_ISREG(p.lstat().st_mode):
                fail("non-regular source file")
            count += 1
            if count > MAX_FILES or p.stat().st_size > MAX_BYTES:
                fail("watched source exceeds limits")
            entries.append((p.relative_to(base).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()))
        dirs.sort()
    return hashlib.sha256(json.dumps(sorted(entries)).encode()).hexdigest()

def load_config(root, language):
    config = json.loads(safe_relative(root, "dev-tree.json").read_text())
    if not isinstance(config, dict) or set(config) - {"schema", "port", "middleware", "routes", "fixture_echo", "daddy_argv"}:
        fail("unknown dev-tree configuration")
    if config.get("schema") != SCHEMA:
        fail("invalid dev-tree schema")
    port = config.get("port", 8088)
    if type(port) is not int or not 1024 <= port <= 65535:
        fail("port must be an unprivileged TCP port")
    middleware = config.get("middleware")
    safe_relative(root, middleware, True)
    routes = config.get("routes")
    if not isinstance(routes, list) or not 1 <= len(routes) <= 64:
        fail("expected 1..64 route entries")
    selected = {}
    for row in routes:
        if not isinstance(row, dict) or set(row) - {"path", "dir", "argv"}:
            fail("invalid route entry")
        path = row.get("path")
        if not isinstance(path, str) or not path.startswith("/") or ".." in path or "?" in path or "#" in path or "\x00" in path:
            fail("invalid HTTP route")
        if path in selected or path.startswith("/__ores_"):
            fail("duplicate or reserved route")
        directory = row.get("dir")
        folder = safe_relative(root, directory, True)
        leaf = "route.ores" if language == "oreslang" else "route.rs"
        if not (folder / leaf).is_file() or (folder / leaf).is_symlink():
            fail("missing authored " + leaf + " in route folder")
        command = row.get("argv")
        if command is not None and (not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command)):
            fail("route argv must be nonempty array of strings")
        selected[path] = {"dir": directory, "argv": command}
    daddy = config.get("daddy_argv")
    if daddy is not None and (not isinstance(daddy, list) or not daddy or not all(isinstance(x, str) and x for x in daddy)):
        fail("daddy_argv must be nonempty array of strings")
    fixture = config.get("fixture_echo", False)
    if type(fixture) is not bool:
        fail("fixture_echo must be boolean")
    if not fixture and (not daddy or any(x["argv"] is None for x in selected.values())):
        fail("production worker mode requires explicit daddy_argv and route argv")
    return config, port, middleware, selected

def ephemeral_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass

def await_ready(port, proc, token):
    for _ in range(75):
        if proc.poll() is not None:
            fail("worker exited before readiness")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=.2)
            conn.request("GET", "/__ores_health", headers={"X-Ores-Dev-Token": token})
            response = conn.getresponse()
            body = response.read()
            conn.close()
            if response.status == 200 and body == b"OK":
                return
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(.04)
    fail("worker readiness deadline exceeded")

def spawn_worker(script, root, argv, mode, marker, token, source_dir=None):
    port = ephemeral_port()
    if argv is None:
        cmd = [sys.executable, str(script), "--internal", mode, "--worker-port",
               str(port), "--token", token, "--marker", marker]
    else:
        values = {"{port}": str(port), "{root}": str(root), "{source_dir}": str(root / (source_dir or marker))}
        cmd = []
        for arg in argv:
            for k, v in values.items():
                arg = arg.replace(k, v)
            cmd.append(arg)
    env = {**os.environ, "ORES_DEV_PORT": str(port), "ORES_DEV_HEALTH_TOKEN": token,
           "ORES_DEV_ROOT": str(root)}
    proc = subprocess.Popen(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=(os.name == "posix"))
    try:
        await_ready(port, proc, token)
    except Exception:
        stop(proc)
        raise
    return proc, port

def forwarded(port, handler, token, child_port=None):
    size = int(handler.headers.get("Content-Length", "0"))
    if not 0 <= size <= 256 * 1024:
        return 413, {}, b"request body too large"
    payload = handler.rfile.read(size) if size else b""
    headers = {k:v for k,v in handler.headers.items()
               if k.lower() not in ("host", "connection", "content-length",
                                    "x-ores-dev-token", "x-ores-dev-target-port")}
    headers["X-Ores-Dev-Token"] = token
    if child_port is not None:
        headers["X-Ores-Dev-Target-Port"] = str(child_port)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(handler.command, handler.path, body=payload, headers=headers)
        response = conn.getresponse()
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            return 502, {}, b"worker response too large"
        excluded = ("connection", "transfer-encoding", "content-length", "server", "date")
        return response.status, {k:v for k,v in response.getheaders()
                                 if k.lower() not in excluded}, body
    finally:
        conn.close()

class HttpService(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class Worker(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self): self.dispatch()
    def do_POST(self): self.dispatch()
    def do_PUT(self): self.dispatch()
    def do_PATCH(self): self.dispatch()
    def do_DELETE(self): self.dispatch()
    def do_HEAD(self): self.dispatch()
    def do_OPTIONS(self): self.dispatch()
    def send(self, status, headers, body):
        self.send_response(status)
        for k,v in headers.items(): self.send_header(k,v)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)
    def dispatch(self):
        state = self.server.state
        if state["mode"] != "grandaddy" and self.headers.get("X-Ores-Dev-Token") != state["token"]:
            return self.send(403, {}, b"worker authorization refused")
        if self.path == "/__ores_health" and state["mode"] != "grandaddy":
            return self.send(200, {}, b"OK")
        if state["mode"] == "child":
            return self.send(200, {"X-Ores-Child-PID": str(os.getpid())}, state["marker"].encode())
        if state["mode"] == "daddy":
            child_port = self.headers.get("X-Ores-Dev-Target-Port", "")
            if not child_port.isascii() or not child_port.isdecimal() or not 1024 <= int(child_port) <= 65535:
                return self.send(400, {}, b"bad child target")
            try: status, headers, body = forwarded(int(child_port), self, state["token"])
            except Exception: return self.send(502, {}, b"child unavailable")
            headers["X-Ores-Daddy-PID"] = str(os.getpid())
            headers["X-Ores-Middleware-Hash"] = state["marker"]
            return self.send(status, headers, body)
        with state["lock"]:
            item = state["children"].get(urllib.parse.urlsplit(self.path).path)
            daddy = state["daddy"]
        if item is None: return self.send(404, {}, b"route not found")
        try: status, headers, body = forwarded(daddy[1], self, state["token"], item[1])
        except Exception: return self.send(502, {}, b"middleware unavailable")
        headers["X-Ores-Grandaddy-PID"] = str(os.getpid())
        return self.send(status, headers, body)

def monitor(state, script, root, middleware, routes, fixture):
    last_m = state["initial_middleware"]
    last = dict(state["initial_routes"])
    pending = {}
    while not state["stop"].wait(POLL):
        try:
            current_m = digest_tree(root, middleware)
            current = {route:digest_tree(root, row["dir"], False) for route,row in routes.items()}
        except Exception as exc:
            print("grandaddy: rejected source snapshot:", exc, file=sys.stderr, flush=True)
            continue
        now = time.monotonic()
        changes = [("daddy", last_m, current_m)] + [
            (route, last[route], current[route]) for route in routes
        ]
        for key, before, after in changes:
            if before == after:
                pending.pop(key, None)
                continue
            if key not in pending or pending[key][0] != after:
                pending[key] = (after, now)
                continue
            if now - pending[key][1] < .3:
                continue
            try:
                if key == "daddy":
                    new = spawn_worker(script, root, None if fixture else state["daddy_argv"],
                                       "daddy", after, state["token"], middleware)
                    with state["lock"]:
                        old = state["daddy"]
                        state["daddy"] = new
                    last_m = after
                else:
                    row = routes[key]
                    leaf = "route.ores" if state["lang"] == "oreslang" else "route.rs"
                    marker = (root / row["dir"] / leaf).read_text()[:256].strip() if fixture else row["dir"]
                    new = spawn_worker(script, root, None if fixture else row["argv"],
                                       "child", marker, state["token"], row["dir"])
                    with state["lock"]:
                        old = state["children"][key]
                        state["children"][key] = new
                    last[key] = after
                threading.Thread(target=lambda p:(time.sleep(.6), stop(p)),
                                 args=(old[0],), daemon=True).start()
                print("grandaddy: reloaded", key, "old", old[0].pid, "new", new[0].pid, flush=True)
                pending.pop(key, None)
            except Exception as exc:
                print("grandaddy: reload refused", key, exc, file=sys.stderr, flush=True)
                pending[key] = (after, now)

def supervise(args):
    if os.name != "posix":
        fail("process-group lifecycle requires POSIX")
    root = pathlib.Path(args.root).resolve(strict=True)
    config, port, middleware, routes = load_config(root, args.language)
    token = os.urandom(24).hex()
    script = pathlib.Path(__file__).resolve()
    state = {"mode":"grandaddy", "token":token, "children":{}, "daddy":None,
             "daddy_argv":config.get("daddy_argv"), "lang":args.language,
             "stop":threading.Event(), "lock":threading.Lock()}
    started = []
    try:
        mhash = digest_tree(root, middleware)
        state["initial_middleware"] = mhash
        state["initial_routes"] = {route:digest_tree(root,row["dir"],False) for route,row in routes.items()}
        state["daddy"] = spawn_worker(script, root,
             None if config.get("fixture_echo") else config["daddy_argv"],
             "daddy", mhash, token, middleware)
        started.append(state["daddy"][0])
        for route,row in routes.items():
            leaf = "route.ores" if args.language == "oreslang" else "route.rs"
            marker = (root / row["dir"] / leaf).read_text()[:256].strip() if config.get("fixture_echo") else row["dir"]
            child = spawn_worker(script, root,
                None if config.get("fixture_echo") else row["argv"],
                "child", marker, token, row["dir"])
            state["children"][route] = child
            started.append(child[0])
        httpd = HttpService(("127.0.0.1", port), Worker)
        httpd.state = state
        threading.Thread(target=monitor,
             args=(state,script,root,middleware,routes,config.get("fixture_echo")),
             daemon=True).start()
        def shutdown(signum, frame):
            state["stop"].set()
            threading.Thread(target=httpd.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        print(json.dumps({"schema":SCHEMA,"grandaddy_pid":os.getpid(),"port":port,
              "daddy_pid":state["daddy"][0].pid,
              "children":{route:child[0].pid for route,child in state["children"].items()},
              "fixture_echo":bool(config.get("fixture_echo"))}), flush=True)
        httpd.serve_forever(poll_interval=.1)
        httpd.server_close()
    finally:
        state["stop"].set()
        with state["lock"]:
            running = [state["daddy"]] + list(state["children"].values())
        for item in running:
            if item: stop(item[0])
        for proc in started: stop(proc)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--language", choices=["oreslang","rust"], default="oreslang")
    parser.add_argument("--internal", choices=["child","daddy"])
    parser.add_argument("--worker-port", type=int)
    parser.add_argument("--token")
    parser.add_argument("--marker")
    args = parser.parse_args()
    if args.internal:
        if not args.token or not args.marker or not args.worker_port or not 1024 <= args.worker_port < 65536:
            fail("invalid internal worker arguments")
        server = HttpService(("127.0.0.1", args.worker_port), Worker)
        server.state = {"mode":args.internal,"token":args.token,"marker":args.marker}
        server.serve_forever()
    else:
        supervise(args)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("ores dev generation tree:", exc, file=sys.stderr)
        sys.exit(2)
