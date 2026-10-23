"""Tests for RigDocument v2 and the legacy settings_json adapter.

The audit test at the bottom reads the real presets.db in SQLite read-only
mode and proves two things at once: every stored preset converts, and the file
is untouched afterwards.
"""

import ast
import hashlib
import inspect
import json
import re
import sqlite3
import unittest
from pathlib import Path

import numpy as np

from engine import params, rigdoc
from engine.dsp import GuitarSignalChain
from tests.test_characterization import SAMPLE_RATE, render, render_input, use_synthetic_cab
from tests.test_chain_prefix_probe import make_probe

ROOT = Path(__file__).parents[1]
DB_PATH = ROOT / "presets.db"

FULL_V1 = {
    "master_volume": 0.8,
    "input": {"trim_db": 3.0},
    "gate": {"enabled": True, "threshold": -55.0, "hold_ms": 50.0, "range_db": -60.0, "release_ms": 80.0},
    "screamer": {"enabled": True, "drive": 0.4, "tone": 0.6, "level": 0.7},
    "amp": {
        "enabled": True, "gain": 0.65, "bass": 0.55, "mid": 0.5, "treble": 0.6,
        "presence": 0.6, "master": 0.7, "model": "5150", "bright": False,
    },
    "parallel": {"enabled": False, "blend": 0.3},
    "cab": {
        "enabled": True, "ir_name": "Celestion V30 4x12", "level": 1.0, "lowcut": 20.0,
        "highcut": 20000.0, "mix": 1.0, "tube": "OFF", "mic": "SM57", "center": 50.0, "distance": 20.0,
    },
    "eq": {"enabled": False, "model_id": 1, "bands": [0.0] * 6, "curve": [{"f": 100.0, "db": 0.0}]},
    "mod": {"enabled": False, "model_id": 12, "rate": 0.5, "mix": 0.5, "tone": 0.5, "depth": 0.5},
    "delay": {"enabled": True, "time": 0.36, "feedback": 0.35, "mix": 0.25, "ducking": False, "duck_depth": 0.6},
    "reverb": {"enabled": True, "decay": 0.5, "mix": 0.2, "tone": 0.5, "type": "plate",
               "ducking": False, "duck_depth": 0.5},
    "pitch": {"enabled": False, "semitones": 0.0, "target_semitones": 0.0, "cents": 0.0,
              "mix": 1.0, "glide": 0.0},
    "_t3k": {"tone_id": 123, "models": ["x.nam"]},
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class V1RoundTripTests(unittest.TestCase):
    def test_full_v1_round_trip_is_exact(self):
        doc = rigdoc.from_v1(FULL_V1, meta={"id": "p1"})
        self.assertEqual(doc.to_v1(), FULL_V1)

    def test_import_canonicalises_the_order_v1_does_not_have(self):
        """v1 key order is get_state() order (pitch last); processing puts it second."""
        doc = rigdoc.from_v1(FULL_V1)
        self.assertEqual(doc.ordered_types(), params.PROCESS_ORDER)
        self.assertNotEqual(list(FULL_V1), list(doc.ordered_types()))

    def test_round_trip_preserves_every_supported_value(self):
        doc = rigdoc.from_v1(FULL_V1)
        back = doc.to_v1()
        for block in ("gate", "screamer", "amp", "cab", "eq", "mod", "delay", "reverb", "pitch", "parallel", "input"):
            self.assertEqual(back[block], FULL_V1[block], block)
        self.assertEqual(back["master_volume"], 0.8)

    def test_extension_namespace_is_preserved_without_a_warning(self):
        doc = rigdoc.from_v1(FULL_V1)
        self.assertEqual(doc.extras["_t3k"], FULL_V1["_t3k"])
        self.assertFalse([i for i in doc.issues if i.where == "_t3k"])

    def test_derived_mirror_is_kept_but_not_treated_as_a_parameter(self):
        doc = rigdoc.from_v1(FULL_V1)
        pitch = doc.module("pitch")
        self.assertEqual(pitch.params["semitones"], 0.0)
        self.assertEqual(pitch.extras["target_semitones"], 0.0)
        self.assertFalse([i for i in doc.issues if "target_semitones" in i.where])


class AdapterBehaviourTests(unittest.TestCase):
    def test_alias_is_accepted_and_canonicalised(self):
        doc = rigdoc.from_v1({"eq": {"enabled": False, "model_id": 1, "data": [1.0, 2.0, 3.0]}})
        self.assertEqual(doc.module("eq").params["bands"], [1.0, 2.0, 3.0])
        self.assertEqual(doc.to_v1()["eq"]["bands"], [1.0, 2.0, 3.0])

    def test_missing_parameter_is_reported_not_invented(self):
        doc = rigdoc.from_v1({"gate": {"enabled": True}})
        gate = doc.module("gate")
        self.assertNotIn("threshold", gate.params)
        flagged = {i.where for i in doc.issues if i.problem == rigdoc.DEFAULTED}
        self.assertIn("gate.threshold", flagged)
        self.assertEqual(doc.to_v1()["gate"], {"enabled": True})

    def test_absent_section_stays_absent(self):
        doc = rigdoc.from_v1({"gate": {"enabled": True}})
        self.assertIsNone(doc.module("reverb"))
        self.assertNotIn("reverb", doc.to_v1())

    def test_unknown_field_is_preserved_and_reported(self):
        doc = rigdoc.from_v1({"gate": {"enabled": True, "mystery": 7}})
        self.assertEqual(doc.module("gate").extras["mystery"], 7)
        self.assertTrue([i for i in doc.issues if i.problem == rigdoc.UNKNOWN_FIELD])
        self.assertEqual(doc.to_v1()["gate"]["mystery"], 7)

    def test_invalid_value_is_kept_and_reported(self):
        doc = rigdoc.from_v1({"gate": {"threshold": "loud"}})
        self.assertEqual(doc.module("gate").params["threshold"], "loud")
        self.assertTrue([i for i in doc.issues if i.problem == rigdoc.INVALID_VALUE])

    def test_out_of_range_is_reported_but_not_clamped(self):
        doc = rigdoc.from_v1({"gate": {"threshold": -200.0}})
        self.assertEqual(doc.module("gate").params["threshold"], -200.0)
        self.assertTrue([i for i in doc.issues if i.problem == rigdoc.OUT_OF_RANGE])

    def test_slot_ids_are_deterministic(self):
        first = rigdoc.from_v1(FULL_V1)
        second = rigdoc.from_v1(FULL_V1)
        self.assertEqual([m.slot_id for m in first.modules], [m.slot_id for m in second.modules])
        self.assertEqual(len({m.slot_id for m in first.modules}), len(first.modules))

    def test_amp_and_nam_together_is_reported(self):
        doc = rigdoc.from_v1({"amp": {"enabled": True}, "nam": {"enabled": True}})
        self.assertTrue([i for i in doc.issues if i.problem == rigdoc.DUPLICATE_SLOT])

    def test_non_object_settings_are_rejected(self):
        for bad in ([], "text", 5, None):
            with self.subTest(value=bad):
                with self.assertRaises(rigdoc.InvalidDocument):
                    rigdoc.from_v1(bad)

    def test_broken_settings_json_is_rejected(self):
        with self.assertRaises(rigdoc.InvalidDocument):
            rigdoc.from_settings_json("{not json")


class V2DocumentTests(unittest.TestCase):
    def setUp(self):
        self.doc = rigdoc.from_v1(FULL_V1, meta={"id": "p1", "name": "Test"})

    def test_dict_round_trip(self):
        again = rigdoc.RigDocument.from_dict(self.doc.to_dict())
        self.assertEqual(again.to_dict(), self.doc.to_dict())

    def test_json_round_trip(self):
        again = rigdoc.RigDocument.from_json(self.doc.to_json())
        self.assertEqual(again.to_dict(), self.doc.to_dict())
        self.assertEqual(again.to_v1(), FULL_V1)

    def test_unsupported_schema_version_is_rejected(self):
        bad = dict(self.doc.to_dict(), schema_version=99)
        with self.assertRaises(rigdoc.UnsupportedSchemaVersion):
            rigdoc.RigDocument.from_dict(bad)

    def test_unknown_module_type_is_rejected(self):
        bad = dict(self.doc.to_dict())
        bad["modules"] = [{"slot_id": "phaser", "type": "phaser", "enabled": True, "params": {}}]
        with self.assertRaises(rigdoc.UnknownModuleType):
            rigdoc.RigDocument.from_dict(bad)

    def test_stored_order_is_the_processing_order(self):
        self.assertEqual(self.doc.ordered_types(), params.PROCESS_ORDER)

    def test_a_reordered_document_keeps_the_user_order(self):
        reordered = dict(self.doc.to_dict())
        reordered["modules"] = list(reversed(reordered["modules"]))
        doc = rigdoc.RigDocument.from_dict(reordered)
        self.assertEqual(doc.ordered_types(), tuple(reversed(params.PROCESS_ORDER)))
        self.assertEqual([m["type"] for m in doc.to_dict()["modules"]], list(reversed(params.PROCESS_ORDER)))

    def test_effective_params_fill_defaults_only_at_read_time(self):
        doc = rigdoc.from_v1({"gate": {"enabled": True}})
        self.assertNotIn("threshold", doc.module("gate").params)
        self.assertEqual(doc.effective_params("gate")["threshold"], -55.0)
        self.assertEqual(doc.to_v1()["gate"], {"enabled": True})

    def test_second_instance_of_a_type_is_an_error(self):
        doc = rigdoc.from_v1({"delay": {"enabled": True}, "gate": {"enabled": True}})
        duplicate = dict(doc.to_dict())
        duplicate["modules"] = duplicate["modules"] + [
            {"slot_id": "delay-2", "type": "delay", "enabled": True, "params": {"mix": 0.5}}
        ]
        loaded = rigdoc.RigDocument.from_dict(duplicate)
        self.assertEqual([i.problem for i in loaded.errors], [rigdoc.DUPLICATE_TYPE])
        # Nothing is dropped: the document still carries both instances.
        self.assertEqual(len(loaded.modules), 3)

    def test_amp_and_nam_together_is_an_error(self):
        doc = rigdoc.from_v1({"amp": {"enabled": True}, "nam": {"enabled": True}})
        self.assertIn(rigdoc.DUPLICATE_SLOT, [i.problem for i in doc.errors])

    def test_parallel_tap_is_frozen_after_pitch(self):
        self.assertEqual(self.doc.tap_after, "pitch")
        self.assertEqual(rigdoc.PARALLEL_TAP_AFTER, "pitch")
        # and it must not leak into the legacy shape
        self.assertNotIn("tap_after", self.doc.to_v1())

    def test_parallel_blend_point_is_frozen_after_cab(self):
        """The wet path rejoins after the cab; mod/delay/reverb stay fully wet."""
        self.assertEqual(self.doc.blend_after, "cab")
        self.assertEqual(rigdoc.PARALLEL_BLEND_AFTER, "cab")
        self.assertEqual(rigdoc.PARALLEL_ANCHORS, ("pitch", "cab"))
        for anchor in rigdoc.PARALLEL_ANCHORS:
            self.assertNotIn(anchor, [k for k in self.doc.to_v1() if "anchor" in k or "after" in k])

    def test_default_order_keeps_the_tap_before_the_blend(self):
        self.assertTrue(self.doc.parallel_tap_is_reachable())

    def test_a_reorder_that_crosses_an_anchor_is_detectable(self):
        """Moving pitch past the cab would put distortion inside the dry tap."""
        doc = rigdoc.from_v1(FULL_V1)
        tainted = doc.to_dict()
        order = [m["type"] for m in tainted["modules"]]
        order.remove("pitch")
        order.insert(order.index("cab") + 1, "pitch")
        by_type = {m["type"]: m for m in tainted["modules"]}
        tainted["modules"] = [by_type[t] for t in order]
        loaded = rigdoc.RigDocument.from_dict(tainted)
        self.assertEqual(list(loaded.ordered_types()), order)  # order itself is kept
        self.assertFalse(loaded.parallel_tap_is_reachable())
        self.assertTrue(doc.parallel_tap_is_reachable())

    def test_chain_level_modules_live_outside_the_graph(self):
        self.assertEqual(set(self.doc.chain), {"master", "input", "parallel"})
        self.assertNotIn("parallel", [m.type for m in self.doc.modules])

    def test_adapter_has_no_path_to_audio_processing(self):
        """Static check: the module must not import the DSP or the audio engine."""
        tree = ast.parse((ROOT / "engine" / "rigdoc.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = {"dsp", "audio", "sounddevice", "scipy", "numpy", "engine.dsp", "engine.audio"}
        self.assertFalse(imported & forbidden, f"rigdoc imports {imported & forbidden}")


ATTR_TO_TYPE = {
    "noise_gate": "gate",
    "pitch_shifter": "pitch",
    "screamer": "screamer",
    "amp": "amp",
    "nam": "amp",  # nam replaces amp in the same slot
    "eq": "eq",
    "cab": "cab",
    "mod": "mod",
    "delay": "delay",
    "reverb": "reverb",
}


class ParallelAnchorBindingTests(unittest.TestCase):
    """The anchors are strings; this binds them to the statements in process()."""

    def setUp(self):
        self.source = inspect.getsource(GuitarSignalChain.process)

    def test_stage_calls_follow_the_declared_engine_order(self):
        """PROCESS_ORDER must be what process() actually applies, nam included."""
        attrs = re.findall(r"self\.(\w+)\.process\(", self.source)
        self.assertTrue(attrs, "no stage calls found in process()")
        stages = []
        for attr in attrs:
            self.assertIn(attr, ATTR_TO_TYPE, f"process() calls an undeclared stage: {attr!r}")
            stage = ATTR_TO_TYPE[attr]
            if stage in stages:
                # Only the amp/nam branch may reach its slot twice.
                self.assertEqual(stage, "amp", f"{stage!r} is processed twice")
                continue
            stages.append(stage)
        self.assertEqual(tuple(stages), params.PROCESS_ORDER)

    def test_tap_statement_sits_between_pitch_and_the_drive_stage(self):
        tap = self.source.index("clean_dry = x.copy()")
        self.assertLess(self.source.index("self.pitch_shifter.process("), tap)
        self.assertLess(tap, self.source.index("self.screamer.process("))
        self.assertEqual(ATTR_TO_TYPE["pitch_shifter"], rigdoc.PARALLEL_TAP_AFTER)

    def test_blend_statement_sits_between_the_cab_and_modulation(self):
        blend = self.source.index("blend * clean_dry")
        self.assertLess(self.source.index("self.cab.process("), blend)
        self.assertLess(blend, self.source.index("self.mod.process("))
        self.assertEqual(ATTR_TO_TYPE["cab"], rigdoc.PARALLEL_BLEND_AFTER)


class ParallelTapRuntimeTests(unittest.TestCase):
    def test_blend_at_one_outputs_exactly_the_post_pitch_signal(self):
        """Proves at runtime that the tap holds gate + pitch and nothing else.

        Every stage after the tap is left enabled and set to do something
        extreme: at blend 1.0 none of it may reach the output.
        """
        x = render_input()
        dry_path = make_probe("pitch")

        parallel = GuitarSignalChain(sample_rate=SAMPLE_RATE)
        parallel.master_volume = 1.0
        parallel.input_trim_db = 0.0
        parallel.parallel_enabled = True
        parallel.parallel_blend = 1.0
        parallel.noise_gate.threshold_db = -60.0
        parallel.pitch_shifter.enabled = True
        parallel.pitch_shifter.set_semitones(3.0)
        parallel.pitch_shifter.mix = 0.6
        parallel.screamer.enabled = True
        parallel.screamer.drive = 0.9
        parallel.screamer._update_filter()
        parallel.amp.gain = 1.0
        parallel.eq.enabled = True
        parallel.eq.set_bands([12.0, -12.0, 12.0, -12.0, 12.0, -12.0], model_id=1)
        use_synthetic_cab(parallel, "v30")

        blended = render(parallel, x)
        dry = render(dry_path, x)
        np.testing.assert_array_equal(blended, dry)
        self.assertGreater(float(np.max(np.abs(dry))), 0.01)  # a real signal, not silence


class ParallelBoundaryTests(unittest.TestCase):
    def _document(self, order):
        base = rigdoc.from_v1(FULL_V1)
        by_type = {m.type: m.to_dict() for m in base.modules}
        return rigdoc.RigDocument.from_dict({
            "schema_version": 2,
            "modules": [by_type[t] for t in order],
        })

    def test_reordering_inside_a_group_keeps_the_parallel_meaning(self):
        safe = {
            "gate and pitch swapped in the tap": ["pitch", "gate", "screamer", "amp", "eq", "cab", "mod", "delay", "reverb"],
            "eq and cab swapped in the wet path": ["gate", "pitch", "screamer", "amp", "cab", "eq", "mod", "delay", "reverb"],
            "mod and delay swapped after the blend": ["gate", "pitch", "screamer", "amp", "eq", "cab", "delay", "mod", "reverb"],
            "delay and reverb reversed after the blend": ["gate", "pitch", "screamer", "amp", "eq", "cab", "reverb", "delay", "mod"],
        }
        for label, order in safe.items():
            with self.subTest(reorder=label):
                doc = self._document(order)
                self.assertEqual(list(doc.ordered_types()), order)
                self.assertTrue(doc.parallel_tap_is_reachable())

    def test_reordering_across_a_boundary_is_refused(self):
        unsafe = {
            "reverb moved in front of the tap": ["reverb", "gate", "pitch", "screamer", "amp", "eq", "cab", "mod", "delay"],
            "delay moved inside the wet path": ["gate", "pitch", "screamer", "delay", "amp", "eq", "cab", "mod", "reverb"],
            "screamer moved after the blend": ["gate", "pitch", "amp", "eq", "cab", "mod", "delay", "reverb", "screamer"],
            "pitch moved after the cab": ["gate", "screamer", "amp", "eq", "cab", "pitch", "mod", "delay", "reverb"],
            "cab moved in front of the tap": ["gate", "cab", "pitch", "screamer", "amp", "eq", "mod", "delay", "reverb"],
            "gate moved to the end": ["pitch", "screamer", "amp", "eq", "cab", "mod", "delay", "reverb", "gate"],
        }
        for label, order in unsafe.items():
            with self.subTest(reorder=label):
                self.assertFalse(self._document(order).parallel_tap_is_reachable())

    def test_missing_anchors_are_not_a_crossing(self):
        """Factory presets omit pitch and cab; that alone must not look unsafe."""
        factory = rigdoc.from_v1({
            "gate": {"enabled": True},
            "screamer": {"enabled": False},
            "amp": {"enabled": True},
            "eq": {"enabled": False},
            "delay": {"enabled": True},
            "reverb": {"enabled": True},
        })
        self.assertEqual(factory.ordered_types(), ("gate", "screamer", "amp", "eq", "delay", "reverb"))
        self.assertTrue(factory.parallel_tap_is_reachable())
        self.assertTrue(rigdoc.from_v1({}).parallel_tap_is_reachable())

    def test_a_crossing_is_still_caught_without_the_anchors(self):
        base = rigdoc.from_v1(FULL_V1)
        by_type = {m.type: m.to_dict() for m in base.modules}
        order = ["reverb", "gate", "screamer", "amp", "eq", "mod", "delay"]
        doc = rigdoc.RigDocument.from_dict({
            "schema_version": 2,
            "modules": [by_type[t] for t in order],
        })
        self.assertFalse(doc.parallel_tap_is_reachable())

    def test_nam_takes_the_amp_slot(self):
        base = rigdoc.from_v1(FULL_V1)
        by_type = {m.type: m.to_dict() for m in base.modules}
        by_type["nam"] = {"slot_id": "nam", "type": "nam", "enabled": True, "params": {}}
        order = ["gate", "pitch", "screamer", "nam", "eq", "cab", "mod", "delay", "reverb"]
        doc = rigdoc.RigDocument.from_dict({
            "schema_version": 2,
            "modules": [by_type[t] for t in order],
        })
        self.assertTrue(doc.parallel_tap_is_reachable())
        self.assertEqual(rigdoc._nominal_index("nam"), rigdoc._nominal_index("amp"))

    def test_a_stage_with_no_declared_position_is_refused(self):
        doc = rigdoc.RigDocument(modules=[rigdoc.ModuleConfig(slot_id="phaser", type="phaser")])
        self.assertFalse(doc.parallel_tap_is_reachable())


class RealPresetAuditTests(unittest.TestCase):
    """Reads the shipped database without modifying it."""

    def test_every_stored_preset_round_trips_and_the_file_is_untouched(self):
        if not DB_PATH.exists():
            self.skipTest("presets.db not present")
        before = (sha256(DB_PATH), DB_PATH.stat().st_size, DB_PATH.stat().st_mtime_ns)
        con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT id, name, category, author, settings_json FROM presets"
            ).fetchall()
        finally:
            con.close()

        self.assertGreater(len(rows), 0, "no presets to audit")
        failures = []
        for preset_id, name, category, author, settings_json in rows:
            with self.subTest(preset=preset_id):
                original = json.loads(settings_json)
                doc = rigdoc.from_v1(
                    original, meta={"id": preset_id, "name": name, "category": category, "author": author}
                )
                back = doc.to_v1()
                if back != original:
                    failures.append(preset_id)
                # v2 must also survive its own serialisation
                self.assertEqual(rigdoc.RigDocument.from_json(doc.to_json()).to_dict(), doc.to_dict())
        self.assertEqual(failures, [], f"round trip changed these presets: {failures}")

        after = (sha256(DB_PATH), DB_PATH.stat().st_size, DB_PATH.stat().st_mtime_ns)
        self.assertEqual(before, after, "presets.db was modified by the audit")

    def test_stored_presets_report_only_defaulted_issues(self):
        """Documents the real gap: factory presets simply omit many parameters."""
        con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT settings_json FROM presets").fetchall()
        finally:
            con.close()
        problems = set()
        for (settings_json,) in rows:
            doc = rigdoc.from_v1(json.loads(settings_json))
            problems.update(i.problem for i in doc.issues)
        self.assertTrue(problems <= {rigdoc.DEFAULTED}, f"unexpected issue kinds: {problems}")


if __name__ == "__main__":
    unittest.main()
