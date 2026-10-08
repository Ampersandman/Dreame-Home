"""Source L9 timeline arithmetic and unknown/terminal state boundaries."""

from copy import deepcopy
import unittest

from dreamehome.laundry_progress import (
    DRYER, WASHER, laundry_cycle_metrics, progress_definitions,
)


def observations(model=WASHER, *, status=3, program=2, phase=None, total=60, remaining=40):
    pairs = {"2.1": status, "2.3": program,
             "2.4": phase if phase is not None else 1 if model == WASHER else 3,
             "2.12" if model == WASHER else "2.9": total,
             "2.13" if model == WASHER else "2.11": remaining}
    return {key: {"value": value, "last_code": 0, "last_reply_null": False}
            for key, value in pairs.items()}


class LaundryProgressTests(unittest.TestCase):
    def test_exact_models_and_independent_source_descriptors(self):
        for model in ("dreame.washer.l9", "dreame.dryer.l9nacn2", "dreame.vacuum.r5023a"):
            self.assertEqual(progress_definitions(model), [])
            self.assertEqual(laundry_cycle_metrics(model, observations()),
                             {"progress": None, "elapsed_time": None})
        for model, durations in ((WASHER, ["2.12", "2.13"]), (DRYER, ["2.9", "2.11"])):
            definitions = progress_definitions(model)
            self.assertEqual([(r["key"], r["unit"]) for r in definitions],
                             [("progress", "%"), ("elapsed_time", "min"), ("finish_time", None)])
            self.assertEqual(definitions[0]["duration_coordinates"], durations)
            self.assertTrue(definitions[0]["provenance"]["source"]["bundle_sha256"])
            definitions[0]["required_coordinates"].clear()
            self.assertTrue(progress_definitions(model)[0]["required_coordinates"])

    def test_raw_minute_ratio_and_presentation_rounding(self):
        for model in (WASHER, DRYER):
            self.assertEqual(laundry_cycle_metrics(model, observations(model)),
                             {"progress": 33.3, "elapsed_time": 20})
            self.assertEqual(laundry_cycle_metrics(model, observations(model, total=80, remaining=20)),
                             {"progress": 75.0, "elapsed_time": 60})
            self.assertEqual(laundry_cycle_metrics(model, observations(model, total=60, remaining=60)),
                             {"progress": 0.0, "elapsed_time": 0})
            self.assertEqual(laundry_cycle_metrics(model, observations(model, remaining=0)),
                             {"progress": 100.0, "elapsed_time": 60})

    def test_active_and_paused_phase_guards(self):
        for model, phases in ((WASHER, (1, 2, 3, 4, 7)), (DRYER, (1, 3))):
            for status in (2, 3):
                for phase in phases:
                    self.assertEqual(laundry_cycle_metrics(model, observations(model, status=status, phase=phase)),
                                     {"progress": 33.3, "elapsed_time": 20})
            for status in (0, 1, 4, 99):
                self.assertEqual(laundry_cycle_metrics(model, observations(model, status=status)),
                                 {"progress": None, "elapsed_time": None})
            for phase in (0, 8, 999):
                self.assertEqual(laundry_cycle_metrics(model, observations(model, phase=phase)),
                                 {"progress": None, "elapsed_time": None})
        self.assertEqual(laundry_cycle_metrics(DRYER, observations(DRYER, phase=2)),
                         {"progress": None, "elapsed_time": None})

    def test_washer_terminal_override_precedes_ai_unknown_and_invalid_duration(self):
        for status in (1, 2, 3):
            for phase in (5, 6):
                rows = observations(status=status, phase=phase, program=0, remaining=0)
                self.assertEqual(laundry_cycle_metrics(WASHER, rows),
                                 {"progress": 100, "elapsed_time": 60})
                rows.pop("2.12")
                self.assertEqual(laundry_cycle_metrics(WASHER, rows),
                                 {"progress": 100, "elapsed_time": None})
                rows["2.12"] = {"value": 0, "last_code": 0}
                self.assertEqual(laundry_cycle_metrics(WASHER, rows),
                                 {"progress": 100, "elapsed_time": None})
        self.assertEqual(laundry_cycle_metrics(WASHER, observations(status=0, phase=6)),
                         {"progress": None, "elapsed_time": None})
        rows = observations(phase=6)
        rows["2.4"]["last_reply_null"] = True
        self.assertEqual(laundry_cycle_metrics(WASHER, rows),
                         {"progress": None, "elapsed_time": None})

    def test_ai_zero_remaining_is_unknown_for_nonterminal_washer_only(self):
        for status in (2, 3):
            self.assertEqual(laundry_cycle_metrics(WASHER, observations(status=status, program=0, remaining=0)),
                             {"progress": None, "elapsed_time": None})
        self.assertEqual(laundry_cycle_metrics(WASHER, observations(program=0, remaining=30)),
                         {"progress": 50.0, "elapsed_time": 30})
        self.assertEqual(laundry_cycle_metrics(DRYER, observations(DRYER, program=0, remaining=0)),
                         {"progress": 100.0, "elapsed_time": 60})

    def test_invalid_duration_never_clamps_or_uses_defaults(self):
        for model in (WASHER, DRYER):
            for total, remaining in ((0, 0), (-1, 0), (60, -1), (60, 61),
                                     (None, 10), (60, None), (True, 0),
                                     (60, False), (60.0, 10), (60, 10.0),
                                     ("60", 10), (60, "10")):
                with self.subTest(model=model, total=total, remaining=remaining):
                    self.assertEqual(laundry_cycle_metrics(model, observations(model, total=total, remaining=remaining)),
                                     {"progress": None, "elapsed_time": None})

    def test_each_required_context_value_rejects_null_failed_and_wrong_type(self):
        for model in (WASHER, DRYER):
            for coordinate in observations(model):
                for changes in ({"value": None}, {"last_code": -4001}, {"last_code": False},
                                {"last_reply_null": True}, {"value": True}, {"value": "3"},
                                {"value": 3.0}):
                    rows = observations(model)
                    rows[coordinate].update(changes)
                    with self.subTest(model=model, coordinate=coordinate, changes=changes):
                        self.assertEqual(laundry_cycle_metrics(model, rows),
                                         {"progress": None, "elapsed_time": None})
                rows = observations(model)
                del rows[coordinate]
                self.assertEqual(laundry_cycle_metrics(model, rows),
                                 {"progress": None, "elapsed_time": None})
            self.assertEqual(laundry_cycle_metrics(model, observations(model, program=999)),
                             {"progress": None, "elapsed_time": None})

    def test_derivation_has_no_mutation_clock_or_identifier_output(self):
        rows = observations()
        before = deepcopy(rows)
        self.assertEqual(set(laundry_cycle_metrics(WASHER, rows)), {"progress", "elapsed_time"})
        self.assertEqual(rows, before)
        self.assertEqual(laundry_cycle_metrics(WASHER, {}), {"progress": None, "elapsed_time": None})
        self.assertEqual(laundry_cycle_metrics(WASHER, None), {"progress": None, "elapsed_time": None})


if __name__ == "__main__":
    unittest.main()
