"""Golden evidence that the registry-driven write path behaves like the old one.

Recorded *before* the registry was wired into the two runtime write paths:
``server.update_parameter`` (the if/elif tree of hardcoded attribute names) and
``GuitarSignalChain.apply_mooer_preset`` (nested settings dict). Each golden
stores the ``state["chain"]`` the API actually returned for one probe, and the
chain ``apply_mooer_preset`` produced for every factory GE150 preset.

The replay test only calls the public entry points -- ``update_parameter()`` and
``apply_mooer_preset()`` -- and compares against the file. It never imports
``engine/param_access.py``, so it stays an independent witness of the rewrite:
if the registry-driven path applies a different attribute, in a different order,
or loses a side effect such as the EQ band reset, the state differs.

Probes are deliberately run on a chain that is nowhere near its defaults (see
``baseline_chain``), so every write is visible, and a few out-of-range probes
pin down where the API clamps and where it does not.

Record with::

    .venv/Scripts/python.exe -m tests.test_registry_wiring --write

Recording refuses to overwrite a golden whose recorded source fingerprint does
not match the working tree, so a rewritten ``server.py`` cannot silently
re-record itself as "unchanged". If the change is deliberate and the sound has
been checked, pass ``--accept-changed-code``.
"""

import argparse
import hashlib
import json
import sys
import unittest
from pathlib import Path

from engine import params
from engine.dsp import GuitarSignalChain
from engine.mooer_preset import FACTORY_GE150_PRESETS
from server import ParamUpdate, engine, update_parameter

ROOT = Path(__file__).parents[1]
GOLDEN_DIR = Path(__file__).parent / "golden"
DISPATCH_GOLDEN = GOLDEN_DIR / "parameter_dispatch.json"
MOOER_GOLDEN = GOLDEN_DIR / "mooer_apply.json"
SOURCES = ("server.py", "engine/dsp.py")

#: Parameters whose sentinel value cannot be derived from the registry: the
#: value has to be one the DSP actually accepts.
PROBE_OVERRIDES = {
    ("amp", "model"): "Twin",
    ("cab", "tube"): "EL34",
    ("cab", "mic"): "MD421",
    ("cab", "ir_name"): "greenback",
}

#: (section, param, value) probes that go past the documented range. They pin
#: the historical clamping: trim/mix/blend clamp to their bounds, the rest of
#: the API stores whatever it is given.
EDGE_PROBES = (
    ("input", "trim", 999.0),
    ("cab", "mix", 5.0),
    ("parallel", "blend", -3.0),
    ("gate", "threshold", -200.0),
    ("mod", "model_id", 99),
    ("eq", "band0", 2.5),
    ("eq", "band3", -4.0),
    ("eq", "band7", 1.0),
)


class GoldenRecordedFromDifferentCode(RuntimeError):
    """Raised instead of overwriting evidence taken from different code."""


def source_fingerprint() -> dict:
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in SOURCES
    }


def probe_value(p: params.Param):
    """A value that is legal for this parameter and never its default."""
    if p.kind == "bool":
        return not p.default
    if p.kind == "int":
        if p.maximum is not None and p.default + 1 <= p.maximum:
            return p.default + 1
        if p.minimum is not None and p.default - 1 >= p.minimum:
            return p.default - 1
        return p.default + 1
    if p.kind == "float":
        # Stay inside the declared range so the probe measures the write, not a
        # clamp; the boundary itself is a fair probe.
        if p.maximum is not None and p.default != p.maximum:
            return float(p.maximum)
        if p.minimum is not None and p.default != p.minimum:
            return float(p.minimum)
        return float(p.default) + 0.1
    if p.kind == "str":
        if p.choices:
            return next(c for c in p.choices if c != p.default)
        return f"{p.default}-probe"
    return [1.0, -2.0, 3.0, -4.0, 5.0, -6.0]


def probes():
    """One probe per settable registry parameter, plus the edge cases."""
    found = []
    for mod in params.MODULES:
        if mod.name == "nam":
            # Its parameters sit behind an optional model; the server keeps its
            # own guarded branch for them.
            continue
        for p in mod.params:
            if p.read_only or p.owner == "server" or p.index_template:
                continue
            value = PROBE_OVERRIDES.get((mod.name, p.key), probe_value(p))
            found.append((mod.name, p.key, value))
    found.extend(EDGE_PROBES)
    return found


def baseline_chain():
    """A chain that is nowhere near its defaults, so a write is always visible.

    Built with plain attribute writes and the DSP's own setters, never through
    the registry, so the baseline itself is not part of what is being tested.
    """
    chain = GuitarSignalChain(sample_rate=48000)
    chain.master_volume = 0.80
    chain.input_trim_db = 2.0
    chain.parallel_enabled = True
    chain.parallel_blend = 0.40

    gate = chain.noise_gate
    gate.enabled = True
    gate.threshold_db = -40.0
    gate.hold_ms = 30.0
    gate.range_db = -50.0
    gate.release_ms = 80.0
    gate.set_timing(gate.attack_ms, gate.release_ms)

    pitch = chain.pitch_shifter
    pitch.enabled = False
    pitch.set_glide(25.0)
    pitch.set_semitones(2.0)
    pitch.cents = 10.0
    pitch.mix = 0.5

    chain.screamer.enabled = True
    chain.screamer.drive = 0.5
    chain.screamer.tone = 0.4
    chain.screamer.level = 0.6
    chain.screamer._update_filter()

    chain.amp.enabled = True
    chain.amp.gain = 0.45
    chain.amp.bass = 0.35
    chain.amp.mid = 0.55
    chain.amp.treble = 0.65
    chain.amp.presence = 0.25
    chain.amp.master = 0.75
    chain.amp.model = "Plexi"
    chain.amp.bright = False

    chain.eq.enabled = True
    chain.eq.set_bands([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], model_id=3)

    chain.cab.enabled = True
    chain.cab.level = 0.9
    chain.cab.set_cutoffs(lowcut_hz=80.0, highcut_hz=7000.0)
    chain.cab.mix = 0.8
    chain.cab.set_tube_and_mic(tube="6L6", mic="SM57", center=40.0, distance=30.0)

    chain.mod.enabled = True
    chain.mod.model_id = 4
    chain.mod.rate = 0.4
    chain.mod.mix = 0.6
    chain.mod.tone = 0.5
    chain.mod.depth = 0.7

    chain.delay.enabled = True
    chain.delay.time_sec = 0.4
    chain.delay.feedback = 0.45
    chain.delay.mix = 0.3
    chain.delay.ducking = True
    chain.delay.duck_depth = 0.55

    chain.reverb.enabled = True
    chain.reverb.decay = 0.6
    chain.reverb.mix = 0.4
    chain.reverb.tone = 0.35
    chain.reverb.reverb_type = "room"
    chain.reverb.ducking = True
    chain.reverb.duck_depth = 0.45
    return chain


def chain_state(state: dict) -> dict:
    """The JSON the browser sees, minus the EQ curve (derived from bands+model).

    Detached through ``json`` so tuples become lists and numpy scalars become
    plain numbers the same way on both sides of the comparison.
    """
    snapshot = json.loads(json.dumps(state["chain"]))
    snapshot["eq"].pop("curve", None)
    return snapshot


def dispatch_results(probe_list):
    results = []
    for section, param, value in probe_list:
        engine.chain = baseline_chain()
        response = update_parameter(ParamUpdate(section=section, param=param, value=value))
        results.append({
            "section": section,
            "param": param,
            "value": value,
            "state": chain_state(response["state"]),
        })
    return results


def mooer_results():
    results = []
    for index, preset in enumerate(FACTORY_GE150_PRESETS):
        engine.chain = baseline_chain()
        engine.chain.apply_mooer_preset(preset)
        results.append({
            "index": index,
            "name": preset.get("preset_name"),
            "state": chain_state(engine.get_state()),
        })
    return results


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def record(accept_changed_code: bool):
    fingerprint = source_fingerprint()
    for path in (DISPATCH_GOLDEN, MOOER_GOLDEN):
        if not path.exists():
            continue
        previous = _read(path).get("sources", {})
        if previous != fingerprint and not accept_changed_code:
            raise GoldenRecordedFromDifferentCode(
                f"{path.name} was recorded from different code. Re-recording now would "
                "destroy the evidence that the rewrite preserves behaviour; pass "
                "--accept-changed-code only after checking the sound."
            )

    GOLDEN_DIR.mkdir(exist_ok=True)
    DISPATCH_GOLDEN.write_text(json.dumps({
        "note": "state['chain'] returned by POST /api/parameter on baseline_chain()",
        "sources": fingerprint,
        "probes": dispatch_results(probes()),
    }, indent=1), encoding="utf-8")
    MOOER_GOLDEN.write_text(json.dumps({
        "note": "state['chain'] after apply_mooer_preset(FACTORY_GE150_PRESETS[i])",
        "sources": fingerprint,
        "presets": mooer_results(),
    }, indent=1), encoding="utf-8")
    print(f"recorded {DISPATCH_GOLDEN.name} and {MOOER_GOLDEN.name}")


class ParameterDispatchGoldenTests(unittest.TestCase):
    """The API still produces the exact state the hardcoded handler produced."""

    @classmethod
    def setUpClass(cls):
        if not DISPATCH_GOLDEN.exists():
            raise unittest.SkipTest("parameter_dispatch.json not recorded")
        cls.golden = _read(DISPATCH_GOLDEN)

    def test_the_probe_list_still_covers_the_registry(self):
        """A parameter added to the registry must get a probe, not silently pass."""
        recorded = {(p["section"], p["param"]) for p in self.golden["probes"]}
        current = {(section, param) for section, param, _ in probes()}
        self.assertEqual(current - recorded, set(),
                         "new parameters have no recorded behaviour; re-record deliberately")
        indexed = {m.name for m in params.MODULES for p in m.params if p.index_template}
        self.assertTrue(indexed, "expected at least one index-addressed parameter")
        for name in indexed:
            self.assertTrue(
                any(section == name and param.startswith("band") for section, param in recorded),
                f"{name} index-addressed parameters have no probe",
            )

    def test_update_parameter_reproduces_the_recorded_state(self):
        recorded = [
            (p["section"], p["param"], p["value"]) for p in self.golden["probes"]
        ]
        replayed = dispatch_results(recorded)
        for expected, actual in zip(self.golden["probes"], replayed):
            with self.subTest(section=expected["section"], param=expected["param"]):
                self.assertEqual(json.dumps(expected["state"], sort_keys=True),
                                 json.dumps(actual["state"], sort_keys=True))


class MooerApplyGoldenTests(unittest.TestCase):
    """apply_mooer_preset still lands on the exact same chain state."""

    @classmethod
    def setUpClass(cls):
        if not MOOER_GOLDEN.exists():
            raise unittest.SkipTest("mooer_apply.json not recorded")
        cls.golden = _read(MOOER_GOLDEN)

    def test_factory_presets_reproduce_the_recorded_state(self):
        replayed = mooer_results()
        self.assertEqual(len(replayed), len(self.golden["presets"]))
        for expected, actual in zip(self.golden["presets"], replayed):
            with self.subTest(preset=expected["name"]):
                self.assertEqual(json.dumps(expected["state"], sort_keys=True),
                                 json.dumps(actual["state"], sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--accept-changed-code", action="store_true")
    args, rest = parser.parse_known_args()
    if args.write:
        record(args.accept_changed_code)
    else:
        unittest.main(argv=[sys.argv[0]] + rest)
