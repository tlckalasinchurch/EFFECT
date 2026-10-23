"""The registry-driven write path: engine/param_access.py.

These tests pin the rules the accessor applies, one per kind of parameter, so a
future edit to ``engine/params.py`` gets a local failure instead of a silently
different knob. The end-to-end proof that the HTTP endpoint still behaves like
the old hardcoded handler lives in tests/test_registry_wiring.py.
"""

import unittest

import numpy as np

from engine import param_access, params
from engine.dsp import GuitarSignalChain


def fresh():
    return GuitarSignalChain(sample_rate=48000)


class PlainWriteTests(unittest.TestCase):
    def test_coerces_to_the_declared_kind(self):
        chain = fresh()
        self.assertEqual(param_access.set(chain, "amp", "gain", "0.25"), 0.25)
        self.assertIsInstance(chain.amp.gain, float)
        param_access.set(chain, "screamer", "enabled", 1)
        self.assertIs(chain.screamer.enabled, True)
        param_access.set(chain, "mod", "model_id", "7")
        self.assertEqual(chain.mod.model_id, 7)
        self.assertIsInstance(chain.mod.model_id, int)
        param_access.set(chain, "amp", "model", 5150)
        self.assertEqual(chain.amp.model, "5150")

    def test_chain_owned_parameters_write_the_chain_itself(self):
        chain = fresh()
        param_access.set(chain, "master", "volume", 0.5)
        param_access.set(chain, "parallel", "blend", 0.25)
        self.assertEqual(chain.master_volume, 0.5)
        self.assertEqual(chain.parallel_blend, 0.25)

    def test_section_and_parameter_aliases_resolve(self):
        chain = fresh()
        param_access.set(chain, "output", "volume", 0.4)          # master alias
        param_access.set(chain, "drive", "drive", 0.9)            # screamer alias
        param_access.set(chain, "amp", "tone_stack", "Twin")      # amp.model alias
        param_access.set(chain, "eq", "data", [1, 2, 3, 4, 5, 6])  # eq.bands alias
        self.assertEqual(chain.master_volume, 0.4)
        self.assertEqual(chain.screamer.drive, 0.9)
        self.assertEqual(chain.amp.model, "Twin")
        self.assertEqual(chain.eq.gains, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])


class ClampTests(unittest.TestCase):
    def test_only_the_parameters_that_clamped_historically_clamp(self):
        chain = fresh()
        param_access.set(chain, "input", "trim", 999.0)
        self.assertEqual(chain.input_trim_db, 24.0)
        param_access.set(chain, "input", "trim", -999.0)
        self.assertEqual(chain.input_trim_db, -24.0)

        param_access.set(chain, "cab", "mix", 5.0)
        self.assertEqual(chain.cab.mix, 1.0)
        param_access.set(chain, "parallel", "blend", -3.0)
        self.assertEqual(chain.parallel_blend, 0.0)

        # Everything else stores what it is given, exactly as before the rewrite.
        param_access.set(chain, "gate", "threshold", -200.0)
        param_access.set(chain, "amp", "gain", 9.0)
        self.assertEqual(chain.noise_gate.threshold_db, -200.0)
        self.assertEqual(chain.amp.gain, 9.0)


class SetterTests(unittest.TestCase):
    def test_setter_with_a_required_sibling_gets_the_object_value(self):
        """gate.release must recompute both time constants, like the old branch."""
        chain = fresh()
        param_access.set(chain, "gate", "release", 120.0)
        self.assertEqual(chain.noise_gate.release_ms, 120.0)
        expected = np.exp(-1.0 / (0.120 * chain.sample_rate + 1e-6))
        self.assertAlmostEqual(float(chain.noise_gate.release_coeff), float(expected))

    def test_setter_taking_a_keyword_only_touches_its_own_value(self):
        chain = fresh()
        chain.cab.set_cutoffs(lowcut_hz=90.0, highcut_hz=6000.0)
        param_access.set(chain, "cab", "lowcut", 120.0)
        self.assertEqual(chain.cab.lowcut_hz, 120.0)
        self.assertEqual(chain.cab.highcut_hz, 6000.0)

    def test_setter_with_no_arguments_rebuilds_derived_state(self):
        """screamer.tone writes the value, then _update_filter() rebuilds biquads."""
        chain = fresh()
        before = chain.screamer.b.copy()
        param_access.set(chain, "screamer", "tone", 0.15)
        self.assertEqual(chain.screamer.tone, 0.15)
        self.assertFalse(np.array_equal(before, chain.screamer.b))

    def test_setter_whose_argument_is_not_the_attribute_gets_the_value(self):
        """select_cab(cab_name) and set_semitones(value) name their argument differently."""
        chain = fresh()
        before = chain.cab.ir_name
        param_access.set(chain, "cab", "ir_name", "1960 412")  # -> greenback profile
        self.assertNotEqual(chain.cab.ir_name, before)

        chain.pitch_shifter.set_glide(50.0)
        param_access.set(chain, "pitch", "semitones", 5.0)
        self.assertEqual(chain.pitch_shifter.target_semitones, 5.0)

    def test_assign_false_lets_the_setter_keep_the_audible_value(self):
        """A glide must not jump: only the target moves until the DSP catches up."""
        chain = fresh()
        chain.pitch_shifter.set_glide(100.0)
        chain.pitch_shifter.set_semitones(0.0)
        param_access.set(chain, "pitch", "semitones", 12.0)
        self.assertEqual(chain.pitch_shifter.target_semitones, 12.0)
        self.assertEqual(chain.pitch_shifter.semitones, 0.0)

    def test_eq_model_change_resets_the_bands_but_a_same_model_keeps_them(self):
        chain = fresh()
        chain.eq.set_bands([1, 2, 3, 4, 5, 6], model_id=1)
        param_access.set(chain, "eq", "model_id", 3)
        self.assertEqual(chain.eq.gains, [0.0] * 6)
        chain.eq.set_bands([1, 2, 3, 4, 5, 6], model_id=3)
        param_access.set(chain, "eq", "model_id", 3)
        self.assertEqual(chain.eq.gains, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])


class IndexedTests(unittest.TestCase):
    def test_band_index_edits_one_gain_and_redesigns_filters(self):
        chain = fresh()
        chain.eq.set_bands([0.0] * 6, model_id=1)
        param_access.set(chain, "eq", "band2", 3.5)
        self.assertEqual(chain.eq.gains, [0.0, 0.0, 3.5, 0.0, 0.0, 0.0])

    def test_band_index_beyond_the_list_extends_it(self):
        chain = fresh()
        chain.eq.gains = [0.0] * 3
        param_access.set(chain, "eq", "band7", 1.5)
        self.assertEqual(len(chain.eq.gains), 8)
        self.assertEqual(chain.eq.gains[7], 1.5)
        self.assertEqual(chain.eq.gains[:3], [0.0, 0.0, 0.0])


class ResolveTests(unittest.TestCase):
    def test_unknown_names_raise_key_error(self):
        with self.assertRaises(KeyError):
            param_access.set(fresh(), "gate", "not_a_parameter", 1.0)
        with self.assertRaises(KeyError):
            param_access.set(fresh(), "not_a_block", "gain", 1.0)

    def test_server_owned_and_missing_modules_are_reported(self):
        with self.assertRaises(param_access.ServerOwnedParameter):
            param_access.set(fresh(), "nam", "quality", "full")
        with self.assertRaises(param_access.ModuleNotInstalled):
            param_access.set(fresh(), "nam", "enabled", True)


class ApplySettingsTests(unittest.TestCase):
    def test_applies_known_keys_and_ignores_the_rest(self):
        chain = fresh()
        applied = param_access.apply_settings(chain, "amp", {
            "enabled": False, "gain": 0.3, "model_id": 7, "model_name": "5150 III",
        })
        self.assertEqual(applied, ["enabled", "gain"])
        self.assertFalse(chain.amp.enabled)
        self.assertEqual(chain.amp.gain, 0.3)

    def test_none_means_the_source_does_not_carry_the_value(self):
        chain = fresh()
        chain.cab.set_tube_and_mic(tube="EL34", mic="SM57", center=50.0, distance=20.0)
        param_access.apply_settings(chain, "cab", {"tube": None, "mic": "MD421"})
        self.assertEqual(chain.cab.tube, "EL34")
        self.assertEqual(chain.cab.mic, "MD421")

    def test_skip_withholds_a_parameter_the_caller_decides_itself(self):
        chain = fresh()
        chain.amp.model = "Plexi"
        param_access.apply_settings(chain, "amp", {"model": "Clean", "gain": 0.2}, skip=("model",))
        self.assertEqual(chain.amp.model, "Plexi")
        self.assertEqual(chain.amp.gain, 0.2)

    def test_alias_keys_are_applied_and_order_is_the_registry_order(self):
        """eq must move the model before the bands, or the reset wipes them."""
        chain = fresh()
        chain.eq.set_bands([9.0] * 6, model_id=1)
        applied = param_access.apply_settings(chain, "eq", {"model_id": 2, "data": [1, 2, 3, 4, 5]})
        self.assertEqual(applied, ["model_id", "bands"])
        self.assertEqual(chain.eq.model_id, 2)
        self.assertEqual(chain.eq.gains, [1.0, 2.0, 3.0, 4.0, 5.0])


class RegistryCoverageTests(unittest.TestCase):
    def test_every_settable_parameter_can_be_written(self):
        """No parameter may be declared and then be unreachable for a writer."""
        for mod in params.MODULES:
            for p in mod.params:
                if p.read_only or p.owner == "server" or p.index_template or mod.name == "nam":
                    continue
                with self.subTest(module=mod.name, param=p.key):
                    chain = fresh()
                    value = p.default if not p.setter else None
                    if value is not None:
                        param_access.set(chain, mod.name, p.key, value)
                    else:
                        param_access.resolve(mod.name, p.key)


if __name__ == "__main__":
    unittest.main()
