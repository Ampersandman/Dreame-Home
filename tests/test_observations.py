"""Appliance-independent read observation and unknown-data preservation."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dreamehome.observations import (
    ObservationStore, VACUUM_INITIAL_READ_PAIRS, compound_fields, entity_fields, property_coordinate,
)


class CoordinateTests(unittest.TestCase):
    def test_coordinates_do_not_confuse_device_or_local_enum_ids(self):
        for value in ("prop.2.1", "2.1", {"siid": "2", "piid": 1}, {"did": "2.1"}):
            self.assertEqual(property_coordinate(value), (2, 1))
        for value in ("-123456", "0", "prop.0.1", "2.1.3", {"siid": True, "piid": 1},
                      {"siid": 2.5, "piid": 1}, {"siid": 0, "piid": 1}):
            self.assertIsNone(property_coordinate(value))


class ObservationTests(unittest.TestCase):
    def test_washer_metadata_does_not_inherit_vacuum_names(self):
        store = ObservationStore("dreame.washer.l9nacn")
        touched = store.merge_cached({
            "did": "private-device", "model": store.model, "masterUid": "private-owner",
            "property": '{"prop.2.1":5,"77.81":{"value":true},"vendor_blob":{"new":1}}',
        })
        result = store.snapshot()
        self.assertEqual(touched, {"2.1", "77.81"})
        self.assertEqual(result["properties"]["2.1"]["value"], 5)
        self.assertNotIn("name", result["properties"]["2.1"])
        self.assertIs(result["properties"]["77.81"]["value"], True)
        self.assertEqual(result["cached"], {"vendor_blob": {"new": 1}})
        self.assertNotIn("private-owner", json.dumps(result))

    def test_failed_poll_preserves_last_good_value_and_error_evidence(self):
        store = ObservationStore("dreame.vacuum.r5023a")
        good = {"did": "1", "siid": 3, "piid": 1, "code": 0, "value": 81}
        failed = {"did": "1", "siid": 3, "piid": 1, "code": -4001, "value": 0}
        store.merge_properties([good])
        store.merge_properties([failed])
        observation = store.snapshot()["properties"]["3.1"]
        self.assertEqual(observation["value"], 81)
        self.assertEqual(observation["code"], 0)
        self.assertEqual(observation["last_code"], -4001)
        self.assertEqual(observation["last_item"], failed)
        self.assertEqual(observation["name"], "BATTERY_LEVEL")

    def test_unknown_mqtt_property_compound_and_event_are_retained(self):
        store = ObservationStore("dreame.dryer.l9nacn")
        raw_value = '[{"k":"UnseenSetting","v":3},{"k":"VendorFuture","v":{"x":true}}]'
        envelope = {"id": 92, "did": "private-id", "data": {
            "method": "properties_changed", "params": [
                {"siid": 77, "piid": 81, "value": raw_value},
            ],
        }}
        self.assertEqual(store.merge_push(json.dumps(envelope).encode()), {"77.81"})
        event = {"data": {"method": "event_occured", "params": {"siid": 9, "eiid": 3, "arguments": [1, 2]}}}
        store.merge_push(event)
        unknown = {"method": "future_vendor_method", "params": {"private_field": "preserved"}}
        store.merge_push(unknown)
        result = store.snapshot()
        observation = result["properties"]["77.81"]
        self.assertEqual(observation["value"], raw_value)
        self.assertEqual(observation["compound"], json.loads(raw_value))
        self.assertEqual(observation["compound_fields"]["/1/v/x"], True)
        self.assertEqual(observation["entity_fields"]["/@VendorFuture/v/x"], True)
        self.assertEqual([item["payload"] for item in result["events"]], [event, unknown])

    def test_null_rpc_preserves_mqtt_value_and_source_without_creating_a_value(self):
        store = ObservationStore("dreame.dryer.l9nacn")
        store.merge_properties([{"siid": 5, "piid": 1, "value": 1}], source="mqtt")
        null_reply = {"siid": 5, "piid": 1, "code": 0, "value": None}
        store.merge_properties([null_reply, {"siid": 3, "piid": 11, "code": 0, "value": None}])
        ota = store.properties["5.1"]
        self.assertEqual(ota["value"], 1)
        self.assertEqual(ota["source"], "mqtt")
        self.assertEqual(ota["last_source"], "rpc")
        self.assertEqual(ota["last_item"], null_reply)
        self.assertIs(ota["last_reply_null"], True)
        self.assertNotIn("value", store.properties["3.11"])
        store.merge_properties([{"siid": 5, "piid": 1, "value": 2}], source="mqtt")
        self.assertFalse(store.properties["5.1"]["last_reply_null"])
        self.assertEqual(store.properties["5.1"]["value"], 2)

    def test_successful_scalar_refresh_clears_previous_compound_projection(self):
        store = ObservationStore("unknown")
        store.merge_properties([{"siid": 2, "piid": 1, "value": '{"a":1}'}])
        store.merge_push({"method": "properties_changed", "params": {"prop.2.1": 12}})
        result = store.snapshot()["properties"]["2.1"]
        self.assertEqual(result["value"], 12)
        self.assertNotIn("compound", result)
        self.assertEqual(result["source"], "mqtt")

    def test_unknown_unsupported_properties_do_not_acquire_values(self):
        store = ObservationStore("unknown")
        store.merge_properties([{"siid": 22, "piid": 10, "code": -4004}, {"unexpected": [4]}])
        result = store.snapshot()
        self.assertNotIn("value", result["properties"]["22.10"])
        self.assertEqual(result["events"][0]["payload"], {"unexpected": [4]})

    def test_snapshot_is_independent_of_inputs_and_mutations(self):
        store = ObservationStore("unknown")
        row = {"siid": 2, "piid": 1, "value": {"x": [1]}}
        store.merge_properties([row])
        row["value"]["x"].append(2)
        snapshot = store.snapshot()
        snapshot["properties"]["2.1"]["value"]["x"].append(3)
        self.assertEqual(store.snapshot()["properties"]["2.1"]["value"], {"x": [1]})

    def test_event_property_cached_bounds_are_visible(self):
        store = ObservationStore("unknown", max_events=2, max_properties=1, max_cached_keys=1)
        for number in range(4):
            store.merge_push({"method": "custom", "params": number})
        store.merge_cached({"2.1": 10, "2.2": 11, "a": 1, "b": 2})
        result = store.snapshot()
        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(result["dropped_events"], 2)
        self.assertEqual(result["dropped_properties"], 1)
        self.assertEqual(result["dropped_cached_keys"], 1)

    def test_bad_or_oversized_json_remains_raw_and_diagnosable(self):
        store = ObservationStore("unknown", max_json_chars=10)
        store.merge_properties([
            {"siid": 2, "piid": 1, "value": '{"a":'},
            {"siid": 2, "piid": 2, "value": '{"long_key":1}'},
            {"siid": 2, "piid": 3, "value": "123"},
        ])
        result = store.snapshot()["properties"]
        self.assertEqual(result["2.1"]["decode_error"], "invalid_json")
        self.assertEqual(result["2.2"]["decode_error"], "json_too_large")
        self.assertEqual(result["2.2"]["value"], '{"long_key":1}')
        self.assertNotIn("compound", result["2.3"])

    def test_initial_vacuum_plan_is_15_explicit_pairs(self):
        self.assertEqual(len(VACUUM_INITIAL_READ_PAIRS), 15)
        self.assertEqual(len(set(VACUUM_INITIAL_READ_PAIRS)), 15)


class CompoundTests(unittest.TestCase):
    def test_entity_setting_paths_survive_reordering_and_escape_keys(self):
        values = [{"k": "AutoDry", "v": True}, {"k": "odd/key~", "v": {"level": 3}}]
        before, truncated = entity_fields(values)
        after, _ = entity_fields(list(reversed(values)))
        self.assertEqual(before, after)
        self.assertEqual(before, {"/@AutoDry/v": True, "/@odd~1key~0/v/level": 3})
        self.assertFalse(truncated)

    def test_single_setting_record_uses_the_same_identity_as_a_list(self):
        single = {"k": "AutoDry", "v": True}
        self.assertEqual(entity_fields(single)[0], entity_fields([single])[0])

    def test_unkeyed_or_ambiguous_arrays_stay_on_compound_root(self):
        for values in ([1, 2], [{"v": 3}], [{"k": "same", "v": 1}, {"k": "same", "v": 2}],
                       [{"k": 1, "v": 1}, {"k": "1", "v": 2}]):
            fields, _ = entity_fields({"array": values, "scalar": 4})
            self.assertEqual(fields, {"/scalar": 4})

    def test_entity_projection_is_bounded_independently(self):
        fields, truncated = entity_fields([{"k": str(i), "v": i} for i in range(50)], max_fields=3)
        self.assertEqual(len(fields), 3)
        self.assertTrue(truncated)

    def test_pointer_escaping_and_bounded_projection(self):
        fields, truncated = compound_fields({"a/b": {"~key": 1}, "other": 2})
        self.assertEqual(fields, {"/a~1b/~0key": 1, "/other": 2})
        self.assertFalse(truncated)
        fields, truncated = compound_fields({str(i): i for i in range(100)}, max_fields=3)
        self.assertEqual(len(fields), 3)
        self.assertTrue(truncated)
        fields, truncated = compound_fields({"a": {"b": {"c": 1}}}, max_depth=2)
        self.assertEqual(fields, {})
        self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
