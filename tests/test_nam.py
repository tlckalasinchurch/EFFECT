"""
Tests for engine.nam and the NAM extraction in engine.tone3000_importer.

Run:  .venv\\Scripts\\python.exe -m unittest tests.test_nam -v

Needs the TONE3000 factory presets (C:\\ProgramData\\TONE3000\\Presets\\Factory).
The golden-vector test also needs a checkout of github.com/tone-3000/embedded
(MIT): set T3K_EMBEDDED_DIR to it; otherwise that test is skipped.
"""

import glob
import os
import struct
import unittest

import numpy as np

from engine import nam
from engine.tone3000_importer import TONE3000_FACTORY_DIR, get_nam_chain, _nam_blocks

PRESETS = sorted(glob.glob(os.path.join(TONE3000_FACTORY_DIR, "*.t3kpreset")))
EMBEDDED = os.environ.get("T3K_EMBEDDED_DIR")


def _guitar_like(n, seed=0):
    t = np.arange(n) / 48000.0
    rng = np.random.default_rng(seed)
    x = 0.25 * np.sin(2 * np.pi * 110 * t) + 0.1 * np.sin(2 * np.pi * 220 * t) + 0.05 * np.sin(2 * np.pi * 330 * t)
    return (x + 0.005 * rng.standard_normal(n)).astype(np.float32)


@unittest.skipUnless(PRESETS, "TONE3000 factory presets not installed")
class NamModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = _nam_blocks(PRESETS[0])[0][2]

    def test_weight_count_matches_config_for_both_submodels(self):
        # WaveNet() raises if the config-derived layout does not use every weight exactly.
        net = nam.SlimmableWaveNet(self.container)
        self.assertEqual(len(net.nets), 2)
        self.assertEqual(sorted(len(s["model"]["weights"]) for s in self.container["config"]["submodels"]), [1871, 12146])

    def test_wrong_weight_count_is_rejected(self):
        sub = dict(self.container["config"]["submodels"][0]["model"])
        sub["weights"] = sub["weights"][:-1]
        with self.assertRaises(ValueError):
            nam.WaveNet(sub)

    def test_unsupported_architecture_is_rejected(self):
        with self.assertRaises(NotImplementedError):
            nam.SlimmableWaveNet({"architecture": "LSTM"})

    def test_block_processing_equals_one_shot(self):
        x = _guitar_like(4096)
        a = nam.SlimmableWaveNet(self.container, build="lite")
        b = nam.SlimmableWaveNet(self.container, build="lite")
        whole = a.process(x)
        parts = np.concatenate([b.process(x[i:i + 512]) for i in range(0, len(x), 512)])
        np.testing.assert_allclose(parts, whole, atol=1e-6)

    def test_silence_in_gives_steady_output_not_a_startup_transient(self):
        net = nam.SlimmableWaveNet(self.container, build="lite")
        out = net.process(np.zeros(2048, np.float32))
        self.assertLess(float(np.abs(out - out[-1]).max()), 1e-5)

    def test_slimmable_submodels_agree(self):
        # Different sizes of the same capture: a wrong layout would decorrelate them.
        x = _guitar_like(9600, seed=1)
        net = nam.SlimmableWaveNet(self.container)
        net.select(0.5)
        lite = net.process(x)[2000:]
        net.reset()
        net.select(1.0)
        full = net.process(x)[2000:]
        self.assertGreater(float(np.corrcoef(lite, full)[0, 1]), 0.9)

    def test_output_is_finite_and_bounded_for_loud_input(self):
        net = nam.SlimmableWaveNet(self.container, build="lite")
        out = net.process(np.clip(_guitar_like(4096) * 8, -1, 1))
        self.assertTrue(np.isfinite(out).all())
        self.assertLess(float(np.abs(out).max()), 10.0)


@unittest.skipUnless(PRESETS, "TONE3000 factory presets not installed")
class PresetExtractionTests(unittest.TestCase):
    def test_every_factory_preset_yields_a_chain(self):
        for path in PRESETS:
            with self.subTest(preset=os.path.basename(path)):
                chain = get_nam_chain(path, "lite")
                self.assertIsNotNone(chain)
                out = chain.process(_guitar_like(512))
                self.assertEqual(out.shape, (512,))
                self.assertTrue(np.isfinite(out).all())

    def test_bad_quality_is_rejected(self):
        with self.assertRaises(ValueError):
            get_nam_chain(PRESETS[0], "huge")

    def test_amp_cab_capture_marks_chain_as_including_the_cab(self):
        stage = lambda gear: {"title": "x", "gear_type": gear, "net": _FakeNet()}
        self.assertTrue(nam.NamChain([stage("amp_cab"), stage("studio")]).includes_cab)
        self.assertFalse(nam.NamChain([stage("pedal"), stage("amp")]).includes_cab)

    def test_input_gain_and_loudness_scaling(self):
        net = _FakeNet(loudness=-24.0)
        chain = nam.NamChain([{"title": "x", "gear_type": None, "net": net}], input_gain_db=6.0)
        out = chain.process(np.ones(4, np.float32))
        # +6 dB in, then +6 dB to bring loudness -24 up to the -18 target
        np.testing.assert_allclose(out, 10 ** (12.0 / 20.0), rtol=1e-4)


class _FakeNet:
    def __init__(self, loudness=None):
        self.metadata = {"loudness": loudness} if loudness is not None else {}

    def process(self, x):
        return x


@unittest.skipUnless(EMBEDDED and PRESETS, "set T3K_EMBEDDED_DIR to a tone-3000/embedded checkout")
class GoldenVectorTests(unittest.TestCase):
    """TONE3000's own reference input/output for the A2-Full and A2-Lite shapes."""

    def _weights(self, name):
        raw = open(os.path.join(EMBEDDED, "weights", name), "rb").read()
        self.assertEqual(raw[:4], b"BMAN")  # 'NAMB' little-endian
        off, count = struct.unpack_from("<II", raw, 12)
        return np.frombuffer(raw, "<f4", count, off).astype(np.float32)

    def _esr_db(self, shape, namb, golden):
        subs = {s["max_value"]: s["model"] for s in _nam_blocks(PRESETS[0])[0][2]["config"]["submodels"]}
        weights = self._weights(namb)
        model = dict(subs[shape])
        model["weights"] = weights.tolist()
        model["config"] = dict(model["config"], head_scale=float(weights[-1]))
        net = nam.WaveNet(model)
        x = np.fromfile(os.path.join(EMBEDDED, "test", "golden_input.raw"), "<f4")
        ref = np.fromfile(os.path.join(EMBEDDED, "test", golden), "<f4")
        y = np.concatenate([net.process(x[i:i + 512]) for i in range(0, len(x), 512)])
        return 10 * np.log10(np.sum((y - ref) ** 2) / np.sum(ref ** 2))

    def test_a2_full_matches_golden(self):
        self.assertLess(self._esr_db(1, "a2full.namb", "golden_a2full_output.raw"), -120.0)

    def test_a2_lite_matches_golden(self):
        self.assertLess(self._esr_db(0.5, "a2lite.namb", "golden_a2lite_output.raw"), -120.0)


if __name__ == "__main__":
    unittest.main()
