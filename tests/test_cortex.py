import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock
import numpy as np

from engine.dsp import GuitarSignalChain
from engine.cortex_models import SCENE_COLORS, DEFAULT_SCENE_LABELS, FACTORY_CORTEX_PRESETS
from engine.cortex_scenes import CortexSceneManager
from engine.morph import MorphController
import server
from server import (
    get_cortex_scenes,
    select_cortex_scene,
    update_cortex_scene,
    get_cortex_presets,
    load_cortex_preset_endpoint,
    export_cortex_preset,
    get_morph_state,
    set_morph_position,
    capture_morph_slot,
    get_eq_curve,
    cortex_mgr,
    morph_mgr,
    engine,
)


class TestCortexSceneManager(unittest.TestCase):
    def setUp(self):
        self.sm = CortexSceneManager()
        self.chain = GuitarSignalChain(sample_rate=48000)

    def test_default_scenes_count_and_badges(self):
        scenes = self.sm.get_scenes()
        self.assertEqual(len(scenes), 8)
        for i in range(8):
            self.assertEqual(scenes[i]["index"], i)
            self.assertEqual(scenes[i]["badge"], chr(65 + i))
            self.assertEqual(scenes[i]["color"], SCENE_COLORS[i]["hex"])

    def test_scene_switching_and_dsp_bypass(self):
        # By default in scene 0 (Clean), screamer is False
        self.sm.set_active_scene(0, chain=self.chain)
        self.assertFalse(self.chain.screamer.enabled)

        # Switch to scene 1 (Verse Crunch), screamer is True
        self.sm.set_active_scene(1, chain=self.chain)
        self.assertTrue(self.chain.screamer.enabled)
        self.assertEqual(self.sm.active_scene_index, 1)

    def test_load_preset_and_parameter_overrides(self):
        preset = FACTORY_CORTEX_PRESETS[0]  # British Lead 100
        self.sm.load_preset(preset, chain=self.chain)

        self.assertEqual(self.sm.current_preset_name, "British Lead 100")
        self.assertEqual(self.sm.active_scene_index, 0)
        # Scene 0 override amp gain = 0.25
        self.assertAlmostEqual(self.chain.amp.gain, 0.25, places=2)

        # Switch to Scene 3 (Solo Boost Lead)
        self.sm.set_active_scene(3, chain=self.chain)
        self.assertTrue(self.chain.screamer.enabled)
        self.assertTrue(self.chain.delay.enabled)
        self.assertAlmostEqual(self.chain.amp.gain, 0.80, places=2)
        self.assertAlmostEqual(self.chain.delay.mix, 0.32, places=2)

    def test_invalid_scene_index_raises(self):
        with self.assertRaises(ValueError):
            self.sm.set_active_scene(8)
        with self.assertRaises(ValueError):
            self.sm.set_active_scene(-1)

    def test_scene_update(self):
        self.sm.update_scene(2, label="My Custom Chorus", color_hex="#123456")
        sc = self.sm.get_scenes()[2]
        self.assertEqual(sc["label"], "My Custom Chorus")
        self.assertEqual(sc["color"], "#123456")


class TestCortexApi(unittest.TestCase):
    def setUp(self):
        # server.morph_mgr is built on the real presets.db; capture/clear would
        # write the user's morph slots, so every API test gets a throw-away DB.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(server, "morph_mgr", MorphController(str(Path(tmp.name) / "morph.db")))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_get_cortex_scenes(self):
        data = get_cortex_scenes()
        self.assertIn("scenes", data)
        self.assertEqual(len(data["scenes"]), 8)
        self.assertIn("active_badge", data)

    def test_select_cortex_scene(self):
        data = select_cortex_scene({"index": 2})
        self.assertTrue(data["success"])
        self.assertEqual(data["active_scene"]["badge"], "C")

    def test_get_cortex_presets(self):
        data = get_cortex_presets()
        self.assertIn("presets", data)
        self.assertGreaterEqual(len(data["presets"]), 3)

    def test_load_cortex_preset(self):
        data = load_cortex_preset_endpoint({"id": "cortex_american_clean_twin"})
        self.assertTrue(data["success"])
        self.assertEqual(data["cortex"]["preset_id"], "cortex_american_clean_twin")

    def test_export_cortex_preset(self):
        res = export_cortex_preset(name="StageMaster")
        doc = json.loads(res.body.decode("utf-8"))
        self.assertEqual(doc["name"], "StageMaster")
        self.assertEqual(len(doc["scenes"]), 8)

    def test_morph_controller(self):
        m = MorphController(db_path=':memory:')
        chain = GuitarSignalChain(sample_rate=48000)
        # Test Heel (0.0)
        m.set_morph(0.0, chain=chain)
        self.assertAlmostEqual(chain.amp.gain, 0.40, places=2)
        # Test Toe (1.0)
        m.set_morph(1.0, chain=chain)
        self.assertAlmostEqual(chain.amp.gain, 0.85, places=2)
        # Test Halfway (0.5)
        m.set_morph(0.5, chain=chain)
        self.assertAlmostEqual(chain.amp.gain, 0.625, places=2)

    def test_dynamic_ducking_delay_and_reverb(self):
        chain = GuitarSignalChain(sample_rate=48000)
        chain.delay.enabled = True
        chain.delay.ducking = True
        chain.delay.duck_depth = 0.8
        chain.reverb.enabled = True
        chain.reverb.ducking = True

        # Process loud block (should engage ducking)
        loud_chunk = np.ones(256, dtype=np.float32) * 0.8
        out_loud = chain.process(loud_chunk)
        self.assertTrue(np.all(np.isfinite(out_loud)))

        # Process quiet block
        quiet_chunk = np.zeros(256, dtype=np.float32)
        out_quiet = chain.process(quiet_chunk)
        self.assertTrue(np.all(np.isfinite(out_quiet)))

    def test_parallel_signal_grid(self):
        chain = GuitarSignalChain(sample_rate=48000)
        chain.parallel_enabled = True
        chain.parallel_blend = 0.4
        test_block = (0.5 * np.sin(np.linspace(0, 10, 256))).astype(np.float32)
        out = chain.process(test_block)
        self.assertEqual(len(out), 256)
        self.assertTrue(np.all(np.isfinite(out)))

    def test_parametric_eq_curve_points(self):
        chain = GuitarSignalChain(sample_rate=48000)
        chain.eq.enabled = True
        chain.eq.set_bands([40.0, 3.0, -2.0, 4.0, 1.0, 14000.0], model_id=5)
        curve = chain.eq.get_curve_points(num_points=32)
        self.assertEqual(len(curve), 32)
        self.assertIn("f", curve[0])
        self.assertIn("db", curve[0])

    def test_morph_capture_and_clear_api(self):
        captured = capture_morph_slot({"slot": "B"})
        self.assertTrue(captured["success"])
        self.assertTrue(captured["morph"]["captured"]["B"])

        from server import clear_morph_slot
        cleared = clear_morph_slot("B")
        self.assertTrue(cleared["success"])
        self.assertFalse(cleared["morph"]["captured"]["B"])

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            capture_morph_slot({"slot": "C"})
        self.assertEqual(error.exception.status_code, 422)

    def test_morph_and_eq_api(self):
        # Test morph API
        res1 = set_morph_position({"pos": 0.75})
        self.assertTrue(res1["success"])
        self.assertEqual(res1["morph"]["morph_pos"], 0.75)

        res2 = get_morph_state()
        self.assertEqual(res2["morph_pos"], 0.75)

        # Test EQ curve API
        res3 = get_eq_curve()
        self.assertIn("curve", res3)
        self.assertGreater(len(res3["curve"]), 0)

