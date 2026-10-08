"""Native laundry readbacks and finish estimates follow actual cycle context."""

from datetime import datetime, timedelta, timezone
import unittest

from dreamehome.laundry_progress import progress_definitions
from test_progress_entities import coordinator, scope, state, WASHER, DRYER


class LaundryReadbackTests(unittest.TestCase):
    def entity(self, model, coordinate):
        namespace = scope()
        item = state(model)
        account = coordinator(item)
        entity = namespace["DreamePropertySensor"](account, item.device.did, coordinate)
        return entity, item, account

    def test_active_program_is_read_only_running_or_paused_with_stable_coordinate(self):
        for model, expected in ((WASHER, "Mixed"), (DRYER, "AI Dry")):
            entity, item, _ = self.entity(model, "2.3")
            identity = entity._attr_unique_id
            self.assertEqual(entity._attr_name, "Active program")
            self.assertEqual(entity.native_value, expected)
            self.assertTrue(entity.available)
            for status in (2, 3):
                item.store.merge_properties([{"siid": 2, "piid": 1, "value": status}])
                self.assertEqual(entity.native_value, expected)
            for status in (0, 1, 99, True):
                item.store.merge_properties([{"siid": 2, "piid": 1, "value": status}])
                self.assertIsNone(entity.native_value)
                self.assertEqual(entity.available, type(status) is int and status in (0, 1))
                self.assertEqual(entity._attr_unique_id, identity)
            self.assertIn(":prop:2.3:state", identity)
            self.assertEqual(item.store.properties["2.3"]["value"], 2 if model == WASHER else 0)

    def test_active_program_never_uses_cached_or_stale_operating_context(self):
        for key in ("2.1", "2.3"):
            for changes in ({"last_source": "listing"}, {"last_code": -1},
                            {"last_reply_null": True}, {"last_item": {"code": 0}}):
                entity, item, _ = self.entity(WASHER, "2.3")
                item.store.properties[key].update(changes)
                self.assertIsNone(entity.native_value)
                self.assertFalse(entity.available)
            entity, item, _ = self.entity(WASHER, "2.3")
            item.timestamps[key] -= 181
            self.assertIsNone(entity.native_value)

    def test_remote_start_is_fresh_strict_read_only_authorization(self):
        for model in (WASHER, DRYER):
            entity, item, _ = self.entity(model, "3.14")
            self.assertEqual(entity._attr_name, "Remote start")
            self.assertIsNone(entity._attr_entity_category)
            self.assertEqual(entity._attr_icon, "mdi:remote")
            self.assertIn(":prop:3.14:state", entity._attr_unique_id)
            for value, expected in ((0, "Off"), (1, "On"), (True, None), (False, None),
                                    (2, None), (1.0, None), ("1", None), (None, None)):
                item.store.merge_properties([{"siid": 3, "piid": 14, "value": value}], source="mqtt")
                self.assertEqual(entity.native_value, expected)
                self.assertEqual(entity.available, expected is not None)
            item.store.merge_properties([{"siid": 3, "piid": 14, "value": 1}], source="mqtt")
            item.timestamps["3.14"] -= 181
            self.assertIsNone(entity.native_value)
            self.assertFalse(entity.available)

    def test_readbacks_are_unavailable_offline_absent_or_during_unload(self):
        for coordinate in ("2.3", "3.14"):
            for mode in ("offline", "absent", "stopped", "unloading"):
                entity, item, account = self.entity(WASHER, coordinate)
                if mode == "offline":
                    item.online = False
                elif mode == "absent":
                    item.present = False
                elif mode == "stopped":
                    account.stopped = True
                else:
                    account.entity_discovery_suspended = True
                self.assertIsNone(entity.native_value)
                self.assertFalse(entity.available)


class LaundryFinishTimeTests(unittest.TestCase):
    def entity(self, model=WASHER):
        namespace = scope()
        item = state(model)
        account = coordinator(item)
        clock = [1200.0]
        wall = [datetime(2026, 10, 8, 12, tzinfo=timezone.utc)]

        class WallClock:
            @staticmethod
            def now(zone):
                return wall[0].astimezone(zone)

        namespace.update(monotonic=lambda: clock[0], datetime=WallClock)
        definition = next(row for row in progress_definitions(model) if row["key"] == "finish_time")
        entity = namespace["DreameCycleSensor"](account, item.device.did, definition)
        return entity, item, account, clock, wall

    def test_timestamp_is_anchored_to_the_remaining_observation_and_does_not_drift(self):
        for model, coordinate in ((WASHER, "2.13"), (DRYER, "2.11")):
            entity, item, _, clock, wall = self.entity(model)
            item.timestamps[coordinate] = 1170.0
            finish = datetime(2026, 10, 8, 12, 14, 30, tzinfo=timezone.utc)
            self.assertEqual(entity.native_value, finish)
            self.assertTrue(entity.available)
            self.assertEqual(entity.device_class, "timestamp")
            self.assertIsNone(entity._attr_state_class)
            self.assertIsNone(entity._attr_native_unit_of_measurement)
            self.assertEqual(entity._attr_name, "Program finish time")
            self.assertEqual(entity._attr_icon, "mdi:clock-end")
            self.assertTrue(entity.extra_state_attributes["estimated"])
            self.assertIn(":cycle:finish_time", entity._attr_unique_id)
            clock[0] += 45
            wall[0] += timedelta(seconds=45)
            self.assertEqual(entity.native_value, finish)
            siid, piid = map(int, coordinate.split("."))
            item.store.merge_properties([{"siid": siid, "piid": piid, "value": 12}], source="rpc")
            item.timestamps[coordinate] = clock[0]
            self.assertEqual(entity.native_value, wall[0] + timedelta(minutes=12))

    def test_pause_standby_schedule_completion_add_clothes_and_aftercare_have_no_eta(self):
        for model in (WASHER, DRYER):
            for status in (0, 1, 2, 99):
                entity, item, _, _, _ = self.entity(model)
                item.store.merge_properties([{"siid": 2, "piid": 1, "value": status}])
                self.assertIsNone(entity.native_value)
                self.assertFalse(entity.available)
            for phase in ((0, 5, 6, 7, 99) if model == WASHER else (0, 1, 2, 99)):
                entity, item, _, _, _ = self.entity(model)
                item.store.merge_properties([{"siid": 2, "piid": 4, "value": phase}])
                self.assertIsNone(entity.native_value)

    def test_invalid_or_unfresh_duration_does_not_create_finish_time(self):
        for model, coordinate in ((WASHER, "2.13"), (DRYER, "2.11")):
            for value in (0, -1, 61, True, "15", None):
                entity, item, _, _, _ = self.entity(model)
                siid, piid = map(int, coordinate.split("."))
                item.store.merge_properties([{"siid": siid, "piid": piid, "value": value}])
                self.assertIsNone(entity.native_value)
            for changes in ({"last_source": "listing"}, {"last_code": -1},
                            {"last_reply_null": True}, {"last_item": {"code": 0}}):
                entity, item, _, _, _ = self.entity(model)
                item.store.properties[coordinate].update(changes)
                self.assertIsNone(entity.native_value)
            entity, item, _, clock, wall = self.entity(model)
            self.assertIsNotNone(entity.native_value)
            clock[0] += 181
            wall[0] += timedelta(seconds=181)
            self.assertIsNone(entity.native_value)
            self.assertFalse(entity.available)

    def test_offline_unload_and_overflow_do_not_expose_an_eta(self):
        for mode in ("offline", "absent", "stopped", "unloading", "overflow"):
            entity, item, account, _, _ = self.entity()
            self.assertIsNotNone(entity.native_value)
            if mode == "offline":
                item.online = False
            elif mode == "absent":
                item.present = False
            elif mode == "stopped":
                account.stopped = True
            elif mode == "unloading":
                account.entity_discovery_suspended = True
            else:
                item.store.merge_properties([{"siid": 2, "piid": 12, "value": 10**50},
                                             {"siid": 2, "piid": 13, "value": 10**49}])
            self.assertIsNone(entity.native_value)
            self.assertFalse(entity.available)


if __name__ == "__main__":
    unittest.main()
