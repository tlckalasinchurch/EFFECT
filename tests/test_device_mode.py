"""Only generic and TONE3000/NAM modes are supported; generic remains identical."""

import json
import time
import unittest
from types import SimpleNamespace

import numpy as np

from engine import device_mode as dm
from engine.dsp import GuitarSignalChain
from engine.mooer_preset import FACTORY_GE150_PRESETS
from tests.test_chain_sweep import BASELINE_PATH, CASES
from tests.test_characterization import render, render_input, signature


class ModeTableTests(unittest.TestCase):
    def test_every_mode_has_one_complete_order(self):
        for mode in dm.DEVICE_MODES:
            with self.subTest(mode=mode):
                order = dm.block_order(mode)
                self.assertEqual(len(order), len(set(order)), "duplicate stage")
                self.assertLessEqual(set(order), set(dm.STAGES), "unknown stage")
                for stage in ("gate", "pitch", "amp"):
                    self.assertIn(stage, order)

    def test_generic_is_the_pre_mode_order_and_is_the_default(self):
        self.assertEqual(dm.block_order("generic"), dm.GENERIC_ORDER)
        self.assertEqual(GuitarSignalChain().device_mode, "generic")

    def test_preset_sources_pick_the_matching_mode(self):
        self.assertEqual(dm.mode_for_source("mooer"), "generic")
        self.assertEqual(dm.mode_for_source("GE150"), "generic")
        self.assertEqual(dm.mode_for_source("cortex"), "generic")
        self.assertEqual(dm.mode_for_source("quad-cortex"), "generic")
        self.assertEqual(dm.mode_for_source("kemper"), "generic")
        self.assertEqual(dm.mode_for_source("tone3000"), "nam")
        self.assertEqual(dm.mode_for_source("t3k"), "nam")
        self.assertEqual(dm.mode_for_source("ableton"), "generic")
        self.assertEqual(dm.mode_for_source(None), "generic")

    def test_removed_modes_are_not_supported(self):
        self.assertEqual(dm.DEVICE_MODES, ("generic", "nam"))
        for removed in ("ge150", "cortex", "kemper"):
            with self.subTest(mode=removed), self.assertRaises(ValueError):
                dm.block_order(removed)

    def test_unknown_mode_is_rejected_and_the_chain_keeps_its_order(self):
        chain = GuitarSignalChain()
        before = chain._stage_order
        with self.assertRaises(ValueError):
            chain.device_mode = "boss"
        self.assertEqual(chain.device_mode, "generic")
        self.assertIs(chain._stage_order, before)

    def test_switching_mode_leaves_every_parameter_alone(self):
        chain = GuitarSignalChain()
        chain.amp.gain = 0.31
        chain.delay.mix = 0.42
        chain.set_device_mode("nam")
        self.assertEqual(chain.amp.gain, 0.31)
        self.assertEqual(chain.delay.mix, 0.42)


class GenericModeIdentityTests(unittest.TestCase):
    """The default sound is the recorded one; anything else is a sound change."""

    def test_generic_mode_reproduces_the_recorded_sweep(self):
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        x = render_input()
        for name, factory in CASES.items():
            chain = factory()
            chain.device_mode = "generic"  # set explicitly, not just inherited
            with self.subTest(case=name):
                got = signature(render(chain, x))
                want = data["cases"][name]
                # The golden stores values rounded to 9 decimals, so 1e-9 is
                # as close to "identical" as the file can express.
                self.assertAlmostEqual(got["peak"], want["peak"], delta=1e-9)
                self.assertAlmostEqual(got["rms"], want["rms"], delta=1e-9)
                np.testing.assert_allclose(got["samples"], want["samples"], atol=1e-9, rtol=0)
                np.testing.assert_allclose(got["block_rms"], want["block_rms"], atol=1e-9, rtol=0)

    def test_explicit_generic_matches_the_default_constructor_bit_for_bit(self):
        x = render_input()
        default = render(CASES["full_stack"](), x)
        chain = CASES["full_stack"]()
        chain.device_mode = "generic"
        np.testing.assert_array_equal(render(chain, x), default)


class MooerAutoSwitchTests(unittest.TestCase):
    """MOOER imports stay on generic rather than selecting unusable GE150 DSP."""

    def test_apply_mooer_preset_stays_on_generic(self):
        chain = GuitarSignalChain()
        chain.set_device_mode("nam")
        chain.apply_mooer_preset(FACTORY_GE150_PRESETS[0])
        self.assertEqual(chain.device_mode, "generic")

    def test_loading_a_saved_tone3000_preset_restores_nam_mode(self):
        import server

        engine = server.engine
        saved = engine.chain
        engine.chain = GuitarSignalChain(sample_rate=48000)
        self.addCleanup(setattr, engine, "chain", saved)

        settings = engine.get_state()["chain"]
        settings["device"] = {"mode": "nam"}
        settings["_t3k"] = {"cache_file": "unit-test-cache"}
        original_restore = server._restore_cached_t3k
        server._restore_cached_t3k = lambda _meta, _chain: SimpleNamespace(describe=lambda: {"active": True})
        self.addCleanup(setattr, server, "_restore_cached_t3k", original_restore)
        original = server.get_all_presets
        server.get_all_presets = lambda: [{"id": "mode-test", "settings": settings}]
        self.addCleanup(setattr, server, "get_all_presets", original)

        server.load_preset(server.PresetLoad(preset_id="mode-test"))
        self.assertEqual(engine.chain.device_mode, "nam")

    def test_a_preset_without_a_device_section_stays_generic(self):
        """Every preset written before device modes existed has no such key."""
        import server

        engine = server.engine
        saved = engine.chain
        engine.chain = GuitarSignalChain(sample_rate=48000)
        engine.chain.set_device_mode("nam")  # stale mode from a previous load
        self.addCleanup(setattr, engine, "chain", saved)

        settings = engine.get_state()["chain"]
        settings.pop("device", None)
        original = server.get_all_presets
        server.get_all_presets = lambda: [{"id": "mode-test", "settings": settings}]
        self.addCleanup(setattr, server, "get_all_presets", original)

        server.load_preset(server.PresetLoad(preset_id="mode-test"))
        self.assertEqual(engine.chain.device_mode, "generic")

    def test_removed_mode_in_a_preset_falls_back_to_generic(self):
        import server

        engine = server.engine
        saved = engine.chain
        engine.chain = GuitarSignalChain(sample_rate=48000)
        self.addCleanup(setattr, engine, "chain", saved)

        settings = engine.get_state()["chain"]
        settings["device"] = {"mode": "cortex"}  # removed/unusable mode
        original = server.get_all_presets
        server.get_all_presets = lambda: [{"id": "mode-test", "settings": settings}]
        self.addCleanup(setattr, server, "get_all_presets", original)

        server.load_preset(server.PresetLoad(preset_id="mode-test"))
        self.assertEqual(engine.chain.device_mode, "generic")


class NamCpuBudgetTests(unittest.TestCase):
    """TONE3000/NAM mode must leave headroom at the 256-sample buffer."""

    def test_nam_mode_fits_within_the_deadline_at_block_256(self):
        block = 256
        deadline_ms = block / 48000.0 * 1000.0
        chain = GuitarSignalChain(device_mode="nam")
        rng = np.random.default_rng(5)
        x = (rng.standard_normal(block) * 0.05).astype(np.float32)
        for _ in range(30):
            chain.process(x)
        times = []
        for _ in range(300):
            started = time.perf_counter()
            chain.process(x)
            times.append((time.perf_counter() - started) * 1000.0)
        median = float(np.median(times))
        # Require the processing median to remain within the block deadline,
        # retaining 10% for scheduling noise.
        self.assertLess(
            median, deadline_ms * 0.9,
            f"NAM median {median:.2f} ms vs deadline {deadline_ms:.2f} ms",
        )


class OrderIsAppliedTests(unittest.TestCase):
    def _recorded_order(self, mode, stages):
        chain = GuitarSignalChain(device_mode=mode)
        calls = []
        for name in stages:
            block = getattr(chain, name)
            original = block.process

            def record(*args, _name=name, _original=original, **kwargs):
                calls.append(_name)
                return _original(*args, **kwargs)

            block.process = record
        chain.process(np.zeros(64, np.float32))
        return calls

    def test_generic_runs_the_gate_before_the_cab(self):
        calls = self._recorded_order("generic", ("noise_gate", "pitch_shifter", "screamer", "amp", "eq", "cab"))
        self.assertLess(calls.index("noise_gate"), calls.index("cab"))

    def test_nam_uses_the_same_verified_stage_order(self):
        calls = self._recorded_order("nam", ("noise_gate", "pitch_shifter", "screamer", "amp", "eq", "cab"))
        self.assertLess(calls.index("noise_gate"), calls.index("cab"))


if __name__ == "__main__":
    unittest.main()
