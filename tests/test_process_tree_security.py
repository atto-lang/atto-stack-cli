#!/usr/bin/env python3
"""POSIX process-group teardown must reap descendants after parent exit."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ores_generation_supervisor", ROOT / "bin/generation-tree.py")
TREE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TREE)

@unittest.skipUnless(os.name=="posix", "POSIX process groups required")
class ProcessGroupTeardown(unittest.TestCase):
    def test_exited_group_leader_does_not_leave_grandchildren(self):
        with tempfile.TemporaryDirectory() as td:
            marker=pathlib.Path(td)/"orphan-finished"
            grandchild=(
                "import pathlib,time; "
                "time.sleep(1.2); "
                f"pathlib.Path({str(marker)!r}).write_text('leaked')"
            )
            leader=(
                "import subprocess,sys; "
                "subprocess.Popen([sys.executable,'-c',"+repr(grandchild)+"],"
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,"
                "stderr=subprocess.DEVNULL)"
            )
            proc=subprocess.Popen([sys.executable,"-c",leader],
                                  start_new_session=True,stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            proc.wait(timeout=3)
            self.assertIsNotNone(proc.poll(), "group leader must exit before teardown")
            TREE.stop(proc)
            time.sleep(1.4)
            self.assertFalse(marker.exists(), "orphaned worker survived exited parent")

    def test_shutdown_reaps_retired_worker_even_before_drain_deadline(self):
        import threading
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                   start_new_session=True, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state = {"stop": threading.Event(), "lock": threading.Lock(),
                 "daddy": None, "children": {}, "retired": [process]}
        try:
            TREE.cleanup_workers(state, [])
            self.assertIsNotNone(process.poll())
            self.assertTrue(state["stop"].is_set())
        finally:
            TREE.stop(process)

    def test_retirement_drain_is_interrupted_by_shutdown(self):
        import threading
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                   start_new_session=True, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state = {"stop": threading.Event(), "lock": threading.Lock(),
                 "retired": [process]}
        watcher = threading.Thread(target=TREE.retire_worker,
                                   args=(state, process), daemon=True)
        try:
            watcher.start()
            state["stop"].set()
            watcher.join(timeout=3)
            self.assertFalse(watcher.is_alive(), "retirement ignored grandaddy shutdown")
            self.assertIsNotNone(process.poll(), "retired worker still alive")
            self.assertFalse(state["retired"], "retired process was not untracked")
        finally:
            TREE.stop(process)

if __name__=="__main__":
    unittest.main()
