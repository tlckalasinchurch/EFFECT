import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import importlib.util

_spec = importlib.util.spec_from_file_location("morph_under_test", Path(__file__).parents[1] / "engine" / "morph.py")
_morph_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_morph_module)
MorphController = _morph_module.MorphController


class TestMorphController(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.controller = MorphController(self.db_path)
        self.chain = SimpleNamespace(
            amp=SimpleNamespace(gain=0.3, master=0.6),
            screamer=SimpleNamespace(drive=0.2, level=0.7, enabled=True),
            delay=SimpleNamespace(mix=0.1, enabled=False),
            reverb=SimpleNamespace(mix=0.15),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fresh_slots_are_marked_empty_not_saved(self):
        self.assertEqual(self.controller.get_state()["captured"], {"A": False, "B": False})

    def test_capture_persists_snapshot_without_changing_live_chain(self):
        before = vars(self.chain.amp).copy(), vars(self.chain.screamer).copy(), vars(self.chain.delay).copy(), vars(self.chain.reverb).copy()
        saved = self.controller.capture_slot(" b ", self.chain)
        after = vars(self.chain.amp).copy(), vars(self.chain.screamer).copy(), vars(self.chain.delay).copy(), vars(self.chain.reverb).copy()
        restored = MorphController(self.db_path).get_state()
        self.assertEqual(before, after)
        self.assertEqual(restored["captured"], {"A": False, "B": True})
        self.assertEqual(restored["slot_b"], saved["slot_b"])
        self.assertEqual(restored["slot_b"]["amp_master"], 0.6)
        self.assertIsNotNone(restored["captured_at"]["B"])

    def test_clear_slot_persists_empty_state_without_changing_live_chain(self):
        self.controller.capture_slot("A", self.chain)
        before = vars(self.chain.amp).copy()
        state = self.controller.clear_slot("A")
        reloaded = MorphController(self.db_path).get_state()
        self.assertEqual(state["captured"]["A"], False)
        self.assertEqual(reloaded["captured"]["A"], False)
        self.assertIsNone(reloaded["captured_at"]["A"])
        self.assertEqual(before, vars(self.chain.amp))

    def test_capture_rejects_invalid_slot_or_incomplete_chain_without_write(self):
        initial = self.controller.get_state()
        for slot, chain in (("C", self.chain), ("A", SimpleNamespace(amp=self.chain.amp))):
            with self.subTest(slot=slot):
                with self.assertRaises(ValueError):
                    self.controller.capture_slot(slot, chain)
        self.assertEqual(self.controller.get_state(), initial)

    def test_non_finite_capture_is_atomic(self):
        self.controller.capture_slot("A", self.chain)
        before = self.controller.get_state()
        self.chain.amp.gain = math.nan
        with self.assertRaises(ValueError):
            self.controller.capture_slot("A", self.chain)
        self.assertEqual(self.controller.get_state(), before)
        self.assertEqual(MorphController(self.db_path).get_state(), before)

    def test_morph_clamps_and_interpolates_supported_values(self):
        self.controller.set_morph(-2, self.chain)
        self.assertEqual(self.controller.morph_pos, 0.0)
        self.controller.set_morph(0.5, self.chain)
        self.assertAlmostEqual(self.chain.amp.gain, 0.625)
        self.controller.set_morph(2, self.chain)
        self.assertEqual(self.controller.morph_pos, 1.0)
        self.assertAlmostEqual(self.chain.amp.gain, 0.85)

    def test_morph_rejects_nan_and_infinity_without_changing_position(self):
        self.controller.set_morph(0.25)
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.controller.set_morph(value)
                self.assertEqual(self.controller.morph_pos, 0.25)


if __name__ == "__main__":
    unittest.main()
