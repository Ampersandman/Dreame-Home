"""Consolidated L9 state keeps freshness, enum identities and unknowns intact."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from dreamehome.laundry_programs import DRYER, WASHER, program_option_pairs
from dreamehome.laundry_summary import laundry_appliance_summary
from test_entity_lifecycle import entity_scope


def observations(model=WASHER, **changes):
    values = {"2.1": 3, "2.2": 0, "2.3": 8,
              "2.4": 1 if model == WASHER else 3,
              "2.12" if model == WASHER else "2.9": 60,
              "2.13" if model == WASHER else "2.11": 40,
              "3.4": 1}
    values.update(changes)
    return {key: {"value": value, "last_code": 0, "last_reply_null": False,
                  "last_source": "mqtt", "last_item": {"value": value}}
            for key, value in values.items()}


class LaundrySummaryTests(unittest.TestCase):
    def test_exact_appliances_running_snapshot_and_english_program_identity(self):
        for model, kind, phase in ((WASHER, "washer", "Washing"), (DRYER, "dryer", "Drying")):
            summary = laundry_appliance_summary(model, observations(model))
            self.assertEqual(summary["appliance_type"], kind)
            self.assertEqual((summary["status"], summary["status_code"]), ("Running", 3))
            self.assertEqual((summary["is_running"], summary["is_paused"], summary["is_powered_on"]),
                             (True, False, True))
            self.assertEqual((summary["program"], summary["program_code"]), ("Underwear", 8))
            self.assertEqual(summary["phase"], phase)
            self.assertEqual(summary["error_code"], 0)
            self.assertEqual(summary["error"], "No fault")
            self.assertFalse(summary["has_error"])
            self.assertEqual((summary["program_duration"], summary["remaining_time"]), (60, 40))
            self.assertEqual((summary["progress"], summary["elapsed_time"]), (33.3, 20))
            self.assertEqual(summary["settings"], {"child_lock": True})
            self.assertEqual(summary["program_options"],
                             [label for label, _ in program_option_pairs(model, include_additional=False)])
        dryer = laundry_appliance_summary(DRYER, observations(DRYER, **{"2.3": 7}))
        self.assertEqual((dryer["program"], dryer["program_code"]), ("Baby Care", 7))
        self.assertEqual(len(dryer["program_options"]), 25)
        self.assertEqual(len(laundry_appliance_summary(WASHER, observations())["program_options"]), 15)

    def test_all_exact_status_flags_and_pause_metrics(self):
        for model in (WASHER, DRYER):
            for status in (0, 1, 2, 3):
                summary = laundry_appliance_summary(model, observations(model, **{"2.1": status}))
                self.assertEqual(summary["is_running"], status == 3)
                self.assertEqual(summary["is_paused"], status == 2)
                self.assertEqual(summary["is_powered_on"], status != 0)
                self.assertEqual(summary["progress"], 33.3 if status in (2, 3) else None)
                self.assertEqual(summary["elapsed_time"], 20 if status in (2, 3) else None)

    def test_unknown_models_and_missing_data_never_fabricate_off_or_no_fault(self):
        for model in ("dreame.washer.l9", "dreame.dryer.l9nacn2", "dreame.vacuum.r5023a", None, [], {}):
            self.assertEqual(laundry_appliance_summary(model, observations()), {})
        for model in (WASHER, DRYER):
            for rows in ({}, None, []):
                summary = laundry_appliance_summary(model, rows)
                for key in ("status", "status_code", "is_running", "is_paused", "is_powered_on",
                            "program", "program_code", "phase", "phase_code", "error", "error_code",
                            "has_error", "program_duration", "remaining_time", "progress", "elapsed_time"):
                    self.assertIsNone(summary[key], key)
                self.assertEqual(summary["settings"], {})

    def test_failed_null_malformed_reply_types_and_latest_item_cannot_publish_state(self):
        invalid = (None, [], "raw", {"last_reply_null": True}, {"has_value": False},
                   {"last_code": -1}, {"last_code": False}, {"last_code": True},
                   {"last_source": "cached"}, {"last_source": "listing"},
                   {"last_item": None}, {"last_item": {"value": None}},
                   {"last_item": {"value": "3"}}, {"last_item": {"value": 2}},
                   {"value": True}, {"value": "3"}, {"value": 3.0},
                   {"value": {}}, {"value": [3]}, {"value": None})
        for model in (WASHER, DRYER):
            for changes in invalid:
                rows = observations(model)
                rows["2.1"] = (rows["2.1"] | changes) if isinstance(changes, dict) else changes
                summary = laundry_appliance_summary(model, rows)
                with self.subTest(model=model, changes=changes):
                    self.assertIsNone(summary["status"])
                    self.assertIsNone(summary["status_code"])
                    self.assertIsNone(summary["is_running"])
                    self.assertIsNone(summary["progress"])
            for key in ("2.2", "2.3", "2.4", "3.4"):
                rows = observations(model)
                rows[key]["last_code"] = -4001
                summary = laundry_appliance_summary(model, rows)
                if key == "3.4":
                    self.assertNotIn("child_lock", summary["settings"])
                else:
                    output = {"2.2": "error_code", "2.3": "program_code", "2.4": "phase_code"}[key]
                    self.assertIsNone(summary[output])

    def test_unknown_integer_enums_do_not_claim_fault_or_known_state(self):
        for model in (WASHER, DRYER):
            rows = observations(model, **{"2.1": 999, "2.2": 999, "2.3": 999, "2.4": 999, "3.4": 999})
            summary = laundry_appliance_summary(model, rows)
            for key in ("status_code", "program_code", "phase_code", "error_code", "has_error", "is_powered_on"):
                self.assertIsNone(summary[key])
            self.assertEqual(summary["settings"], {})
            self.assertIsNone(summary["progress"])
            self.assertIsNone(summary["elapsed_time"])

    def test_only_known_faults_claim_has_error_and_no_door_binary_is_invented(self):
        for model, code, label in ((WASHER, 2, "Water Inlet Error"),
                                    (DRYER, 2, "Door Open / Lock Error")):
            summary = laundry_appliance_summary(model, observations(model, **{"2.2": code, "3.13": 1}))
            self.assertEqual((summary["error_code"], summary["error"], summary["has_error"]), (code, label, True))
            self.assertNotIn("door", summary)
            self.assertNotIn("door_open", summary["settings"])
        unnamed = laundry_appliance_summary(WASHER, observations(**{"2.2": 12}))
        self.assertEqual(unnamed["error_code"], 12)
        self.assertTrue(unnamed["has_error"])
        self.assertIsNone(unnamed["error"])

    def test_duration_guards_and_ai_terminal_rules_match_existing_metrics(self):
        for model in (WASHER, DRYER):
            total_key, remaining_key = ("2.12", "2.13") if model == WASHER else ("2.9", "2.11")
            for invalid in (True, "60", 60.0, -1, None, float("inf")):
                summary = laundry_appliance_summary(model, observations(model, **{total_key: invalid}))
                self.assertIsNone(summary["program_duration"])
                self.assertIsNone(summary["elapsed_time"])
                summary = laundry_appliance_summary(model, observations(model, **{remaining_key: invalid}))
                self.assertIsNone(summary["remaining_time"])
                self.assertIsNone(summary["elapsed_time"])
            summary = laundry_appliance_summary(model, observations(model, **{remaining_key: 61}))
            self.assertEqual(summary["remaining_time"], 61)  # Independent successful read; inconsistent ratio unknown.
            self.assertIsNone(summary["progress"])
        ai = laundry_appliance_summary(WASHER, observations(**{"2.3": 0, "2.13": 0}))
        self.assertIsNone(ai["remaining_time"])
        self.assertIsNone(ai["progress"])
        terminal = laundry_appliance_summary(WASHER, observations(**{"2.3": 0, "2.4": 6, "2.13": 0}))
        self.assertEqual(terminal["remaining_time"], 0)
        self.assertEqual(terminal["progress"], 100)
        self.assertEqual(terminal["elapsed_time"], 60)
        no_duration = observations(**{"2.3": 0, "2.4": 6, "2.13": 0})
        no_duration.pop("2.12")
        terminal_without_duration = laundry_appliance_summary(WASHER, no_duration)
        self.assertEqual(terminal_without_duration["progress"], 100)
        self.assertIsNone(terminal_without_duration["elapsed_time"])
        completed = laundry_appliance_summary(DRYER, observations(DRYER, **{"2.4": 2}))
        self.assertIsNone(completed["progress"])

    def test_settings_use_source_options_and_proved_switch_flags_without_defaults(self):
        washer = laundry_appliance_summary(WASHER, observations(**{"2.8": 2, "2.18": 3, "3.6": 0, "3.7": 1}))
        self.assertEqual(washer["settings"], {"temperature": "40℃", "spin_speed": "1000",
                                               "child_lock": True, "fresh_air_circulation": False,
                                               "dynamic_rinse": True})
        dryer = laundry_appliance_summary(DRYER, observations(DRYER, **{"2.6": 2, "2.5": 1,
                                                                        "3.8": 1, "3.12": 0,
                                                                        "3.11": 1, "4.7": 1}))
        self.assertEqual(dryer["settings"], {"dryness_level": "Cupboard Dry", "airflow": "Normal",
                                              "child_lock": True, "wrinkle_care": True,
                                              "low_temperature": False})
        for value in (True, 1.0, "1", 2, None):
            result = laundry_appliance_summary(DRYER, observations(DRYER, **{"3.4": value}))
            self.assertNotIn("child_lock", result["settings"])

    def test_existing_freshness_clock_excludes_expired_future_failed_and_cached_rows(self):
        namespace = entity_scope()
        namespace["monotonic"] = lambda: 1000
        cases = ((819, {}), (1001, {}), (900, {"last_reply_null": True}),
                 (900, {"last_code": -1}), (900, {"last_source": "cached"}),
                 (900, {"last_item": {"value": None}}))
        for timestamp, changes in cases:
            rows = observations()
            rows["2.1"].update(changes)
            item = SimpleNamespace(store=SimpleNamespace(properties=rows),
                                   timestamps={key: timestamp for key in rows})
            result = laundry_appliance_summary(WASHER, namespace["fresh_observations"](item))
            self.assertIsNone(result["is_running"])
            if timestamp != 900:
                self.assertIsNone(result["has_error"])
                self.assertEqual(result["settings"], {})
        rows = observations()
        item = SimpleNamespace(store=SimpleNamespace(properties=rows), timestamps={key: 900 for key in rows})
        result = laundry_appliance_summary(WASHER, namespace["fresh_observations"](item))
        self.assertTrue(result["is_running"])

    def test_program_summary_matches_select_options_including_duplicate_groups(self):
        for model in (WASHER, DRYER):
            for label, code in program_option_pairs(model):
                result = laundry_appliance_summary(model, observations(model, **{"2.3": code}))
                self.assertEqual((result["program"], result["program_code"]), (label, code))
        dryer = laundry_appliance_summary(DRYER, observations(DRYER, **{"2.3": 17}))
        self.assertEqual(dryer["program"], "Care: Wool")

    def test_snapshot_is_serializable_bounded_independent_and_contains_no_identifiers(self):
        rows = observations()
        rows["99.1"] = {"value": {"access_token": "not-for-the-ui", "did": "private-device"}, "last_code": 0}
        rows["cached:private"] = {"value": "private-token", "last_code": 0}
        before = deepcopy(rows)
        result = laundry_appliance_summary(WASHER, rows)
        encoded = json.dumps(result, allow_nan=False)
        self.assertLess(len(encoded), 2200)
        for private in ("not-for-the-ui", "private-device", "private-token", "source_label", "provenance"):
            self.assertNotIn(private, encoded)
        self.assertEqual(rows, before)
        result["settings"]["child_lock"] = False
        result["program_options"].clear()
        again = laundry_appliance_summary(WASHER, rows)
        self.assertTrue(again["settings"]["child_lock"])
        self.assertEqual(len(again["program_options"]), 15)


if __name__ == "__main__":
    unittest.main()
