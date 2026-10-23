"""
Tests for MOOER GE150 Models, Presets, and DSP components.
"""

import unittest
import numpy as np
import json
from engine.mooer_models import (
    AMP_MODELS,
    CAB_MODELS,
    DS_MODELS,
    EQ_MODELS,
    MOD_MODELS,
    DELAY_MODELS,
    REVERB_MODELS,
    MODULE_CATALOG,
)
from engine.mooer_preset import (
    parse_mo_preset,
    export_mo_preset,
    mo_to_workstation_preset,
    FACTORY_GE150_PRESETS,
)

class TestMooerModels(unittest.TestCase):
    def test_catalog_completeness(self):
        # 55 factory amps + 10 user amps = 65
        self.assertEqual(len(AMP_MODELS), 65)
        # 26 factory cabs + 10 user cabs = 36
        self.assertEqual(len(CAB_MODELS), 36)
        # 20 DS/OD models
        self.assertEqual(len(DS_MODELS), 20)
        # 4 EQ models
        self.assertEqual(len(EQ_MODELS), 4)
        # 19 MOD models
        self.assertEqual(len(MOD_MODELS), 19)
        # 9 DELAY models
        self.assertEqual(len(DELAY_MODELS), 9)
        # 7 REVERB models
        self.assertEqual(len(REVERB_MODELS), 7)

    def test_factory_presets_parsing(self):
        for preset_doc in FACTORY_GE150_PRESETS:
            # Test serialization to JSON
            raw_json = json.dumps(preset_doc)
            parsed = parse_mo_preset(raw_json)
            self.assertEqual(parsed["schema"], "V1.3.0")
            self.assertIn("effectModule", parsed)
            self.assertIn("AMP", parsed["effectModule"])

            # Test conversion to workstation format
            ws_preset = mo_to_workstation_preset(parsed)
            self.assertTrue(ws_preset["id"].startswith("mooer_"))
            self.assertIn("settings", ws_preset)
            settings = ws_preset["settings"]
            self.assertIn("amp", settings)
            self.assertIn("cab", settings)
            self.assertIn("gate", settings)

    def test_export_mo_preset(self):
        # Create dummy workstation state
        chain_state = {
            "amp": {"enabled": True, "gain": 0.8, "bass": 0.5, "mid": 0.6, "treble": 0.7, "presence": 0.5, "master": 0.75, "model_id": 7},
            "cab": {"enabled": True, "tube": "EL34", "mic": "SM57", "center": 35, "distance": 15, "model_id": 6},
            "screamer": {"enabled": True, "drive": 0.3, "tone": 0.6, "level": 0.8, "model_id": 2},
            "gate": {"enabled": True, "threshold": -50.0},
            "delay": {"enabled": True, "time": 0.4, "feedback": 0.35, "mix": 0.25},
            "reverb": {"enabled": True, "decay": 0.5, "mix": 0.2, "tone": 0.6},
        }

        mo_json = export_mo_preset("MY LEAD", chain_state)
        parsed = json.loads(mo_json)
        self.assertEqual(parsed["preset_name"], "MY LEAD")
        self.assertEqual(parsed["schema"], "V1.3.0")
        self.assertEqual(parsed["effectModule"]["AMP"]["TYPE"], 7)
        self.assertEqual(parsed["effectModule"]["AMP"]["SWITCH"], 1)
        self.assertEqual(parsed["effectModule"]["CAB"]["SWITCH"], 1)
        # Check tube index for EL34 is 1
        self.assertEqual(parsed["effectModule"]["CAB"]["Data"][0], 1)

if __name__ == "__main__":
    unittest.main()
