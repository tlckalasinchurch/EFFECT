"""Characterization tests for the audio path, recorded before the signal-chain refactor.

PURPOSE
-------
These tests are a **change detector**, not a correctness oracle. The baseline
in ``tests/golden/dsp_chain_baseline.json`` was recorded from the code as it
stood *before* any signal-chain refactoring, so a refactor that changes the
sound is caught. It says nothing about whether that sound matches a real amp --
nobody has compared the output with the hardware, so do not cite these numbers
as audio quality evidence.

RECORDED CONDITIONS (also stored in the baseline file)
------------------------------------------------------
* sample rate 48000 Hz, block size 128 samples, 1280 samples total (10 blocks)
* input: 110/220/330 Hz sine stack + 0.005 RMS white noise, seed 7
* default constructor state of ``GuitarSignalChain`` plus the per-case tweaks

KNOWN LIMITATION: this chain is **not block-size invariant** -- the same input
rendered at 128 vs 512 samples differs by up to 0.21 peak. That is existing
behaviour (the gate follows block RMS), so the baseline is only meaningful at
the 128-sample block size and is deliberately not re-recorded per block size.

The NAM test at the bottom is different: it is analytic. A one-layer, kernel-1
WaveNet collapses to a closed-form expression, so the expected output is
derived from the maths rather than from the implementation's own output.
"""

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np

from engine.dsp import GuitarSignalChain
from engine import nam

SAMPLE_RATE = 48000
BLOCK = 128
LENGTH = 1280
BASELINE_PATH = Path(__file__).parent / "golden" / "dsp_chain_baseline.json"
ATOL = 1e-6


def render_input(length=LENGTH, seed=7):
    """Deterministic guitar-ish test signal (no chain code involved)."""
    t = np.arange(length) / float(SAMPLE_RATE)
    rng = np.random.default_rng(seed)
    x = (
        0.25 * np.sin(2 * np.pi * 110 * t)
        + 0.10 * np.sin(2 * np.pi * 220 * t)
        + 0.05 * np.sin(2 * np.pi * 330 * t)
        + 0.005 * rng.standard_normal(length)
    )
    return x.astype(np.float32)


def render(chain, x, block=BLOCK):
    """Process with an explicit window so the result does not depend on defaults."""
    parts = [chain.process(x[i:i + block]) for i in range(0, len(x), block)]
    return np.concatenate(parts)


def use_synthetic_cab(chain, key):
    """Use the built-in IR generator, never custom_irs/*.wav.

    ``select_cab`` prefers a real WAV from ``custom_irs/`` when one exists, so
    the same call renders differently on a machine that has those files. These
    tests must not depend on the contents of the user's IR folder.
    """
    cab = chain.cab
    cab.set_ir_data(cab._generate_synthetic_ir(key), cab.CAB_PROFILES[key]["name"])
    return chain


def configure_default():
    return GuitarSignalChain(sample_rate=SAMPLE_RATE)


def configure_drive_amp():
    chain = GuitarSignalChain(sample_rate=SAMPLE_RATE)
    chain.noise_gate.enabled = False
    chain.screamer.enabled = True
    chain.screamer.drive = 0.65
    chain.screamer.level = 0.80
    chain.amp.model = "Plexi"
    chain.amp.gain = 0.80
    chain.amp.master = 0.65
    use_synthetic_cab(chain, "greenback")
    return chain


def configure_dual_delay_reverb():
    chain = GuitarSignalChain(sample_rate=SAMPLE_RATE)
    chain.noise_gate.enabled = False
    chain.mod.enabled = True
    chain.mod.model_id = 12  # ModulationProcessor defaults to an int model id
    chain.delay.enabled = True
    chain.delay.time_sec = 0.28
    chain.delay.feedback = 0.30
    chain.delay.mix = 0.35
    chain.reverb.enabled = True
    chain.reverb.decay = 0.45
    chain.reverb.mix = 0.25
    return chain


CASES = {
    "default": configure_default,
    "drive_amp": configure_drive_amp,
    "dual_delay_reverb": configure_dual_delay_reverb,
}


def signature(y):
    """Compact fingerprint: a wide strided sample set plus per-block energy."""
    step = max(1, len(y) // 24)
    return {
        "peak": round(float(np.max(np.abs(y))), 9),
        "rms": round(float(np.sqrt(np.mean(y.astype(np.float64) ** 2))), 9),
        "samples": [round(float(v), 9) for v in y[::step][:24]],
        "block_rms": [
            round(float(np.sqrt(np.mean(y[i:i + BLOCK].astype(np.float64) ** 2))), 9)
            for i in range(0, len(y), BLOCK)
        ],
    }


def build_baseline():
    x = render_input()
    return {
        "_metadata": {
            "purpose": (
                "Characterization baseline recorded from the pre-refactor code. "
                "Detects behaviour change only; not evidence of correctness."
            ),
            "sample_rate": SAMPLE_RATE,
            "block_size": BLOCK,
            "length": LENGTH,
            "input": "110/220/330 Hz sine stack + 0.005 RMS white noise, seed 7",
            "cab_ir": "built-in synthetic IR generator only; custom_irs/*.wav is deliberately not read",
            "dsp_py_sha256": hashlib.sha256(
                (Path(__file__).parents[1] / "engine" / "dsp.py").read_bytes()
            ).hexdigest(),
        },
        "cases": {name: signature(render(factory(), x)) for name, factory in CASES.items()},
    }


class DspChainCharacterizationTests(unittest.TestCase):
    def test_baseline_file_is_present_and_complete(self):
        self.assertTrue(BASELINE_PATH.exists(), "run this module as a script to write the baseline")
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(data["cases"]), set(CASES))

    def test_recorded_cases_still_render_the_same_audio(self):
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

    def test_rendering_is_deterministic(self):
        x = render_input()
        first = render(configure_dual_delay_reverb(), x)
        second = render(configure_dual_delay_reverb(), x)
        np.testing.assert_array_equal(first, second)

    def test_every_module_disabled_is_a_transparent_passthrough(self):
        """Bypass must stay bit-exact: it is the only path we can assert absolutely."""
        chain = GuitarSignalChain(sample_rate=SAMPLE_RATE)
        for name in ("noise_gate", "pitch_shifter", "screamer", "amp", "cab", "mod", "delay", "reverb"):
            getattr(chain, name).enabled = False
        chain.master_volume = 1.0
        x = render_input()
        np.testing.assert_array_equal(render(chain, x), x)

    def test_silence_in_stays_silent(self):
        chain = GuitarSignalChain(sample_rate=SAMPLE_RATE)
        out = chain.process(np.zeros(1024, np.float32))
        self.assertTrue(np.isfinite(out).all())
        self.assertEqual(float(np.max(np.abs(out))), 0.0)

    def test_loud_input_stays_finite_and_clipped(self):
        x = np.clip(render_input() * 20.0, -1.0, 1.0).astype(np.float32)
        out = render(GuitarSignalChain(sample_rate=SAMPLE_RATE), x)
        self.assertTrue(np.isfinite(out).all())
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0)


class NamAnalyticTests(unittest.TestCase):
    """A kernel-1, one-layer WaveNet is a fixed closed-form expression."""

    W = {
        "rechannel": 0.75,
        "conv": -0.4,
        "conv_b": 0.05,
        "mixin": 0.3,
        "l1x1": 0.2,
        "l1x1_b": -0.01,
        "head": 1.3,
        "head_b": 0.02,
        "head_scale": 1.1,
    }

    def _model(self):
        layer = {
            "input_size": 1,
            "condition_size": 1,
            "channels": 1,
            "bottleneck": 1,
            "kernel_sizes": [1],
            "dilations": [1],
            "activation": ["Tanh"],
            "gating_mode": ["none"],
            "secondary_activation": [None],
            "head": {"out_channels": 1, "kernel_size": 1, "bias": True},
            "layer1x1": {"active": True, "groups": 1},
        }
        w = self.W
        return {
            "architecture": "WaveNet",
            "sample_rate": 48000,
            "config": {
                "layers": [layer],
                "head_scale": w["head_scale"],
            },
            "weights": [
                w["rechannel"],
                w["conv"], w["conv_b"],
                w["mixin"],
                w["l1x1"], w["l1x1_b"],
                w["head"], w["head_b"],
                w["head_scale"],
            ],
        }

    def test_single_layer_matches_closed_form(self):
        net = nam.WaveNet(self._model())
        x = np.linspace(-0.5, 0.5, 64).astype(np.float32)
        w = self.W
        inner = w["conv"] * (w["rechannel"] * x) + w["conv_b"] + w["mixin"] * x
        expected = w["head_scale"] * (w["head"] * np.tanh(inner) + w["head_b"])
        np.testing.assert_allclose(net.process(x), expected, atol=1e-6)

    def test_kernel_one_model_has_no_temporal_state(self):
        """With every history empty, feeding blocks or the whole buffer must agree."""
        a = nam.WaveNet(self._model())
        b = nam.WaveNet(self._model())
        x = np.linspace(-0.4, 0.4, 256).astype(np.float32)
        whole = a.process(x)
        blocks = np.concatenate([b.process(x[i:i + 32]) for i in range(0, 256, 32)])
        np.testing.assert_allclose(blocks, whole, atol=1e-6)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Write the DSP characterization baseline.")
    parser.add_argument("--write", action="store_true", help="record the baseline from the current code")
    args = parser.parse_args()
    if not args.write:
        parser.error("pass --write to record the baseline")
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(build_baseline(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {BASELINE_PATH}")
