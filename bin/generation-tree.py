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
import tempfile
import threading
import time
import urllib.parse

SCHEMA = "ores.dev.generations/v1"
POLL = .15
MAX_FILES = 4000
MAX_BYTES = 4 * 1024 * 1024
# Worker argv is trusted project configuration, but its process must not
# automatically inherit the grandaddy's unrelated access keys or CI secrets.
WORKER_ENV_ALLOWLIST = (
    "PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE",
    "JAVA_HOME", "GRAALVM_HOME", "RUSTUP_HOME", "CARGO_HOME",
    "RUSTUP_TOOLCHAIN", "ORESLANG_BIN", "ORESLANG_JAVA_PROJECT",
    "PYTHONIOENCODING", "PYTHONUNBUFFERED"
)

def fail(s):
    raise ValueError(s)

def safe_relative(root, rel, directory=False):
    if not isinstance(rel, str) or not rel or "\\" in rel or "\x00" in rel:
        fail("invalid relative path")
    # PurePosixPath normalizes '.', empty segments, and repeated separators.
    # Reject those in the original text before constructing a filesystem path.
    if rel.startswith("/") or any(x in ("", ".", "..") for x in rel.split("/")):
        fail("path must remain within project")
    p = pathlib.PurePosixPath(rel)
    current = root
    for part in p.parts:
        current /= part
        if stat.S_ISLNK(current.lstat().st_mode):
            fail("symlinked source path: " + rel)
    if directory and not current.is_dir():
        fail("source directory missing: " + rel)
    return current

def digest_regular_file(path):
    # lstat() followed by read_bytes() is susceptible to a leaf symlink
    # replacement. Open the final component without following links and
    # enforce size/type bounds on the opened descriptor, not path metadata.
    options = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, options)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            fail("watched source must be a bounded regular file")
        data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or len(data) != info.st_size:
            fail("watched source changed size while scanning")
        return hashlib.sha256(data).hexdigest()

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
            if count > MAX_FILES:
                fail("watched source exceeds file-count limit")
            # Revalidate each path component before opening the leaf.
            safe_relative(root, p.relative_to(root).as_posix())
            entries.append((p.relative_to(base).as_posix(), digest_regular_file(p)))
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
        if not isinstance(row, dict) or set(row) - {"path", "dir", "argv", "source_file"}:
            fail("invalid route entry")
        path = row.get("path")
        if not isinstance(path, str) or not path.startswith("/") or ".." in path or "?" in path or "#" in path or "\x00" in path:
            fail("invalid HTTP route")
        if path in selected or path.startswith("/__ores_"):
            fail("duplicate or reserved route")
        directory = row.get("dir")
        folder = safe_relative(root, directory, True)
        default_leaf = "route.ores" if language == "oreslang" else "route.rs"
        leaf = row.get("source_file", default_leaf)
        candidates = ("route.ores", "get.ores", "post.ores", "put.ores", "patch.ores",
                      "delete.ores", "head.ores", "options.ores") if language == "oreslang" else ("route.rs",)
        if not isinstance(leaf, str) or leaf not in candidates:
            fail("unadmitted route source_file")
        if not (folder / leaf).is_file() or (folder / leaf).is_symlink():
            fail("missing authored " + leaf + " in route folder")
        command = row.get("argv")
        if command is not None and (not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command)):
            fail("route argv must be nonempty array of strings")
        selected[path] = {"dir": directory, "argv": command, "source_file": leaf}
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
    if proc is None:
        return
    # A worker can spawn compilers or actors and exit before its descendants.
    # Always terminate the owned process group, even when its leader is dead.
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        # Escalate for children that ignored TERM. The process group survives
        # its leader when descendants remain; a mere proc.poll() is insufficient.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    else:
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait(timeout=2)

def retire_worker(state, proc):
    # Allow a bounded in-flight drain, interrupted by grandaddy shutdown.
    state["stop"].wait(4)
    try:
        stop(proc)
    finally:
        with state["lock"]:
            if proc in state["retired"]:
                state["retired"].remove(proc)

def cleanup_workers(state, started):
    state["stop"].set()
    with state["lock"]:
        live = [state["daddy"]] + list(state["children"].values())
        retired = list(state["retired"])
    for item in live:
        if item:
            stop(item[0])
    for proc in set(started + retired):
        stop(proc)

def await_ready(port, proc, token):
    # Compiling cold Rust or Graal workers can exceed a 3-second probe window.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
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
        # Never put the internal bearer or source-derived marker in process argv.
        cmd = [sys.executable, str(script), "--internal", mode, "--worker-port",
               str(port)]
    else:
        values = {"{port}": str(port), "{root}": str(root), "{source_dir}": str(root / (source_dir or marker))}
        cmd = []
        for arg in argv:
            for k, v in values.items():
                arg = arg.replace(k, v)
            cmd.append(arg)
    env = {key: os.environ[key] for key in WORKER_ENV_ALLOWLIST if key in os.environ}
    env.update({"ORES_DEV_PORT": str(port), "ORES_DEV_HEALTH_TOKEN": token,
                "ORES_DEV_MARKER": marker, "ORES_DEV_ROOT": str(root)})
    with tempfile.TemporaryFile(mode="w+t",encoding="utf-8") as worker_log:
        proc = subprocess.Popen(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=worker_log,
                                start_new_session=(os.name == "posix"))
        try:
            await_ready(port, proc, token)
        except Exception as failure:
            stop(proc)
            worker_log.seek(0)
            detail = worker_log.read()[-1600:]
            raise ValueError("worker readiness denied: " + str(failure) +
                             ("; worker: " + detail if detail else "")) from failure
    return proc, port

def forwarded(port, handler, token, child_port=None):
    # Every request has exactly one unambiguous framing mode.
    if handler.headers.get_all("Transfer-Encoding", []):
        return 400, {}, b"transfer-encoding not admitted"
    if not handler.path.startswith("/") or handler.path.startswith("//"):
        return 400, {}, b"origin-form request target required"
    lengths = handler.headers.get_all("Content-Length", [])
    if len(lengths) > 1 or (lengths and (not lengths[0].isascii() or not lengths[0].isdecimal())):
        return 400, {}, b"invalid content-length"
    size = int(lengths[0]) if lengths else 0
    if not 0 <= size <= 256 * 1024:
        return 413, {}, b"request body too large"
    payload = handler.rfile.read(size) if size else b""
    if len(payload) != size:
        return 400, {}, b"incomplete request body"
    # Connection names additional hop-by-hop fields; do not forward those
    # even though the Connection header itself is removed.
    connection_names = {name.strip().lower() for line in handler.headers.get_all("Connection", [])
                        for name in line.split(",")}
    hop = {"host", "connection", "content-length", "transfer-encoding",
           "te", "trailer", "upgrade", "keep-alive", "proxy-connection",
           "proxy-authorization", "proxy-authenticate"}
    headers = {k:v for k,v in handler.headers.items()
               if k.lower() not in hop and k.lower() not in connection_names
               and not k.lower().startswith("x-ores-dev-")}
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
        # Never publish the internal bearer token or worker target headers.
        # Strip headers named by upstream Connection, not only static hop fields.
        upstream_headers = response.getheaders()
        connection_names = {name.strip().lower() for k,v in upstream_headers
                            if k.lower() == "connection" for name in v.split(",")}
        excluded = {"connection", "transfer-encoding", "content-length",
                    "server", "date", "te", "trailer", "upgrade",
                    "keep-alive", "proxy-connection", "proxy-authenticate",
                    "proxy-authorization"} | connection_names
        return response.status, {k:v for k,v in upstream_headers
                                 if k.lower() not in excluded
                                 and not k.lower().startswith("x-ores-dev-")}, body
    finally:
        conn.close()

class HttpService(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, *args, **kwargs):
        self._connections = threading.BoundedSemaphore(64)
        super().__init__(*args, **kwargs)

    def get_request(self):
        conn, address = super().get_request()
        conn.settimeout(5)
        return conn, address

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()

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
        if len(self.path) > 2048:
            return self.send(414, {}, b"URI too long")
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
            route_path = urllib.parse.urlsplit(self.path).path
            item = state["children"].get(route_path)
            daddy = state["daddy"]
            # A single immutable admission snapshot accompanies this request,
            # even if both middleware and route generations change in flight.
            incarnation = ("d" + str(state["daddy_generation"]) + ":c" +
                           str(state["child_generations"].get(route_path, 0)))
        if item is None: return self.send(404, {}, b"route not found")
        try: status, headers, body = forwarded(daddy[1], self, state["token"], item[1])
        except Exception: return self.send(502, {}, b"middleware unavailable")
        headers["X-Ores-Grandaddy-PID"] = str(os.getpid())
        headers["X-Ores-Generation"] = incarnation
        return self.send(status, headers, body)

def monitor(state, script, root, middleware, routes, fixture):
    last_m = state["initial_middleware"]
    last = dict(state["initial_routes"])
    pending = {}
    restart_history = {}
    while not state["stop"].wait(POLL):
        try:
            current_m = digest_tree(root, middleware)
            current = {route:digest_tree(root, row["dir"], False) for route,row in routes.items()}
        except Exception as exc:
            print("grandaddy: rejected source snapshot:", exc, file=sys.stderr, flush=True)
            continue
        now = time.monotonic()
        with state["lock"]:
            workers = {"daddy": state["daddy"], **state["children"]}
        changes = [("daddy", last_m, current_m)] + [
            (route, last[route], current[route]) for route in routes
        ]
        for key, before, after in changes:
            # An OTP-style worker crash rotates its own generation. A crashed
            # daddy does not invalidate healthy route children or grandaddy.
            dead = workers[key][0].poll() is not None
            if before == after and not dead:
                pending.pop(key, None)
                continue
            intended = (after, dead)
            if key not in pending or pending[key][0] != intended:
                print("grandaddy: candidate", key, "reason", "worker-exit" if dead else "source-drift",
                      "exit", workers[key][0].returncode, "pid", workers[key][0].pid,
                      "from", before[:12], "to", after[:12], file=sys.stderr, flush=True)
                # A new source digest gets a fresh admission budget even if
                # the previous source repeatedly failed compilation.
                if before != after and (key not in pending or pending[key][0][0] != after):
                    restart_history[key] = []
                pending[key] = (intended, now)
                continue
            if now - pending[key][1] < .3:
                continue
            recent = [t for t in restart_history.get(key, []) if now - t < 11]
            restart_history[key] = recent
            if len(recent) >= 3:
                continue
            # Failed worker admission consumes a restart budget too.
            recent.append(now)
            try:
                if key == "daddy":
                    new = spawn_worker(script, root, None if fixture else state["daddy_argv"],
                                       "daddy", after, state["token"], middleware)
                    if state["stop"].is_set():
                        stop(new[0])
                        return
                    # Only promote the generation whose exact watched source
                    # fingerprint was admitted. Source can change while a
                    # guest compiler warms up or an invalid build fails.
                    if digest_tree(root, middleware) != after:
                        stop(new[0])
                        raise ValueError("middleware changed during worker admission")
                    with state["lock"]:
                        old = state["daddy"]
                        state["daddy"] = new
                        state["retired"].append(old[0])
                        state["daddy_generation"] += 1
                    last_m = after
                else:
                    row = routes[key]
                    leaf = row["source_file"]
                    marker = (root / row["dir"] / leaf).read_text()[:256].strip() if fixture else row["dir"]
                    new = spawn_worker(script, root, None if fixture else row["argv"],
                                       "child", marker, state["token"], row["dir"])
                    if state["stop"].is_set():
                        stop(new[0])
                        return
                    if digest_tree(root, row["dir"], False) != after:
                        stop(new[0])
                        raise ValueError("route changed during worker admission")
                    with state["lock"]:
                        old = state["children"][key]
                        state["children"][key] = new
                        state["retired"].append(old[0])
                        state["child_generations"][key] += 1
                    last[key] = after
                threading.Thread(target=retire_worker, args=(state, old[0]),
                                 daemon=True).start()
                print("grandaddy: reloaded", key, "old", old[0].pid,
                      "new", new[0].pid, "hash", after[:12],
                      file=sys.stderr, flush=True)
                pending.pop(key, None)
            except Exception as exc:
                print("grandaddy: reload refused", key, exc, file=sys.stderr, flush=True)
                pending[key] = (intended, now)

def supervise(args):
    if os.name != "posix":
        fail("process-group lifecycle requires POSIX")
    root = pathlib.Path(args.root).resolve(strict=True)
    config, port, middleware, routes = load_config(root, args.language)
    token = os.urandom(24).hex()
    script = pathlib.Path(__file__).resolve()
    state = {"mode":"grandaddy", "token":token, "children":{}, "daddy":None,
             "daddy_argv":config.get("daddy_argv"), "lang":args.language,
             "daddy_generation":0, "child_generations":{route:0 for route in routes},
             "stop":threading.Event(), "lock":threading.Lock(), "retired":[]}
    started = []
    watcher = None
    try:
        mhash = digest_tree(root, middleware)
        state["initial_middleware"] = mhash
        state["initial_routes"] = {route:digest_tree(root,row["dir"],False) for route,row in routes.items()}
        state["daddy"] = spawn_worker(script, root,
             None if config.get("fixture_echo") else config["daddy_argv"],
             "daddy", mhash, token, middleware)
        started.append(state["daddy"][0])
        for route,row in routes.items():
            leaf = row["source_file"]
            marker = (root / row["dir"] / leaf).read_text()[:256].strip() if config.get("fixture_echo") else row["dir"]
            child = spawn_worker(script, root,
                None if config.get("fixture_echo") else row["argv"],
                "child", marker, token, row["dir"])
            state["children"][route] = child
            started.append(child[0])
        # Deny a mixed startup generation if source changed during compilation.
        if digest_tree(root, middleware) != mhash or any(
            digest_tree(root, row["dir"], False) != state["initial_routes"][route]
            for route, row in routes.items()
        ):
            fail("source changed during initial worker admission")
        httpd = HttpService(("127.0.0.1", port), Worker)
        httpd.state = state
        watcher = threading.Thread(target=monitor,
             args=(state,script,root,middleware,routes,config.get("fixture_echo")),
             daemon=True)
        watcher.start()
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
        # A daemon watcher may still be admitting a slow guest-code candidate.
        if watcher is not None:
            watcher.join(timeout=35)
        cleanup_workers(state, started)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--language", choices=["oreslang","rust"], default="oreslang")
    parser.add_argument("--internal", choices=["child","daddy"])
    parser.add_argument("--worker-port", type=int)
    args = parser.parse_args()
    if args.internal:
        token = os.environ.get("ORES_DEV_HEALTH_TOKEN", "")
        marker = os.environ.get("ORES_DEV_MARKER", "")
        if not token or not marker or not args.worker_port or not 1024 <= args.worker_port < 65536:
            fail("invalid internal worker arguments")
        server = HttpService(("127.0.0.1", args.worker_port), Worker)
        server.state = {"mode":args.internal,"token":token,"marker":marker}
        server.serve_forever()
    else:
        supervise(args)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("ores dev generation tree:", exc, file=sys.stderr)
        sys.exit(2)
