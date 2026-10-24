"""Golden sweep and CPU budget for the HD stereo path (WorldClassAudioProcessor).

When the HD engine is switched on, the audio callback calls
``WorldClassAudioProcessor.process`` instead of ``GuitarSignalChain.process``,
so the chain sweep in tests/test_chain_sweep.py says nothing about what the
user hears. This file renders the same twelve scenarios (plus an Ozzy_Neural
case) through the HD path and pins left and right separately.

Like the chain sweep it is a change detector, not a correctness oracle.

Record with::

    .venv/Scripts/python.exe -m tests.test_hd_sweep --write

Recording refuses to overwrite a golden taken from different DSP code; pass
``--accept-changed-dsp`` only after the new sound has been checked by ear.
"""

import argparse
import hashlib
import json
import sys
import time
import unittest
from pathlib import Path

import numpy as np

from engine.world_class_dsp import WorldClassAudioProcessor
from tests.test_characterization import ATOL, BLOCK, LENGTH, SAMPLE_RATE, render_input, signature
from tests.test_chain_sweep import CASES as CHAIN_CASES, _base

BASELINE_PATH = Path(__file__).parent / "golden" / "hd_chain_sweep.json"
ENGINE_DIR = Path(__file__).parents[1] / "engine"
FINGERPRINTED = ("dsp.py", "world_class_dsp.py")


def ozzy_neural():
    chain = _base()
    chain.noise_gate.enabled = False
    chain.amp.model = "Ozzy_Neural"
    chain.amp.gain = 0.78
    return chain


CASES = dict(CHAIN_CASES, ozzy_neural=ozzy_neural)


def dsp_fingerprint() -> str:
    h = hashlib.sha256()
    for name in FINGERPRINTED:
        h.update((ENGINE_DIR / name).read_bytes())
    return h.hexdigest()


def render_hd(chain, x, block=BLOCK):
    hd = WorldClassAudioProcessor(sample_rate=SAMPLE_RATE)
    hd.enabled = True
    return np.concatenate([hd.process(chain, x[i:i + block]) for i in range(0, len(x), block)])


def case_signature(y):
    return {"left": signature(y[:, 0]), "right": signature(y[:, 1])}


def build_baseline():
    x = render_input()
    return {
        "_metadata": {
            "purpose": "HD stereo path sweep. Detects behaviour change only; not evidence of correctness.",
            "sample_rate": SAMPLE_RATE,
            "block_size": BLOCK,
            "length": LENGTH,
            "tolerance": ATOL,
            "dsp_sha256": dsp_fingerprint(),
            "fingerprinted": list(FINGERPRINTED),
        },
        "cases": {name: case_signature(render_hd(factory(), x)) for name, factory in CASES.items()},
    }


class GoldenRecordedFromDifferentCode(RuntimeError):
    """Raised instead of overwriting a golden taken from different DSP code."""


def write_baseline(path: Path = BASELINE_PATH, accept_changed_dsp: bool = False):
    current = dsp_fingerprint()
    if path.exists() and not accept_changed_dsp:
        try:
            recorded = json.loads(path.read_text(encoding="utf-8"))["_metadata"]["dsp_sha256"]
        except (OSError, ValueError, KeyError, TypeError):
            recorded = None
        if recorded != current:
            raise GoldenRecordedFromDifferentCode(
                f"{path.name} was recorded from DSP code {recorded[:12] if recorded else 'unreadable'}, "
                f"but the working tree is {current[:12]}. Check the sound, then pass --accept-changed-dsp."
            )
    data = build_baseline()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


class HdSweepTests(unittest.TestCase):
    def test_every_scenario_still_renders_the_same_audio(self):
        self.assertTrue(BASELINE_PATH.exists(), "run this module with --write to record the sweep")
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(data["cases"]), set(CASES))
        x = render_input()
        for name, factory in CASES.items():
            got = case_signature(render_hd(factory(), x))
            for side in ("left", "right"):
                with self.subTest(case=name, side=side):
                    want = data["cases"][name][side]
                    self.assertAlmostEqual(got[side]["peak"], want["peak"], delta=ATOL)
                    self.assertAlmostEqual(got[side]["rms"], want["rms"], delta=ATOL)
                    np.testing.assert_allclose(got[side]["samples"], want["samples"], atol=ATOL, rtol=0)
                    np.testing.assert_allclose(got[side]["block_rms"], want["block_rms"], atol=ATOL, rtol=0)


class HdCpuBudgetTests(unittest.TestCase):
    """Median block time must leave headroom under the deadline.

    shortcut: wall-clock on this machine, median only (p99 is too noisy for a unit
    test); measure p99 in the running app for real-time sign-off.
    """

    def _median_ms(self, fn, block, blocks=400):
        rng = np.random.default_rng(3)
        x = (rng.standard_normal(block) * 0.05).astype(np.float32)
        for _ in range(30):
            fn(x)
        times = []
        for _ in range(blocks):
            t = time.perf_counter()
            fn(x)
            times.append((time.perf_counter() - t) * 1000.0)
        return float(np.median(times))

    def test_full_stack_fits_half_the_deadline(self):
        for path in ("chain", "hd"):
            for block in (128, 256):
                deadline = block / SAMPLE_RATE * 1000.0
                chain = CASES["full_stack"]()
                if path == "chain":
                    fn = chain.process
                else:
                    hd = WorldClassAudioProcessor(sample_rate=SAMPLE_RATE)
                    hd.enabled = True
                    fn = lambda blk, hd=hd, chain=chain: hd.process(chain, blk)
                with self.subTest(path=path, block=block):
                    if path == "hd" and block == 128:
                        self.skipTest("HD at block 128 is known to overrun; the UI asks for buffer 256+")
                    median = self._median_ms(fn, block)
                    self.assertLess(median, deadline * 0.5, f"{path} median {median:.2f} ms vs deadline {deadline:.2f} ms")


def main(argv=None, path=BASELINE_PATH):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="record the baseline from the current code")
    parser.add_argument("--accept-changed-dsp", action="store_true")
    args = parser.parse_args(argv)
    if not args.write:
        parser.error("pass --write to record the baseline")
    try:
        write_baseline(path, accept_changed_dsp=args.accept_changed_dsp)
    except GoldenRecordedFromDifferentCode as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
