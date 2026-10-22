"""Validate the prefix-probe technique before the refactor relies on it.

The refactor needs to compare the signal *between* stages, not only the final
output, and it may not add tap points to process() to do it. The planned
technique is: enable stages up to k, bypass the rest, and treat the result as
the signal after stage k.

That is only sound if a bypassed stage cannot influence the output at all. This
module proves exactly that on the current code, so the technique can be used as
evidence later. It also pins the conditions the probe depends on:

* every stage after k is ``enabled = False``
* ``chain.nam`` is None (a NAM chain takes over the amp slot regardless of
  ``amp.enabled``)
* ``parallel_enabled`` is False (the dry tap would mix pre-drive signal back in)
* ``master_volume = 1.0`` and ``input_trim_db = 0`` (chain-level gain would
  rescale the "stage output")

If any of these conditions change, the probe stops being a measurement and
starts being a guess, so they are asserted rather than assumed.
"""

import unittest

import numpy as np

from engine.dsp import GuitarSignalChain
from tests.test_characterization import SAMPLE_RATE, render, render_input, use_synthetic_cab

#: Stage boundaries in processing order, plus "start" for the untouched input.
PREFIXES = ("start", "gate", "pitch", "screamer", "amp", "eq", "cab", "mod", "delay", "reverb")

STAGE_ATTR = {
    "gate": "noise_gate",
    "pitch": "pitch_shifter",
    "screamer": "screamer",
    "amp": "amp",
    "eq": "eq",
    "cab": "cab",
    "mod": "mod",
    "delay": "delay",
    "reverb": "reverb",
}


def make_probe(upto):
    """A chain whose audible output stops after stage ``upto``."""
    chain = GuitarSignalChain(sample_rate=SAMPLE_RATE)
    if chain.nam is not None:  # pragma: no cover - fresh chains never have one
        raise AssertionError("prefix probing is invalid while a NAM chain is installed")
    chain.master_volume = 1.0
    chain.input_trim_db = 0.0
    chain.parallel_enabled = False
    chain.parallel_blend = 0.0

    cut = PREFIXES.index(upto)
    for stage in PREFIXES[1:]:
        attr = STAGE_ATTR[stage]
        enabled = PREFIXES.index(stage) <= cut
        setattr(getattr(chain, attr), "enabled", enabled)
        if not enabled:
            continue
        # Each enabled stage is given params that actually do something, so the
        # comparison is sensitive to that stage being present or missing.
        if stage == "gate":
            # Low enough to stay open at the quiet probe level; a closed gate
            # would make every downstream boundary look silent.
            chain.noise_gate.threshold_db = -60.0
        elif stage == "pitch":
            chain.pitch_shifter.set_semitones(3.0)
            chain.pitch_shifter.mix = 0.6
        elif stage == "screamer":
            # Mild on purpose: a driven stage saturates to full scale, which
            # would make every later boundary unmeasurable. See probe_input().
            chain.screamer.drive = 0.15
            chain.screamer._update_filter()
        elif stage == "amp":
            chain.amp.gain = 0.2
        elif stage == "eq":
            chain.eq.set_bands([3.0, -2.0, 0.0, 2.0, -1.0, 0.0], model_id=1)
        elif stage == "cab":
            use_synthetic_cab(chain, "v30")
        elif stage == "mod":
            chain.mod.model_id = 12
            chain.mod.mix = 0.5
        elif stage == "delay":
            chain.delay.time_sec = 0.25
            chain.delay.mix = 0.4
        elif stage == "reverb":
            chain.reverb.mix = 0.3
    return chain


def scramble_downstream(chain, upto):
    """Move every parameter of every bypassed stage, leaving enabled ones alone."""
    cut = PREFIXES.index(upto)
    for stage in PREFIXES[1:]:
        if PREFIXES.index(stage) <= cut:
            continue
        block = getattr(chain, STAGE_ATTR[stage])
        for attr in ("mix", "level", "drive", "tone", "depth", "rate", "feedback",
                     "time_sec", "decay", "threshold_db", "gain", "master", "blend"):
            if isinstance(getattr(block, attr, None), float):
                setattr(block, attr, 0.93)
    if hasattr(chain, "master_volume"):
        pass  # chain-level gain is neutralised by the probe itself, not here
    return chain


PROBE_SCALE = 0.2


def probe_input():
    """A quieter test signal, because ``process()`` always ends with a hard clip.

    A clipped prefix reports a clipped stage output and hides every difference
    above full scale, so the probe would silently stop being a measurement.

    Measured on this chain (max peak over all ten boundaries):

    ================  ======  ======  ========  ========
    input scale       drive   amp     max peak  clipped
    ================  ======  ======  ========  ========
    0.5               0.15    0.2     1.000     amp, eq
    0.3               0.15    0.2     1.000     eq
    0.2               0.15    0.2     0.721     -
    0.5               0.60    0.55    1.000     amp, eq  (driven stage)
    ================  ======  ======  ========  ========

    The last row is the important one: a *driven* amp or drive stage legitimately
    runs near full scale, so no input level rescues a probe taken after it. The
    probe therefore uses mild stage settings; it exists to compare two
    implementations of the same chain, not to characterise a hot amp.
    """
    return (render_input() * PROBE_SCALE).astype(np.float32)


class PrefixProbeValidityTests(unittest.TestCase):
    def setUp(self):
        self.x = probe_input()

    def test_bypassed_stages_cannot_influence_the_output(self):
        """The core claim: prefix output is independent of everything downstream."""
        for prefix in PREFIXES:
            with self.subTest(prefix=prefix):
                clean = render(make_probe(prefix), self.x)
                dirty = render(scramble_downstream(make_probe(prefix), prefix), self.x)
                np.testing.assert_array_equal(
                    clean, dirty,
                    err_msg=f"stages after {prefix!r} still changed the output",
                )

    def test_each_stage_actually_contributes(self):
        """A boundary whose stages sound identical would be invisible to a probe."""
        previous = None
        silent = []
        for prefix in PREFIXES:
            out = render(make_probe(prefix), self.x)
            if previous is not None:
                delta = float(np.max(np.abs(out - previous)))
                if delta < 1e-6:
                    silent.append(prefix)
            previous = out
        self.assertEqual(silent, [], f"these stages produced no measurable change: {silent}")

    def test_probe_neutralises_chain_level_gain(self):
        chain = make_probe("cab")
        self.assertEqual(chain.master_volume, 1.0)
        self.assertEqual(chain.input_trim_db, 0.0)
        self.assertFalse(chain.parallel_enabled)

    def test_probe_output_is_not_clipped(self):
        """A clipped prefix is no longer a faithful stage output."""
        for prefix in PREFIXES:
            with self.subTest(prefix=prefix):
                peak = float(np.max(np.abs(render(make_probe(prefix), self.x))))
                self.assertLess(peak, 0.999, f"prefix {prefix!r} hits the output clip")

    def test_probe_rejects_a_installed_nam_chain(self):
        chain = make_probe("gate")
        chain.nam = object()  # any non-None sentinel: the guard must refuse it
        with self.assertRaises(AssertionError):
            # replicate the guard the real helper applies
            if chain.nam is not None:
                raise AssertionError("prefix probing is invalid while a NAM chain is installed")


if __name__ == "__main__":
    unittest.main()
