"""
Integration tests for MOOER GE150 API endpoints directly via handler functions.
"""

import unittest
import json
from server import (
    get_mooer_models,
    get_mooer_presets,
    load_mooer_preset,
    update_parameter,
    export_current_to_mooer,
    ParamUpdate,
    engine,
)

class TestMooerApi(unittest.TestCase):
    def test_get_models(self):
        resp = get_mooer_models()
        self.assertIn("catalog", resp)
        catalog = resp["catalog"]
        self.assertIn("AMP", catalog)
        self.assertIn("CAB", catalog)
        self.assertEqual(len(catalog["AMP"]), 65)
        self.assertEqual(len(catalog["CAB"]), 36)

    def test_get_presets(self):
        resp = get_mooer_presets()
        self.assertIn("presets", resp)
        self.assertGreaterEqual(len(resp["presets"]), 5)

    def test_load_preset(self):
        resp = load_mooer_preset({"name": "01A 65 US DX"})
        self.assertTrue(resp["success"])
        self.assertEqual(resp["preset"]["name"], "01A 65 US DX")
        state = resp["state"]
        self.assertEqual(state["chain"]["cab"]["tube"], "6L6")
        self.assertEqual(state["chain"]["cab"]["mic"], "SM57")

    def test_export_preset(self):
        resp = export_current_to_mooer(name="StageLead")
        data = resp.body.decode("utf-8")
        doc = json.loads(data)
        self.assertEqual(doc["device"], "MOOER GE150")
        self.assertEqual(doc["schema"], "V1.3.0")
        self.assertIn("effectModule", doc)

    def test_cab_parameters(self):
        # Update tube to EL34
        req1 = ParamUpdate(section="cab", param="tube", value="EL34")
        resp1 = update_parameter(req1)
        self.assertEqual(resp1["state"]["chain"]["cab"]["tube"], "EL34")

        # Update mic to MD421
        req2 = ParamUpdate(section="cab", param="mic", value="MD421")
        resp2 = update_parameter(req2)
        self.assertEqual(resp2["state"]["chain"]["cab"]["mic"], "MD421")

        # Update center to 75
        req3 = ParamUpdate(section="cab", param="center", value=75.0)
        resp3 = update_parameter(req3)
        self.assertEqual(resp3["state"]["chain"]["cab"]["center"], 75.0)

if __name__ == "__main__":
    unittest.main()
