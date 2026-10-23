import logging
import os
import re
import unittest

import numpy as np

from engine.cortex_models import FACTORY_CORTEX_PRESETS
from engine.cortex_scenes import CortexSceneManager, SPECIAL_PARAMS, BLOCK_ATTRS
from engine.dsp import CabinetSimulator, GraphicEqualizer, GuitarSignalChain, Reverb

SR = 48000
APP_JS = os.path.join(os.path.dirname(__file__), "..", "web", "app.js")


def _sine(freq, n=SR // 2, amp=0.3):
    return (amp * np.sin(2 * np.pi * freq * np.arange(n) / SR)).astype(np.float32)


def _rms_tail(y):
    return float(np.sqrt(np.mean(y[len(y) // 2:] ** 2)))


def _snapshot(chain):
    """Every value any factory scene can touch, plus block enabled flags."""
    snap = {}
    for name, attr in BLOCK_ATTRS.items():
        block = getattr(chain, attr)
        snap[(name, "enabled")] = block.enabled
    for preset in FACTORY_CORTEX_PRESETS:
        for sc in preset["scenes"]:
            for name, params in (sc.get("param_overrides") or {}).items():
                block = getattr(chain, BLOCK_ATTRS[name])
                for param in params:
                    if (name, param) == ("pitch", "semitones"):
                        snap[(name, param)] = block.target_semitones
                    elif (name, param) == ("eq", "data"):
                        snap[(name, param)] = list(block.gains)
                    else:
                        snap[(name, param)] = getattr(block, param)
    return snap


class SceneStateTests(unittest.TestCase):
    def test_a_d_a_returns_to_same_state(self):
        for preset in FACTORY_CORTEX_PRESETS:
            chain = GuitarSignalChain(SR)
            mgr = CortexSceneManager()
            mgr.load_preset(preset, chain=chain)
            base = _snapshot(chain)  # default scene already applied
            mgr.set_active_scene(0, chain)
            a1 = _snapshot(chain)
            mgr.set_active_scene(3, chain)
            d = _snapshot(chain)
            mgr.set_active_scene(0, chain)
            a2 = _snapshot(chain)
            self.assertEqual(a1, a2, preset["id"])
            self.assertEqual(base, a1, preset["id"])
            if preset["scenes"][3].get("param_overrides"):
                self.assertNotEqual(a1, d, preset["id"])

    def test_every_scene_visited_then_back_is_stable(self):
        chain = GuitarSignalChain(SR)
        mgr = CortexSceneManager()
        mgr.load_preset(FACTORY_CORTEX_PRESETS[0], chain=chain)
        mgr.set_active_scene(0, chain)
        first = _snapshot(chain)
        for i in range(8):
            mgr.set_active_scene(i, chain)
        mgr.set_active_scene(0, chain)
        self.assertEqual(first, _snapshot(chain))

    def test_external_change_is_not_clobbered(self):
        chain = GuitarSignalChain(SR)
        mgr = CortexSceneManager()
        mgr.load_preset(FACTORY_CORTEX_PRESETS[0], chain=chain)
        mgr.set_active_scene(1, chain)  # overrides amp.gain
        chain.amp.gain = 0.123          # knob moved by hand
        mgr.set_active_scene(2, chain)  # also overrides amp.gain; revert must skip it
        mgr.set_active_scene(1, chain)
        self.assertAlmostEqual(chain.amp.gain, 0.55)


class OverrideKeyTests(unittest.TestCase):
    def test_all_factory_override_keys_map_to_dsp_attributes(self):
        chain = GuitarSignalChain(SR)
        for preset in FACTORY_CORTEX_PRESETS:
            for sc in preset["scenes"]:
                for name, params in (sc.get("param_overrides") or {}).items():
                    block = getattr(chain, BLOCK_ATTRS[name])
                    for param in params:
                        self.assertTrue(
                            hasattr(block, param) or (name, param) in SPECIAL_PARAMS,
                            f"{preset['id']} scene {sc['index']}: {name}.{param}",
                        )
                        self.assertIsNotNone(CortexSceneManager.resolve_param(chain, name, param))

    def test_applying_scenes_logs_no_dropped_override(self):
        chain = GuitarSignalChain(SR)
        mgr = CortexSceneManager()
        with self.assertNoLogs("engine.cortex_scenes", level=logging.WARNING):
            for preset in FACTORY_CORTEX_PRESETS:
                mgr.load_preset(preset, chain=chain)
                for i in range(8):
                    mgr.set_active_scene(i, chain)

    def test_overrides_actually_land_on_dsp(self):
        chain = GuitarSignalChain(SR)
        mgr = CortexSceneManager()
        american = FACTORY_CORTEX_PRESETS[1]
        mgr.load_preset(american, chain=chain)
        mgr.set_active_scene(3, chain)
        self.assertAlmostEqual(chain.delay.time_sec, 0.12)
        mgr.set_active_scene(7, chain)
        self.assertEqual(chain.reverb.reverb_type, "spring")
        mgr.load_preset(FACTORY_CORTEX_PRESETS[2], chain=chain)
        mgr.set_active_scene(6, chain)
        self.assertAlmostEqual(chain.noise_gate.threshold_db, -38.0)


class DspEffectTests(unittest.TestCase):
    def _eq(self, gains):
        eq = GraphicEqualizer(model_id=5, sample_rate=SR)
        eq.enabled = True
        eq.set_bands(gains)
        return eq

    def test_low_cut_removes_lows(self):
        x = _sine(60)
        off = _rms_tail(self._eq([20, 0, 0, 0, 0, 20000]).process(x))
        on = _rms_tail(self._eq([400, 0, 0, 0, 0, 20000]).process(x))
        self.assertLess(on, off * 0.2)

    def test_high_cut_removes_highs(self):
        x = _sine(9000)
        off = _rms_tail(self._eq([20, 0, 0, 0, 0, 20000]).process(x))
        on = _rms_tail(self._eq([20, 0, 0, 0, 0, 2000]).process(x))
        self.assertLess(on, off * 0.2)

    def test_shelves_plateau_instead_of_peaking(self):
        curve = {p["f"]: p["db"] for p in self._eq([20, 12, 0, 0, 12, 20000]).get_curve_points(256)}
        freqs = sorted(curve)
        lo_20, lo_50 = curve[freqs[0]], curve[min(freqs, key=lambda f: abs(f - 50))]
        hi_20k, hi_12k = curve[freqs[-1]], curve[min(freqs, key=lambda f: abs(f - 12000))]
        self.assertGreater(lo_20, 9.0)
        self.assertGreater(lo_50, 9.0)
        self.assertGreater(hi_12k, 9.0)
        self.assertGreater(hi_20k, 7.0)

    def test_slider_move_keeps_filter_state(self):
        eq = self._eq([20, 6, 3, 0, 0, 20000])
        eq.process(_sine(200, 2048))
        before = {s[0]: s[3].copy() for s in eq._sections}
        eq.set_bands([20, 6.5, 3, 0, 0, 20000])
        for sec in eq._sections:
            np.testing.assert_array_equal(sec[3], before[sec[0]])
        self.assertTrue(any(np.any(z != 0) for z in before.values()))

    def test_mic_drag_keeps_filter_state(self):
        cab = CabinetSimulator(SR)
        cab.set_tube_and_mic(center=40, distance=20)
        cab.process(_sine(300, 2048))
        before = [s[2].copy() for s in cab._tube_mic_sections]
        cab.set_tube_and_mic(center=45)
        after = [s[2] for s in cab._tube_mic_sections]
        self.assertEqual(len(before), len(after))
        for b, a in zip(before, after):
            np.testing.assert_array_equal(a, b)
        self.assertTrue(any(np.any(z != 0) for z in before))

    def test_power_tubes_saturate_but_off_is_linear(self):
        x = _sine(220, 4096, amp=0.5)
        for tube, should_clip in (("OFF", False), ("6L6", True), ("EL34", True),
                                  ("EL84", True), ("6V6", True), ("KT88", True)):
            lo, hi = CabinetSimulator(SR), CabinetSimulator(SR)
            lo.set_tube_and_mic(tube=tube)
            hi.set_tube_and_mic(tube=tube)
            y1 = lo.process(x)
            y2 = hi.process(2.0 * x)
            linear = np.allclose(y2, 2.0 * y1, atol=1e-4)
            self.assertEqual(not linear, should_clip, tube)

    @staticmethod
    def _reverb_tail(**kw):
        """Feed a noise burst, then silence, in real-sized blocks; return the tail."""
        rv = Reverb(mix=1.0, sample_rate=SR, **kw)
        rv.enabled = True
        burst = np.random.default_rng(1).standard_normal(4096).astype(np.float32) * 0.3
        for i in range(0, len(burst), 256):
            rv.process(burst[i:i + 256])
        zeros = np.zeros(256, dtype=np.float32)
        return np.concatenate([rv.process(zeros) for _ in range(200)])

    def test_reverb_tone_changes_tail_brightness(self):
        def hf_ratio(tone):
            tail = self._reverb_tail(decay=0.6, tone=tone)
            spec = np.abs(np.fft.rfft(tail)) ** 2
            freqs = np.fft.rfftfreq(len(tail), 1.0 / SR)
            return spec[freqs > 5000].sum() / spec.sum()

        self.assertGreater(hf_ratio(1.0), hf_ratio(0.0) * 3)

    def test_reverb_type_changes_tail_length(self):
        def late_energy(rtype):
            tail = self._reverb_tail(decay=0.7, reverb_type=rtype)
            return float(np.sum(tail[len(tail) // 2:] ** 2))

        self.assertGreater(late_energy("cathedral"), late_energy("room") * 2)


class FrontendWiringTests(unittest.TestCase):
    def setUp(self):
        with open(APP_JS, encoding="utf-8") as f:
            self.src = f.read()

    def test_helper_functions_defined_exactly_once(self):
        for name in ("initMorphAndParallel", "attachCabMicDrag", "attachEqEvents", "drawEqCurve"):
            self.assertEqual(len(re.findall(rf"function {name}\(", self.src)), 1, name)

    def test_every_called_helper_is_defined(self):
        called = set(re.findall(r"(?<![\w.])(attach\w+|init[A-Z]\w+|draw\w+|render\w+|update\w+|select\w+|toggle\w+)\(", self.src))
        defined = set(re.findall(r"function\s+(\w+)\(", self.src))
        missing = sorted(n for n in called if n not in defined and n not in {"if", "for"})
        self.assertEqual(missing, [])

    def test_keydown_ignores_modifier_combos(self):
        self.assertIn("e.ctrlKey || e.metaKey || e.altKey", self.src)

    def test_single_reverb_panel_branch(self):
        self.assertEqual(self.src.count("if (b.id === 'reverb') {"), 1)


if __name__ == "__main__":
    unittest.main()
