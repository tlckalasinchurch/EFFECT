"""F3 / D3 / D4 hardening: finite parameter values, rate rebuild, callback stats.

None of these touch a golden file: finite values, the 48 kHz chain and the
audio output of a healthy callback are unchanged.
"""

import math
import types
import unittest

import numpy as np

from engine import param_access, params
from engine.audio import AudioEngine, rebuild_chain_for_rate
from engine.cortex_scenes import CortexSceneManager
from engine.dsp import GuitarSignalChain


def _engine(chain=None):
    engine = AudioEngine(sample_rate=48000, block_size=128)
    if chain is not None:
        engine.chain = chain
    return engine


def _callback(engine, frames=128, value=0.1):
    indata = np.full((frames, 1), value, dtype=np.float32)
    outdata = np.ones((frames, 2), dtype=np.float32)
    engine._audio_callback(indata, outdata, frames, None, None)
    return outdata


class NonFiniteParameterTests(unittest.TestCase):
    def test_nan_and_inf_are_refused_and_the_value_is_untouched(self):
        chain = GuitarSignalChain()
        before = chain.delay.feedback
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(param_access.NonFiniteValue):
                param_access.set(chain, "delay", "feedback", bad)
        self.assertEqual(chain.delay.feedback, before)

    def test_a_non_finite_list_entry_is_refused(self):
        chain = GuitarSignalChain()
        gains = list(chain.eq.gains)
        with self.assertRaises(param_access.NonFiniteValue):
            param_access.set(chain, "eq", "band0", float("nan"))
        self.assertEqual(list(chain.eq.gains), gains)

    def test_finite_values_still_pass(self):
        chain = GuitarSignalChain()
        self.assertEqual(param_access.set(chain, "delay", "feedback", 0.5), 0.5)

    def test_apply_settings_skips_a_non_finite_value_and_keeps_going(self):
        chain = GuitarSignalChain()
        applied = param_access.apply_settings(chain, "delay", {"feedback": float("nan"), "mix": 0.4})
        self.assertIn("mix", applied)
        self.assertNotIn("feedback", applied)
        self.assertEqual(chain.delay.mix, 0.4)
        self.assertTrue(math.isfinite(chain.delay.feedback))

    def test_the_api_handler_answers_400(self):
        import server
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            server.update_parameter(server.ParamUpdate(section="delay", param="feedback", value=float("nan")))
        self.assertEqual(caught.exception.status_code, 400)

    def test_a_scene_override_cannot_write_nan(self):
        chain = GuitarSignalChain()
        with self.assertRaises(ValueError):
            CortexSceneManager._set("delay", chain.delay, "feedback", float("nan"))


class SampleRateRebuildTests(unittest.TestCase):
    def test_blocks_are_designed_for_the_new_rate_and_settings_survive(self):
        old = GuitarSignalChain(sample_rate=48000)
        old.amp.gain = 0.91
        old.delay.time_sec = 0.5
        old.master_volume = 0.4
        new = rebuild_chain_for_rate(old, 96000)
        for block in (new.noise_gate, new.screamer, new.amp, new.cab, new.delay, new.reverb, new.mod):
            self.assertEqual(block.sample_rate, 96000)
        self.assertEqual((new.amp.gain, new.delay.time_sec, new.master_volume), (0.91, 0.5, 0.4))
        self.assertNotEqual(new.delay.buffer.shape, old.delay.buffer.shape)

    def test_every_registry_value_is_carried_over(self):
        old = GuitarSignalChain(sample_rate=48000)
        old.amp.bass = 0.2
        old.reverb.mix = 0.6
        new = rebuild_chain_for_rate(old, 44100)
        for mod in params.MODULES:
            if mod.name == "nam":
                continue
            a, b = param_access._target(old, mod), param_access._target(new, mod)
            for p in mod.params:
                if p.read_only or p.owner == "server" or p.key == "ir_name":
                    continue
                self.assertTrue(
                    np.array_equal(np.asarray(getattr(a, p.read_attr or p.attr)),
                                   np.asarray(getattr(b, p.read_attr or p.attr))),
                    f"{mod.name}.{p.key}")

    def test_engine_applies_the_rate_once_and_keeps_the_chain_when_unchanged(self):
        engine = _engine()
        same = engine.chain
        engine.apply_sample_rate(48000)
        self.assertIs(engine.chain, same)
        engine.apply_sample_rate(96000)
        self.assertIsNot(engine.chain, same)
        self.assertEqual((engine.sample_rate, engine.chain.sample_rate, engine.chain.amp.sample_rate),
                         (96000, 96000, 96000))


class CallbackHardeningTests(unittest.TestCase):
    def test_a_raising_chain_gives_silence_and_is_counted(self):
        engine = _engine(types.SimpleNamespace(process=lambda x: 1 / 0))
        out = _callback(engine)
        self.assertEqual(float(np.max(np.abs(out))), 0.0)
        stats = engine.callback_stats()
        self.assertEqual(stats["callback_errors"], 1)
        self.assertIn("ZeroDivisionError", stats["last_callback_error"])

    def test_non_finite_output_is_silenced_and_counted(self):
        engine = _engine(types.SimpleNamespace(process=lambda x: np.full(len(x), np.nan, dtype=np.float32)))
        out = _callback(engine)
        self.assertEqual(float(np.max(np.abs(out))), 0.0)
        self.assertEqual(engine.callback_stats()["nonfinite_blocks"], 1)

    def test_a_healthy_block_is_not_touched(self):
        engine = _engine(types.SimpleNamespace(process=lambda x: x * 0.5))
        out = _callback(engine, value=0.2)
        np.testing.assert_allclose(out, 0.1, atol=1e-7)
        self.assertEqual(engine.callback_stats()["nonfinite_blocks"], 0)

    def test_warmup_spikes_are_reported_separately_from_steady_state(self):
        engine = _engine()
        engine._callback_warmup = 2
        engine._callback_count = 0
        engine.chain = types.SimpleNamespace(process=lambda x: x)
        for _ in range(5):
            _callback(engine)
        stats = engine.callback_stats()
        self.assertEqual(stats["percentile_blocks"], 3)
        self.assertGreaterEqual(stats["warmup_max_ms"], 0.0)

    def test_percentiles_and_deadline_counters(self):
        engine = _engine()
        deadline = 128 / 48000 * 1000.0
        for ms in [0.1] * 98 + [deadline * 0.6, deadline * 2]:
            engine._record_block_time(ms)
        stats = engine.callback_stats()
        self.assertEqual(stats["percentile_blocks"], 100)
        self.assertAlmostEqual(stats["p50_ms"], 0.1, places=3)
        self.assertGreater(stats["p99_9_ms"], deadline)
        self.assertEqual(stats["over_deadline_blocks"], 1)
        self.assertEqual(stats["over_half_deadline_blocks"], 2)

    def test_no_samples_means_no_percentiles(self):
        stats = _engine().callback_stats()
        self.assertIsNone(stats["p99_ms"])
        self.assertEqual(stats["percentile_blocks"], 0)


if __name__ == "__main__":
    unittest.main()
