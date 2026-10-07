"""Source availability and fail-closed context regression tests."""

import json
from pathlib import Path
import unittest

from dreamehome import vacuum_telemetry as telemetry


def observed(value, **metadata):
    return {"value": value, "has_value": True, "last_code": 0,
            "last_reply_null": False, **metadata}


def context(state=13, status=6, task=0, **properties):
    rows = {"2.1": observed(state), "4.1": observed(status),
            "4.7": observed(task), "4.17": observed(0),
            "4.2": observed(12), "4.3": observed(8),
            "4.63": observed(40), "4.64": observed(30)}
    rows.update({key: observed(value) for key, value in properties.items()})
    return rows


class VacuumTelemetryTests(unittest.TestCase):
    def available(self, coordinate, rows):
        return telemetry.vacuum_telemetry_available(telemetry.VACUUM_MODEL, coordinate, rows)

    def test_constants_match_pinned_source_enums(self):
        reference = json.loads((Path(__file__).parent / "fixtures/vacuum_reference.json")
                               .read_text(encoding="utf-8"))
        self.assertEqual(reference["attribution"]["revision"], telemetry.SOURCE_REVISION)
        enums = reference["enums"]
        for name, actual, extra in (
            ("DreameVacuumState", telemetry._STATE_CODES, {0}),
            ("DreameVacuumStatus", telemetry._STATUS_CODES, set()),
            ("DreameVacuumTaskStatus", telemetry._TASK_CODES, set()),
            ("DreameVacuumSelfWashBaseStatus", telemetry._SELF_WASH_CODES, set()),
        ):
            with self.subTest(enum=name):
                expected = set(enums[name]["members"].values()) - {-1}
                self.assertEqual(actual, expected | extra)
                self.assertIn(telemetry.SOURCE_REVISION, enums[name]["source"]["url"])

    def test_idle_preserves_history_but_does_not_manufacture_progress(self):
        for state, status in ((13, 6), (2, 0), (6, 14), (0, 6)):
            rows = context(state, status)
            for coordinate in ("4.2", "4.3"):
                with self.subTest(state=state, coordinate=coordinate):
                    self.assertTrue(self.available(coordinate, rows))
            self.assertFalse(self.available("4.63", rows))
            self.assertFalse(self.available("4.64", rows))

    def test_cleaning_and_paused_tasks_remain_available(self):
        for state, status, task in ((1, 2, 1), (3, 1, 6), (3, 1, 7),
                                    (6, 6, 12), (3, 1, 15)):
            for coordinate in ("4.2", "4.3", "4.63"):
                with self.subTest(state=state, task=task, coordinate=coordinate):
                    self.assertTrue(self.available(coordinate, context(state, status, task)))
        # Task/status are alternative positive branches in the source getter.
        rows = context(1, 2, 0)
        del rows["4.17"]
        self.assertTrue(self.available("4.63", rows))

    def test_low_battery_cleaning_pause_uses_actual_source_flag(self):
        rows = context(6, 6, 0, **{"4.17": 1})
        self.assertTrue(self.available("4.63", rows))
        for invalid in (None, True, "1", -1):
            with self.subTest(value=invalid):
                rows["4.17"] = observed(invalid)
                self.assertFalse(self.available("4.63", rows))
        rows["4.17"] = observed(1, last_code=-1)
        self.assertFalse(self.available("4.63", rows))
        del rows["4.17"]
        self.assertFalse(self.available("4.63", rows))
        self.assertTrue(self.available("4.2", rows))

    def test_mapping_and_cruising_are_excluded(self):
        cases = ((11, 21, 5), (3, 1, 5), (3, 1, 10), (2, 0, 10),
                 (1, 21, 1), (98, 22, 20), (99, 1, 21),
                 (98, 23, 22), (99, 1, 23), (1, 22, 1))
        for state, status, task in cases:
            for coordinate in ("4.2", "4.3", "4.63"):
                with self.subTest(task=task, status=status, coordinate=coordinate):
                    self.assertFalse(self.available(coordinate, context(state, status, task)))

    def test_fast_mapping_paused_condition_matches_source(self):
        # MAP_CLEANING_PAUSED alone is not fast_mapping_paused: source also
        # requires paused/error/idle state, unlike unconditional FAST_MAPPING.
        self.assertTrue(self.available("4.2", context(6, 6, 10)))
        self.assertTrue(self.available("4.63", context(6, 6, 10)))

    def test_drying_requires_positive_typed_self_wash_status(self):
        rows = {"4.25": observed(2)}
        self.assertTrue(self.available("4.64", rows))
        for invalid in (None, True, False, "2", 2.0, -1, 0, 1, 3, 8, 999):
            with self.subTest(value=invalid):
                self.assertFalse(self.available("4.64", {"4.25": observed(invalid)}))
        self.assertFalse(self.available("4.64", {"4.25": observed(2, last_code=-1)}))
        self.assertFalse(self.available("4.64", {}))

    def test_required_context_failures_do_not_use_old_retained_values(self):
        for coordinate in ("2.1", "4.1", "4.7"):
            for invalid in (None, True, False, "1", 1.0, -1, 999, {}, []):
                rows = context(1, 2, 1)
                rows[coordinate] = observed(invalid)
                for target in ("4.2", "4.3", "4.63"):
                    with self.subTest(coordinate=coordinate, value=invalid, target=target):
                        self.assertFalse(self.available(target, rows))
            for metadata in ({"last_code": -1}, {"last_code": True},
                             {"last_reply_null": True}, {"has_value": False}):
                rows = context(1, 2, 1)
                rows[coordinate].update(metadata)
                self.assertFalse(self.available("4.2", rows))
                self.assertFalse(self.available("4.63", rows))
            rows = context(1, 2, 1)
            del rows[coordinate]
            self.assertFalse(self.available("4.3", rows))

    def test_exact_model_coordinate_and_observation_shape_gates(self):
        rows = context(1, 2, 1)
        self.assertTrue(self.available("4.63", {"properties": rows}))
        for model in ("dreame.vacuum.other", "dreame.washer.l9nacn", ""):
            self.assertFalse(telemetry.vacuum_telemetry_available(model, "4.2", rows))
        for coordinate in ("4.4", "4.40", "4.66", "4.2/value", ""):
            self.assertFalse(self.available(coordinate, rows))
        for invalid in (None, [], "", {"properties": []}):
            self.assertFalse(self.available("4.2", invalid))

    def test_telemetry_value_validation_belongs_to_caller(self):
        rows = context(1, 2, 1)
        rows["4.63"] = observed(1000)
        self.assertTrue(self.available("4.63", rows))
        self.assertEqual(rows["4.63"]["value"], 1000)
        # This helper only checks context; the sensor's numeric/range validator
        # must reject invalid percentages without losing raw observations.


if __name__ == "__main__":
    unittest.main()
