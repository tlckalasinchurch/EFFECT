"""Streaming, zero-latency convolution for the cabinet IR.

``fftconvolve(block, ir)[:len(block)]`` forgets the part of every block's
response that falls after the block, so a long IR loses its low end.  This
class keeps that tail across calls.

The IR is cut into partitions of ``block`` samples.  The first partition is
convolved directly (so the output needs no input from the future); the others
are summed in the frequency domain from a ring of past input spectra, one FFT
pair per ``block`` samples whatever the length of the callback.  Everything is
sized in ``__init__`` -- call it from a control thread, never from the audio
callback -- and ``process`` only fills those arrays.  NumPy still allocates
small temporaries inside the FFT and ufunc calls, so this is *not* an
allocation-free claim.

One instance belongs to one audio thread.  Swapping the IR means building a new
instance and replacing the reference (the old one is simply no longer used).
"""

import numpy as np


class PartitionedConvolver:
    def __init__(self, ir, block=128):
        ir = np.asarray(ir, dtype=np.float64).ravel()
        if ir.size < 1:
            raise ValueError("IR must contain at least 1 sample")
        B = self.B = int(block)
        P = self.P = -(-ir.size // B)
        padded = np.zeros(P * B)
        padded[:ir.size] = ir
        parts = padded.reshape(P, B)
        bins = B + 1
        self.h0 = parts[0].copy()
        self.H0 = np.fft.rfft(parts[0], 2 * B)
        self.M = P - 1                      # partitions handled in the frequency domain
        if self.M:
            # Oldest input spectrum pairs with the last partition, so keep the
            # partition spectra newest-last to match the ring window below.
            self.Hrev = np.fft.rfft(parts[1:], 2 * B, axis=1)[::-1].copy()
            self.ring = np.zeros((2 * self.M, bins), dtype=np.complex128)
        self.xb = np.zeros(B)               # input of the block being filled
        self.f = np.zeros(B)                # later partitions' first half, for this block
        self.c = np.zeros(B)                # previous block's tail, for this block
        self.U = np.zeros(bins, dtype=np.complex128)
        self.pos = 0
        self.w = 0

    def reset(self):
        """Forget all history (same IR)."""
        for a in (self.xb, self.f, self.c, self.U):
            a.fill(0)
        if self.M:
            self.ring.fill(0)
        self.pos = 0
        self.w = 0

    def process(self, x):
        """Convolve ``x`` (any length >= 0); returns ``len(x)`` samples."""
        n = len(x)
        out = np.empty(n)
        B = self.B
        i = 0
        while i < n:
            pos = self.pos
            m = min(n - i, B - pos)
            self.xb[pos:pos + m] = x[i:i + m]
            head = np.convolve(self.xb[:pos + m], self.h0)[pos:pos + m]
            out[i:i + m] = head + self.f[pos:pos + m] + self.c[pos:pos + m]
            i += m
            self.pos = pos + m
            if self.pos == B:
                self._complete_block()
                self.pos = 0
        return out

    def _complete_block(self):
        B = self.B
        X = np.fft.rfft(self.xb, 2 * B)
        # Tail of this block's response, through partition 0 and every older input.
        self.c[:] = np.fft.irfft(X * self.H0 + self.U, 2 * B)[B:]
        if self.M:
            M = self.M
            self.ring[self.w] = X
            self.ring[self.w + M] = X
            self.w = (self.w + 1) % M
            # ring[w:w+M] runs oldest -> newest, pairing with Hrev's rows.
            np.einsum("ij,ij->j", self.ring[self.w:self.w + M], self.Hrev, out=self.U)
            self.f[:] = np.fft.irfft(self.U, 2 * B)[:B]
        # (no later partitions: U and f stay zero)
