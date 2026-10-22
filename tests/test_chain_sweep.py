"""Twelve-scenario golden sweep for the DSP chain, recorded before the refactor.

The three cases in tests/test_characterization.py pin the default chain. They do
not exercise most modules, so a refactor could quietly change the EQ, the
modulation stage or the parallel blend and still pass. This file adds twelve
scenarios that each switch on a different part of the chain.

Same rules as the characterization baseline: it is a change detector, not a
correctness oracle, and it is recorded at 48 kHz / block 128 only because the
chain is not block-size invariant (the gate follows block RMS).

Record with::

    .venv/Scripts/python.exe -m tests.test_chain_sweep --write

Only do that *before* a refactor. Re-recording afterwards on top of a changed
chain would destroy the evidence.
"""

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np

from engine.dsp import GuitarSignalChain
from tests.test_characterization import (
    ATOL,
    BLOCK,
    LENGTH,
    SAMPLE_RATE,
    render,
    render_input,
    signature,
    use_synthetic_cab,
)

BASELINE_PATH = Path(__file__).parent / "golden" / "dsp_chain_sweep.json"


def _base():
    chain = GuitarSignalChain(sample_rate=SAMPLE_RATE)
    chain.master_volume = 0.7  # headroom so no case is pinned at the output clip
    return chain


def gate_tight():
    chain = _base()
    chain.noise_gate.threshold_db = -30.0
    chain.noise_gate.release_ms = 30.0
    chain.noise_gate.set_timing(chain.noise_gate.attack_ms, chain.noise_gate.release_ms)
    return chain


def pitch_up():
    chain = _base()
    chain.noise_gate.enabled = False
    chain.pitch_shifter.enabled = True
    chain.pitch_shifter.set_semitones(5.0)
    chain.pitch_shifter.mix = 1.0
    return chain


def pitch_down():
    chain = _base()
    chain.noise_gate.enabled = False
    chain.pitch_shifter.enabled = True
    chain.pitch_shifter.set_semitones(-12.0)
    chain.pitch_shifter.cents = 20.0
    chain.pitch_shifter.mix = 0.8
    return chain


def drive_hot():
    chain = _base()
    chain.screamer.enabled = True
    chain.screamer.drive = 0.9
    chain.screamer.tone = 0.3
    chain.screamer.level = 0.9
    chain.screamer._update_filter()
    chain.amp.gain = 0.4
    return chain


def amp_clean():
    chain = _base()
    chain.noise_gate.enabled = False
    chain.amp.model = "Twin"
    chain.amp.gain = 0.2
    chain.amp.bass = 0.7
    chain.amp.mid = 0.4
    chain.amp.treble = 0.8
    chain.amp.presence = 0.3
    chain.amp.bright = True
    return chain


def cab_greenback_cuts():
    chain = _base()
    use_synthetic_cab(chain, "greenback")
    chain.cab.set_cutoffs(lowcut_hz=90.0, highcut_hz=6000.0)
    chain.cab.set_tube_and_mic(mic="SM57", center=30.0, distance=10.0)
    chain.cab.mix = 0.85
    return chain


def eq_moore():
    chain = _base()
    chain.eq.enabled = True
    chain.eq.set_bands([4.0, -2.0, 0.0, 3.0, -1.0, 0.0], model_id=1)
    return chain


def eq_studio():
    chain = _base()
    chain.eq.enabled = True
    chain.eq.set_bands([80.0, 3.0, -2.0, 2.0, 4.0, 9000.0], model_id=5)
    return chain


def mod_chorus():
    chain = _base()
    chain.mod.enabled = True
    chain.mod.model_id = 12
    chain.mod.rate = 0.3
    chain.mod.depth = 0.8
    chain.mod.mix = 0.6
    return chain


def delay_long():
    chain = _base()
    chain.delay.enabled = True
    chain.delay.time_sec = 0.5
    chain.delay.feedback = 0.55
    chain.delay.mix = 0.5
    return chain


def reverb_hall():
    chain = _base()
    chain.reverb.enabled = True
    chain.reverb.decay = 0.85
    chain.reverb.mix = 0.45
    chain.reverb.tone = 0.35
    chain.reverb.reverb_type = "hall"
    return chain


def full_stack():
    chain = GuitarSignalChain(sample_rate=SAMPLE_RATE)
    chain.master_volume = 0.45
    chain.screamer.enabled = True
    chain.screamer.drive = 0.5
    chain.screamer._update_filter()
    chain.amp.gain = 0.5
    use_synthetic_cab(chain, "v30")
    chain.eq.enabled = True
    chain.eq.set_bands([2.0, -1.0, 1.0, 0.0, 0.0, 0.0], model_id=1)
    chain.mod.enabled = True
    chain.mod.model_id = 12
    chain.mod.mix = 0.35
    chain.delay.enabled = True
    chain.delay.time_sec = 0.3
    chain.delay.mix = 0.3
    chain.reverb.enabled = True
    chain.reverb.mix = 0.25
    chain.parallel_enabled = True
    chain.parallel_blend = 0.35
    return chain


CASES = {
    "gate_tight": gate_tight,
    "pitch_up": pitch_up,
    "pitch_down": pitch_down,
    "drive_hot": drive_hot,
    "amp_clean": amp_clean,
    "cab_greenback_cuts": cab_greenback_cuts,
    "eq_moore": eq_moore,
    "eq_studio": eq_studio,
    "mod_chorus": mod_chorus,
    "delay_long": delay_long,
    "reverb_hall": reverb_hall,
    "full_stack": full_stack,
}


def build_baseline():
    x = render_input()
    return {
        "_metadata": {
            "purpose": (
                "Twelve-scenario DSP sweep recorded before the signal-chain refactor. "
                "Detects behaviour change only; not evidence of correctness."
            ),
            "sample_rate": SAMPLE_RATE,
            "block_size": BLOCK,
            "length": LENGTH,
            "input": "110/220/330 Hz sine stack + 0.005 RMS white noise, seed 7",
            "cab_ir": "built-in synthetic IR generator only; custom_irs/*.wav is deliberately not read",
            "tolerance": ATOL,
            "dsp_py_sha256": hashlib.sha256(
                (Path(__file__).parents[1] / "engine" / "dsp.py").read_bytes()
            ).hexdigest(),
        },
        "cases": {name: signature(render(factory(), x)) for name, factory in CASES.items()},
    }


class DspChainSweepTests(unittest.TestCase):
    def test_baseline_is_present_and_covers_every_case(self):
        self.assertTrue(BASELINE_PATH.exists(), "run this module as a script to record the sweep")
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(data["cases"]), 12)
        self.assertEqual(set(data["cases"]), set(CASES))

    def test_every_scenario_still_renders_the_same_audio(self):
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        x = render_input()
        for name, factory in CASES.items():
            with self.subTest(case=name):
                got = signature(render(factory(), x))
                want = data["cases"][name]
                self.assertAlmostEqual(got["peak"], want["peak"], delta=ATOL)
                self.assertAlmostEqual(got["rms"], want["rms"], delta=ATOL)
                np.testing.assert_allclose(got["samples"], want["samples"], atol=ATOL, rtol=0)
                np.testing.assert_allclose(got["block_rms"], want["block_rms"], atol=ATOL, rtol=0)

    def test_cases_are_distinguishable_from_each_other(self):
        """A sweep where two scenarios sound alike would hide half the chain."""
        x = render_input()
        rms = {name: signature(render(factory(), x))["rms"] for name, factory in CASES.items()}
        collisions = []
        names = list(rms)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if abs(rms[a] - rms[b]) < 1e-3:
                    collisions.append((a, b))
        self.assertEqual(collisions, [], f"these scenarios are indistinguishable: {collisions}")

    def test_no_case_is_pinned_at_the_output_clip(self):
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        pinned = [name for name, sig in data["cases"].items() if sig["peak"] >= 0.999]
        self.assertEqual(pinned, [], f"clipped scenarios compress differences: {pinned}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Record the 12-case DSP sweep baseline.")
    parser.add_argument("--write", action="store_true", help="record from the current code")
    args = parser.parse_args()
    if not args.write:
        parser.error("pass --write to record the sweep")
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(build_baseline(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {BASELINE_PATH}")
