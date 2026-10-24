"""Aliasing guard for the high-gain amp in both live paths.

A 3,217 Hz sine through the 5150 at gain 0.9 (cab off, so only the amp and the
output stage are measured). Energy that is not a harmonic of the input is
aliasing that folded back from above Nyquist; before oversampling it was
-13.5 dB (chain) and -25.1 dB (HD) relative to the fundamental.
"""

import unittest

import numpy as np

from engine.dsp import GuitarSignalChain, soft_clip
from engine.oversample import Oversampler, PeakLimiter
from engine.world_class_dsp import WorldClassAudioProcessor

SR = 48000
F0 = 3217.0
N = 1 << 15
LIMIT_DB = -60.0


def _chain():
    c = GuitarSignalChain(sample_rate=SR)
    c.noise_gate.enabled = False
    c.amp.model = "5150"
    c.amp.gain = 0.9
    c.cab.enabled = False
    return c


def _render(fn, x, block=128):
    return np.concatenate([fn(x[i:i + block]) for i in range(0, len(x), block)])


def non_harmonic_db(y):
    y = np.asarray(y, np.float64)[len(y) // 2:]
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / SR)
    harmonic = np.zeros_like(f, bool)
    for k in range(1, int(SR / 2 / F0) + 1):
        harmonic |= np.abs(f - k * F0) < 15
    audible = (f > 20) & (f < 20000)
    fundamental = spec[np.abs(f - F0) < 15].sum()
    return 10 * np.log10(spec[audible & ~harmonic].sum() / fundamental)


class AliasingTests(unittest.TestCase):
    def setUp(self):
        t = np.arange(N) / SR
        self.x = (0.3 * np.sin(2 * np.pi * F0 * t)).astype(np.float32)

    def test_chain_path(self):
        self.assertLess(non_harmonic_db(_render(_chain().process, self.x)), LIMIT_DB)

    def test_hd_path(self):
        chain = _chain()
        hd = WorldClassAudioProcessor(SR)
        hd.enabled = True
        hd.stereo_width = 0.0
        y = _render(lambda b: hd.process(chain, b), self.x)
        self.assertLess(non_harmonic_db(y[:, 0]), LIMIT_DB)

    def test_soft_clip_output_stays_under_full_scale_when_driven_2x(self):
        os_ = Oversampler(SR)
        hot = np.sign(self.x) * 2.0  # square wave twice past full scale
        y = _render(lambda b: os_.process(b, soft_clip), hot.astype(np.float32))
        self.assertLess(float(np.max(np.abs(y))), 1.0)

    def test_peak_limiter_holds_the_ceiling_and_leaves_quiet_audio_alone(self):
        lim = PeakLimiter(SR)
        hot = np.column_stack((self.x * 6.0, self.x * 3.0)).astype(np.float32)
        y = _render(lim.process, hot)
        self.assertLessEqual(float(np.max(np.abs(y[2048:]))), lim.ceiling * 1.01)
        quiet = np.column_stack((self.x, self.x)).astype(np.float32)
        q = _render(PeakLimiter(SR).process, quiet)
        np.testing.assert_allclose(q[lim.lookahead:], quiet[:-lim.lookahead], atol=1e-7)

    def test_peak_limiter_is_block_size_invariant(self):
        hot = np.column_stack((self.x * 6.0, self.x * 2.0)).astype(np.float32)
        a = _render(PeakLimiter(SR).process, hot, block=128)
        b = _render(PeakLimiter(SR).process, hot, block=37)
        np.testing.assert_allclose(a, b, atol=1e-6)

    def test_oversampler_is_block_size_invariant(self):
        a = _render(lambda b, o=Oversampler(SR): o.process(b, np.tanh), self.x * 3, block=128)
        o2 = Oversampler(SR)
        b = _render(lambda blk: o2.process(blk, np.tanh), self.x * 3, block=37)
        np.testing.assert_allclose(a, b, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
