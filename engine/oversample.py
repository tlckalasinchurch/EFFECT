"""Stateful oversampling for memoryless nonlinearities (tanh stages, clippers).

A waveshaper run at the base rate folds every harmonic above Nyquist back into
the audible band as inharmonic fizz. Running it at ``factor`` times the rate,
behind an anti-imaging filter and in front of an anti-aliasing filter, keeps
those harmonics out.

The filters are elliptic IIR (minimum phase), so the added latency is a few
samples rather than the tens a linear-phase FIR of the same steepness costs.
Their state is kept across blocks, so block size does not change the output.
"""

import math

import numpy as np
from scipy import signal
from numpy.lib.stride_tricks import sliding_window_view


class PeakLimiter:
    """Lookahead peak limiter with stereo-linked, smoothly moving gain.

    Unlike a waveshaper it never bends the waveform, so it adds no harmonics and
    needs no oversampling; transients keep their shape and only the level moves.
    The cost is ``lookahead_ms`` of extra latency.
    """

    def __init__(self, sample_rate, channels=2, ceiling=0.944, lookahead_ms=0.7, release_ms=80.0):
        self.ceiling = float(ceiling)
        self.lookahead = max(1, int(round(sample_rate * lookahead_ms / 1000.0)))
        # Attack reaches ~98% of the target within the lookahead window.
        self._attack = 1.0 - math.exp(-4.0 / self.lookahead)
        self._release = 1.0 - math.exp(-1.0 / (sample_rate * release_ms / 1000.0))
        self._delay = np.zeros((self.lookahead, channels), dtype=np.float32)
        self._gain = 1.0

    def process(self, x):
        n = len(x)
        buf = np.concatenate((self._delay, x))
        self._delay = buf[n:].copy()
        peak = np.max(np.abs(buf), axis=1)
        need = np.minimum(1.0, self.ceiling / np.maximum(peak, 1e-9))
        target = sliding_window_view(need, self.lookahead + 1).min(axis=1)  # one per output sample
        gains = np.empty(n)
        g, att, rel = self._gain, self._attack, self._release
        for i in range(n):  # n is a block (<= a few hundred), cheap next to the DSP around it
            t = target[i]
            g += (t - g) * (att if t < g else rel)
            gains[i] = g
        self._gain = g
        return (buf[:n] * gains[:, None]).astype(np.float32)


class Oversampler:
    def __init__(self, sample_rate, factor=8, stop_db=90.0):
        self.factor = int(factor)
        high = float(sample_rate) * self.factor
        # Pass up to 20 kHz; stop at fs - pass, so anything that still folds
        # back on decimation lands above the passband.
        f_pass = min(20000.0, 0.42 * sample_rate)
        f_stop = sample_rate - f_pass
        order, wn = signal.ellipord(f_pass, f_stop, 0.1, stop_db, fs=high)
        self._sos = signal.ellip(order, 0.1, stop_db, wn, btype="low", output="sos", fs=high)
        self.reset()

    def reset(self):
        self._zi_up = np.zeros((self._sos.shape[0], 2))
        self._zi_down = np.zeros((self._sos.shape[0], 2))

    def process(self, x, shaper):
        """Return ``shaper(x)`` computed at the high rate, at the base rate."""
        L = self.factor
        up = np.zeros(len(x) * L)
        up[::L] = np.asarray(x, dtype=np.float64) * L
        up, self._zi_up = signal.sosfilt(self._sos, up, zi=self._zi_up)
        y, self._zi_down = signal.sosfilt(self._sos, shaper(up), zi=self._zi_down)
        return y[::L].astype(np.float32)
