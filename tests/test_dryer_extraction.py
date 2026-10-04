"""Static plugin extraction must reject code and keep exact-model facts."""

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("extract_l9_dryer", ROOT / "tools/extract_l9_dryer.py")
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


class StaticLiteralTests(unittest.TestCase):
    def test_only_literals_and_explicit_translation_references_are_accepted(self):
        data = extractor.parse_literal("[{key:1,value:_string.default.Run,enabled:true,extra:null}]", {"Run": "Running"})
        self.assertEqual(data, [{"key": 1, "value": {"translation_key": "Run", "label": "Running"},
                                 "enabled": True, "extra": None}])
        for code in ("{key:foo()}", "{key:global.secret}", "{key:1+2}", "[__import__('os')]"):
            with self.assertRaises((ValueError, SyntaxError)):
                extractor.parse_literal(code, {})

    def test_string_content_is_not_rewritten_as_javascript_identifiers(self):
        self.assertEqual(extractor.parse_literal("{key:'true',value:'null',falsehood:false}", {}),
                         {"key": "true", "value": "null", "falsehood": False})

    def test_bracket_scanner_ignores_quoted_delimiters(self):
        source = 'var Choices = [{value:"[not a bracket]",nested:{key:2}}];'
        segment, position = extractor.literal_segment(source, "Choices")
        self.assertEqual(source[position:position + len(segment)], segment)
        self.assertEqual(extractor.parse_literal(segment, {})[0]["nested"], {"key": 2})


class CatalogBoundaryTests(unittest.TestCase):
    def test_exact_dryer_coordinate_evidence_and_no_report_action_read(self):
        catalog = json.loads((ROOT / "src/dreamehome/data/l9_dryer.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["model"], "dreame.dryer.l9nacn")
        self.assertEqual(catalog["source"]["plugin_version"], 130)
        self.assertEqual(len(catalog["read_candidates"]), 17)
        self.assertTrue(all(len(pair) == 2 for pair in catalog["read_candidates"]))
        self.assertEqual(catalog["direct_read_pairs"], [[3, 14]])
        report = next(row for row in catalog["action_definitions"] if row["name"] == "reportAll")
        self.assertIn("action", report["observed_helpers"])
        self.assertEqual(report["literal_parameters"], [2, 4, 1])
        # Property2.4 is reported stage; action2.4 is the report request. The
        # action's extra argument must not become a property value/write plan.
        stage = next(row for row in catalog["properties"] if row["siid"] == 2 and row["piid"] == 4)
        self.assertEqual(stage["name"], "washStatus")
        self.assertNotIn("write", stage["access"])

    def test_control_only_coordinates_have_labels_but_no_guessed_read_seed(self):
        catalog = json.loads((ROOT / "src/dreamehome/data/l9_dryer.json").read_text(encoding="utf-8"))
        by_pair = {(row["siid"], row["piid"]): row for row in catalog["properties"]}
        self.assertEqual(len(by_pair), 22)
        for pair in ((3, 3), (3, 5), (3, 10), (3, 12), (3, 13)):
            self.assertIn("write", by_pair[pair]["access"])
            self.assertFalse(by_pair[pair]["read_candidate"])
            self.assertNotIn(list(pair), catalog["read_candidates"])
        self.assertEqual(by_pair[(3, 13)]["translation_key"], "NightMode")
        self.assertNotIn((4, 7), by_pair)  # No source meaning invented for future MQTT fields.
        self.assertEqual(by_pair[(2, 10)]["value_list"][1]["label"], "+5")
        self.assertIsNone(by_pair[(2, 10)]["unit"])  # Code1 is not one minute.

    def test_program_enum_requires_explicit_export_table_binding(self):
        catalog = json.loads((ROOT / "src/dreamehome/data/l9_dryer.json").read_text(encoding="utf-8"))
        selection = catalog["program_table_selection"]
        self.assertEqual(selection["is_export_sales_literal"], 1)
        self.assertEqual(selection["selected_table"], "ProgramMode_W")
        program = next(row for row in catalog["properties"] if row["siid"] == 2 and row["piid"] == 3)
        self.assertEqual(len(program["value_list"]), 31)
        self.assertEqual(program["enum_source"], selection)

    def test_firmware_cloud_flag_is_separate_from_numeric_properties(self):
        catalog = json.loads((ROOT / "src/dreamehome/data/l9_dryer.json").read_text(encoding="utf-8"))
        flag = catalog["cloud_property_keys"][0]
        self.assertEqual(flag["key"], "prop.s_auto_upgrade")
        self.assertEqual(flag["access"], ["read", "write"])
        self.assertEqual([entry["value"] for entry in flag["value_list"]], ["0", "1"])
        self.assertFalse(flag["live_verified"])
        self.assertNotIn(flag["key"], [row["key"] for row in catalog["properties"]])


if __name__ == "__main__":
    unittest.main()
