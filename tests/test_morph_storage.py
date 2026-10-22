"""Regression tests for MorphController's SQLite resource handling.

The leak this guards against::

    with sqlite3.connect(path) as conn:   # commits/rolls back, never closes
        ...

CPython's per-connection statement cache keeps a reference back to the
connection, so refcounting does not free it either.  Every capture/clear left
one handle open for good, and on Windows ``presets.db`` stayed locked -- which
is why ``tests/test_morph_quality.py`` used to fail in ``tearDown`` with
``PermissionError: [WinError 32] ... test.db``.
"""

import gc
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from engine.morph import MorphController


def _live_connections():
    """Connections still reachable in this process, leaks included."""
    return sum(1 for obj in gc.get_objects() if isinstance(obj, sqlite3.Connection))


def _chain():
    return SimpleNamespace(
        amp=SimpleNamespace(gain=0.3, master=0.6),
        screamer=SimpleNamespace(drive=0.2, level=0.7, enabled=True),
        delay=SimpleNamespace(mix=0.1, enabled=False),
        reverb=SimpleNamespace(mix=0.15),
    )


class MorphStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.controller = MorphController(self.db_path)

    def tearDown(self):
        del self.controller
        self.temp_dir.cleanup()

    def test_repeated_operations_do_not_leave_connections_open(self):
        chain = _chain()
        before = _live_connections()
        for _ in range(5):
            self.controller.capture_slot("A", chain)
            self.controller.capture_slot("B", chain)
            self.controller.clear_slot("B")
        after = _live_connections()
        self.assertEqual(
            after - before, 0,
            f"{after - before} SQLite connections were still open after the operations",
        )

    def test_database_file_is_deletable_while_the_controller_lives(self):
        """The user-visible symptom: a locked file. Must work without a GC run."""
        self.controller.capture_slot("A", _chain())
        os.unlink(self.db_path)  # PermissionError on Windows while a handle is open
        self.assertFalse(os.path.exists(self.db_path))

    def test_commit_is_still_persisted(self):
        self.controller.capture_slot("A", _chain())
        reloaded = MorphController(self.db_path).get_state()
        self.assertTrue(reloaded["captured"]["A"])
        self.assertEqual(reloaded["slot_a"]["amp_master"], 0.6)

    def test_database_stays_usable_after_a_rejected_capture(self):
        self.controller.capture_slot("A", _chain())
        bad = _chain()
        bad.delay.mix = float("nan")
        with self.assertRaises(ValueError):
            self.controller.capture_slot("A", bad)
        self.assertEqual(MorphController(self.db_path).get_state()["slot_a"]["delay_mix"], 0.1)
        self.controller.clear_slot("A")
        self.assertFalse(self.controller.get_state()["captured"]["A"])


if __name__ == "__main__":
    unittest.main()
