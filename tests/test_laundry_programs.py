"""Exact app-main program profiles and English presentation of wire identities."""

import unittest

from dreamehome.laundry_controls import ControlValidationError, control_options, prepare_control_write
from dreamehome.laundry_programs import (
    DRYER, WASHER, program_catalog, program_definition, program_language, program_option_pairs,
)
from dreamehome.presentation import control_presentation, cycle_presentation, property_presentation
from test_laundry_controls import observations


class LaundryProgramTests(unittest.TestCase):
    def test_main_profiles_follow_source_keys_not_list_positions(self):
        self.assertEqual([row["value"] for row in program_catalog(WASHER)],
                         [0, 22, 1, 2, 3, 4, 5, 6, 21, 8, 9, 11, 12, 13, 14])
        dryer = program_catalog(DRYER)
        self.assertEqual([row["value"] for row in dryer if row["group"] == "dry"], list(range(16)))
        self.assertEqual([row["value"] for row in dryer if row["group"] == "care"],
                         [18, 19, 16, 17, 20, 21, 22, 23, 24])
        self.assertEqual(len(dryer), 25)
        self.assertEqual(len(program_catalog(WASHER, include_additional=True)), 22)
        self.assertEqual(len(program_catalog(DRYER, include_additional=True)), 31)
        self.assertEqual(program_catalog("dreame.dryer.l9"), [])

    def test_english_app_names_preserve_original_source_identity(self):
        self.assertEqual(program_definition(DRYER, 7)["labels"], {"en": "Baby Care"})
        self.assertEqual(program_definition(DRYER, 7)["source_label"], "Towels")
        for model in (WASHER, DRYER):
            self.assertEqual(program_definition(model, 8)["label"], "Underwear")
            self.assertEqual(program_definition(model, 8)["source_label"], "Delicates")
        self.assertEqual(program_definition(DRYER, 9)["labels"]["en"], "Synthetics")
        self.assertEqual(program_definition(DRYER, 27)["labels"]["en"], "Synthetic")
        self.assertEqual(program_definition(WASHER, 11)["label"], "Anti-Allergen")
        self.assertEqual(program_definition(WASHER, 11)["source_label"], "Allergy Care")
        self.assertEqual(program_definition(WASHER, 12)["labels"], {"en": "Spin Only"})
        self.assertEqual(program_definition(WASHER, 22)["label"], "ECO 40-60")
        self.assertIsNone(program_definition(WASHER, True))
        self.assertIsNone(program_definition(WASHER, "22"))
        self.assertIsNone(program_definition(WASHER, 999))

    def test_english_options_are_locale_independent_bijective_and_stable(self):
        for model in (WASHER, DRYER):
            english = program_option_pairs(model, "en")
            for language in (None, "en", "de-DE", "de_AT", "fr"):
                pairs = program_option_pairs(model, language)
                self.assertEqual(pairs, english)
                self.assertEqual(len({label for label, _ in pairs}), len(pairs))
                self.assertEqual(len({code for _, code in pairs}), len(pairs))
                all_labels = dict((code, label) for label, code in pairs)
                standard_labels = dict((code, label) for label, code in program_option_pairs(model, language, include_additional=False))
                self.assertTrue(all(all_labels[code] == label for code, label in standard_labels.items()))
        german_ha = dict((code, label) for label, code in program_option_pairs(DRYER, "de"))
        self.assertEqual(german_ha[3], "Dry: Wool")
        self.assertEqual(german_ha[17], "Care: Wool")
        self.assertEqual(german_ha[9], "Synthetics")
        self.assertEqual(german_ha[27], "Cloud programs: Synthetic")
        self.assertEqual(program_language("de_AT"), "en")
        self.assertEqual(program_language("en-GB"), "en")
        self.assertEqual(program_language(None), "en")

    def test_source_reference_minutes_are_not_live_estimates_or_mutable_state(self):
        self.assertIsNone(program_definition(WASHER, 0)["reference_duration_minutes"])
        self.assertEqual(program_definition(WASHER, 22)["reference_duration_minutes"], 234)
        self.assertEqual(program_definition(DRYER, 5)["reference_duration_minutes"], 112)
        self.assertEqual(program_definition(DRYER, 0)["reference_duration_kind"], "source-default")
        edited = program_catalog(WASHER)
        edited[0]["labels"]["en"] = "Modified"
        self.assertEqual(program_catalog(WASHER)[0]["labels"], {"en": "AI Wash"})
        self.assertEqual(program_catalog(WASHER)[0]["group_labels"], {"en": "Wash"})

    def test_only_main_profile_choices_can_be_new_program_writes(self):
        for model, omitted in ((WASHER, (7, 10, 15, 16, 17, 18, 19)), (DRYER, tuple(range(25, 31)))):
            rows = observations(model)
            allowed = {row["value"] for row in control_options(model, "program", rows)}
            self.assertEqual(allowed, {row["value"] for row in program_catalog(model)})
            for raw in omitted:
                self.assertIsNotNone(program_definition(model, raw))
                with self.assertRaises(ControlValidationError):
                    prepare_control_write(model, "program", raw, rows)
            # A historical additional current program stays recognizable and
            # may be replaced with a standard choice; no raw address is guessed.
            prior = observations(model, program=omitted[0])
            self.assertEqual(prepare_control_write(model, "program", 1, prior)["properties"],
                             [{"siid": 2, "piid": 3, "value": 1}])

    def test_cycle_settings_controls_and_operational_readbacks_sensors(self):
        for model in (WASHER, DRYER):
            self.assertIsNone(control_presentation(model, "child_lock")["entity_category"])
            for key in ("program", "start", "pause", "stop", "extra_time", "speed_mode"):
                self.assertIsNone(control_presentation(model, key)["entity_category"])
            for key in ("2.1", "2.3", "2.4", "3.14"):
                self.assertTrue(property_presentation(model, key)["enabled_default"])
            for key in ("2.2", "99.1", "cached:unknown"):
                self.assertFalse(property_presentation(model, key)["enabled_default"])
                self.assertEqual(property_presentation(model, key)["entity_category"], "diagnostic")
            self.assertFalse(property_presentation(model, "2.1", "/arbitrary")["enabled_default"])
        self.assertIsNone(control_presentation(WASHER, "night_mode")["entity_category"])

    def test_all_entity_labels_remain_english_for_other_ha_languages(self):
        for language in ("de-DE", "de_AT", "fr", None):
            self.assertEqual(control_presentation(WASHER, "program", language)["label"], "Selected program")
            self.assertEqual(control_presentation(DRYER, "child_lock", language)["label"], "Child lock")
            self.assertEqual(property_presentation(WASHER, "2.4", language=language)["label"], "Wash phase")
            self.assertEqual(property_presentation(DRYER, "2.11", language=language)["label"], "Remaining time")
            self.assertEqual(cycle_presentation("progress", language)["label"], "Program progress")


if __name__ == "__main__":
    unittest.main()
