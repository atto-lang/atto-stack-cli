#!/usr/bin/env python3
"""Content watcher must never hash symlink targets, pipes or oversized sources."""
import hashlib
import importlib.util
import os
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("ores_watch_guard", ROOT/"bin/generation-tree.py")
GUARD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)

class SnapshotAdmission(unittest.TestCase):
    def test_noncanonical_source_paths_are_refused_before_normalization(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root/"src").mkdir()
            for value in ("src//routes", "src/./routes", "src/../etc", "./src",
                          "src/", "src\\\\routes", "/tmp"):
                with self.subTest(path=value):
                    with self.assertRaises(ValueError):
                        GUARD.safe_relative(root, value)

    def test_regular_sources_are_hashed_by_opened_descriptor(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"route.rs"
            p.write_bytes(b"program-v1")
            self.assertEqual(GUARD.digest_regular_file(p),
                             hashlib.sha256(b"program-v1").hexdigest())
            p.write_bytes(b"program-v2")
            self.assertNotEqual(GUARD.digest_regular_file(p),
                                hashlib.sha256(b"program-v1").hexdigest())

    def test_final_component_symlink_cannot_be_followed(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            secret=root/"unrelated-source"
            secret.write_bytes(b"unrelated")
            link=root/"route.ores"
            link.symlink_to(secret)
            with self.assertRaises((OSError,ValueError)):
                GUARD.digest_regular_file(link)

    def test_size_limit_is_enforced_without_unbounded_read(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"large.ores"
            with p.open("wb") as out:
                out.seek(GUARD.MAX_BYTES)
                out.write(b"x")
            with self.assertRaises(ValueError):
                GUARD.digest_regular_file(p)

    @unittest.skipUnless(hasattr(os,"mkfifo"),"POSIX FIFO required")
    def test_named_pipe_never_blocks_source_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"fifo.rs"
            os.mkfifo(p)
            with self.assertRaises(ValueError):
                GUARD.digest_regular_file(p)

    def test_nested_symlink_source_tree_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r=pathlib.Path(d)
            (r/"src/routes/a").mkdir(parents=True)
            (r/"src/routes/a/route.ores").write_text("regular")
            (r/"outside").mkdir()
            (r/"src/routes/a/link").symlink_to(r/"outside",target_is_directory=True)
            with self.assertRaises(ValueError):
                GUARD.digest_tree(r,"src/routes/a",recursive=True)

if __name__=="__main__":
    unittest.main()
