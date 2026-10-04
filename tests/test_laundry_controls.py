"""Exact source control encoders and dependency boundaries; no device commands."""

from copy import deepcopy
import unittest

from dreamehome.laundry_controls import (
    ControlValidationError, DRYER, WASHER, control_available, control_definitions,
    control_options, omitted_controls, prepare_control_write,
)


def observations(model=WASHER, *, program=0, status=1, phase=0, **values):
    rows = {"2.1": status, "2.2": 0, "2.3": program, "2.4": phase, "3.4": 0, "3.14": 1}
    for definition in control_definitions(model):
        if definition["kind"] != "button":
            rows.setdefault(definition["coordinate"], definition["options"][0]["value"])
    rows.update({"2.5": 0, "2.8": 1, "2.14": 0, "2.16": 2, "3.7": 0, "3.8": 0,
                 "3.9": 0} if model == WASHER else {"3.10": 0, "3.12": 0})
    rows.update(values)
    return {key: {"value": raw, "last_code": 0, "last_reply_null": False}
            for key, raw in rows.items()}


class LaundryControlTests(unittest.TestCase):
    def test_exact_model_gate_and_no_raw_or_ambiguous_writes(self):
        for model in ("dreame.washer.l9", "dreame.dryer.l9nacn2", "dreame.vacuum.r5023a"):
            self.assertEqual(control_definitions(model), [])
            self.assertFalse(control_available(model, "start", observations()))
            with self.assertRaises(ControlValidationError):
                prepare_control_write(model, "start", None, observations())
        for key in ("3.11", "3.13", "4.7", "night_mode", "delay_time", "report_all", "sanitize"):
            self.assertFalse(control_available(DRYER, key, observations(DRYER)))
            with self.assertRaises(ControlValidationError):
                prepare_control_write(DRYER, key, True, observations(DRYER))
        self.assertIn("night_mode", omitted_controls(DRYER))
        self.assertIn("stain_type", omitted_controls(WASHER))
        self.assertFalse(any(row["kind"] == "number" for model in (WASHER, DRYER)
                             for row in control_definitions(model)))

    def test_descriptors_are_source_bound_and_not_mutable_global_state(self):
        definitions = control_definitions(WASHER)
        self.assertEqual(len(definitions), 16)
        self.assertEqual(len(control_definitions(DRYER)), 12)
        for model in (WASHER, DRYER):
            for row in control_definitions(model):
                self.assertFalse(row["live_write_verified"])
                self.assertEqual(row["platform"], row["kind"])
                self.assertTrue(row["provenance"]["source"]["bundle_sha256"])
                if row["kind"] != "button":
                    self.assertEqual(row["coordinate"], f"{row['siid']}.{row['piid']}")
        definitions[0]["options"].clear()
        self.assertTrue(control_definitions(WASHER)[0]["options"])

    def test_source_integer_encoders_are_codes_not_displayed_units(self):
        rows = observations()
        payload = prepare_control_write(WASHER, "spin_speed", 4, rows)
        self.assertEqual(payload, {"method": "set_properties", "properties": [
            {"siid": 2, "piid": 18, "value": 4}]})
        self.assertEqual(prepare_control_write(WASHER, "temperature", 2, rows)["properties"][0]["value"], 2)
        for raw in (1400, "4", 4.0, True, None, {}, [4]):
            with self.assertRaises(ControlValidationError):
                prepare_control_write(WASHER, "spin_speed", raw, rows)
        for raw in (0, 1, "1", 1.0, None):
            with self.assertRaises(ControlValidationError):
                prepare_control_write(WASHER, "child_lock", raw, rows)
        self.assertEqual(prepare_control_write(WASHER, "child_lock", True, rows)["properties"],
                         [{"siid": 3, "piid": 4, "value": 1}])
        self.assertEqual(prepare_control_write(WASHER, "child_lock", False, rows)["properties"][0]["value"], 0)

    def test_actions_match_exact_native_inputs_and_do_not_replay_settings(self):
        for model in (WASHER, DRYER):
            for key, status, aiid, raw in (("start", 1, 2, 1), ("start", 2, 2, 1),
                                          ("pause", 3, 2, 0), ("stop", 3, 1, 0)):
                with self.subTest(model=model, key=key, status=status):
                    self.assertEqual(prepare_control_write(model, key, None, observations(model, status=status)),
                                     {"method": "action", "action": {"siid": 2, "aiid": aiid,
                                      "in": [{"piid": aiid, "value": raw}]}})
            with self.assertRaises(ControlValidationError):
                prepare_control_write(model, "start", {"piid": 2, "value": 1}, observations(model))
            for values in ({"3.14": 0}, {"2.2": 1}, {"3.4": 1}):
                self.assertFalse(control_available(model, "start", observations(model, **values)))
            self.assertFalse(control_available(model, "pause", observations(model, status=2)))
            self.assertFalse(control_available(model, "start", observations(model, status=3)))

    def test_required_observations_fail_closed_for_null_failed_unknown_types(self):
        for change in ({"value": None}, {"last_code": -4001}, {"last_code": False},
                       {"last_reply_null": True}, {"value": True}, {"value": "1"},
                       {"value": 1.0}, {"value": 999}):
            rows = observations()
            rows["2.1"].update(change)
            self.assertFalse(control_available(WASHER, "start", rows))
            self.assertEqual(control_options(WASHER, "program", rows), [])
            with self.assertRaises(ControlValidationError):
                prepare_control_write(WASHER, "start", None, rows)
        rows = observations()
        del rows["2.3"]
        self.assertFalse(control_available(WASHER, "program", rows))
        rows = observations()
        rows["3.4"]["value"] = 1
        self.assertTrue(control_available(WASHER, "child_lock", rows))
        self.assertFalse(control_available(WASHER, "water_level", rows))
        self.assertFalse(control_available(WASHER, "water_level", {"2.1": 1}))

    def test_washer_program_nulls_and_excluded_codes(self):
        eco = observations(program=22)
        self.assertEqual([r["value"] for r in control_options(WASHER, "temperature", eco)], [2])
        self.assertEqual([r["value"] for r in control_options(WASHER, "spin_speed", eco)], [4])
        for key in ("extra_time", "rinse_cycles", "water_level", "detergent_dosing",
                    "softener_dosing", "dynamic_rinse", "speed_mode", "night_mode"):
            self.assertFalse(control_available(WASHER, key, eco))
        with self.assertRaises(ControlValidationError):
            prepare_control_write(WASHER, "temperature", 1, eco)
        wool = observations(program=6)
        self.assertNotIn(4, [r["value"] for r in control_options(WASHER, "temperature", wool)])

    def test_washer_interdependent_settings_do_not_silently_write_neighbors(self):
        rows = observations(program=2, **{"3.8": 1})
        self.assertNotIn(2, [r["value"] for r in control_options(WASHER, "temperature", rows)])
        self.assertFalse(control_available(WASHER, "extra_time", rows))
        self.assertFalse(control_available(WASHER, "temperature", observations(**{"2.5": 1})))
        self.assertFalse(control_available(WASHER, "spin_speed", observations(**{"3.9": 1})))
        rows = observations(**{"3.7": 1})
        self.assertNotIn(0, [r["value"] for r in control_options(WASHER, "rinse_cycles", rows)])
        rows = observations(**{"2.16": 0})
        with self.assertRaises(ControlValidationError):
            prepare_control_write(WASHER, "dynamic_rinse", True, rows)
        rows = observations(program=4, **{"2.8": 2})
        with self.assertRaises(ControlValidationError):
            prepare_control_write(WASHER, "speed_mode", True, rows)
        rows = observations(**{"2.14": 1})
        with self.assertRaises(ControlValidationError):
            prepare_control_write(WASHER, "speed_mode", True, rows)
        self.assertEqual(prepare_control_write(WASHER, "dynamic_rinse", True, observations())["properties"],
                         [{"siid": 3, "piid": 7, "value": 1}])

    def test_source_phase_constraints_and_conservative_standby_policy(self):
        self.assertFalse(control_available(WASHER, "temperature", observations(status=2, phase=1)))
        self.assertFalse(control_available(WASHER, "night_mode", observations(phase=1)))
        self.assertFalse(control_available(WASHER, "night_mode", observations(program=6)))
        self.assertTrue(control_available(WASHER, "fresh_air_circulation", observations(status=2, phase=1)))
        self.assertFalse(control_available(WASHER, "fresh_air_circulation", observations(status=3, phase=1)))
        self.assertFalse(control_available(WASHER, "fresh_air_circulation", observations(program=14)))
        self.assertTrue(control_available(DRYER, "wrinkle_care", observations(DRYER, status=2, phase=3)))
        self.assertFalse(control_available(DRYER, "wrinkle_care", observations(DRYER, status=1, phase=3)))

    def test_dryer_export_program_filters_use_key_not_reordered_array_position(self):
        quick = observations(DRYER, program=1)
        self.assertEqual(control_options(DRYER, "airflow", quick), [{"value": 2, "label": "Strong"}])
        self.assertFalse(control_available(DRYER, "speed_mode", quick))
        wool = observations(DRYER, program=3)
        self.assertFalse(control_available(DRYER, "extra_time", wool))
        # key18 Hot Air binds defaultConfig_W[18], not its array position16.
        hot = observations(DRYER, program=18)
        self.assertFalse(control_available(DRYER, "dryness_level", hot))
        self.assertTrue(control_available(DRYER, "extra_time", hot))
        self.assertEqual(control_options(DRYER, "airflow", hot), [{"value": 1, "label": "Normal"}])
        for program in (17, 19):
            rows = observations(DRYER, program=program)
            self.assertFalse(control_available(DRYER, "dryness_level", rows))
        for raw in (True, "18", 18.0, 99):
            with self.assertRaises(ControlValidationError):
                prepare_control_write(DRYER, "program", raw, observations(DRYER))
        self.assertEqual(prepare_control_write(DRYER, "program", 18, observations(DRYER))["properties"],
                         [{"siid": 2, "piid": 3, "value": 18}])

    def test_dryer_mutual_exclusion_requires_other_flag_already_off(self):
        rows = observations(DRYER, **{"3.10": 1})
        self.assertEqual([r["value"] for r in control_options(DRYER, "low_temperature", rows)], [0])
        with self.assertRaises(ControlValidationError):
            prepare_control_write(DRYER, "low_temperature", True, rows)
        rows = observations(DRYER, **{"3.12": 1})
        with self.assertRaises(ControlValidationError):
            prepare_control_write(DRYER, "speed_mode", True, rows)
        self.assertEqual(prepare_control_write(DRYER, "low_temperature", False, rows)["properties"],
                         [{"siid": 3, "piid": 12, "value": 0}])
        self.assertEqual(prepare_control_write(DRYER, "speed_mode", True, observations(DRYER))["properties"],
                         [{"siid": 3, "piid": 10, "value": 1}])

    def test_encoder_is_pure_and_payloads_do_not_contain_target_identifiers(self):
        rows = observations()
        before = deepcopy(rows)
        first = prepare_control_write(WASHER, "program", 22, rows)
        self.assertEqual(rows, before)
        self.assertNotIn("did", first["properties"][0])
        first["properties"][0]["value"] = 999
        self.assertEqual(prepare_control_write(WASHER, "program", 22, rows)["properties"][0]["value"], 22)


if __name__ == "__main__":
    unittest.main()
