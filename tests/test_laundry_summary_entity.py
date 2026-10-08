"""The existing laundry status entity exposes a current, read-only overview."""

from copy import deepcopy
from unittest.mock import AsyncMock
import unittest

from test_progress_entities import coordinator, scope, state, WASHER, DRYER, VACUUM


class LaundrySummaryEntityTests(unittest.TestCase):
    def entity(self, model=WASHER, key="2.1", pointer=None):
        namespace = scope()
        item = state(model)
        account = coordinator(item)
        account.async_execute_control = AsyncMock()
        entity = namespace["DreamePropertySensor"](account, item.device.did, key, pointer)
        return entity, item, account

    def test_existing_status_id_state_and_card_metadata_are_preserved(self):
        for model, appliance, program in ((WASHER, "washer", "Mixed"), (DRYER, "dryer", "AI Dry")):
            with self.subTest(model=model):
                entity, item, account = self.entity(model)
                before = deepcopy(item.store.properties)
                attributes = entity.extra_state_attributes
                self.assertEqual(entity._attr_unique_id, "fabricated-key:prop:2.1:state")
                self.assertEqual(entity._attr_name, "Operation state")
                self.assertEqual(entity.native_value, "Running")
                self.assertEqual((attributes["siid"], attributes["piid"]), (2, 1))
                self.assertEqual(attributes["raw_code"], 3)
                self.assertTrue(attributes["observation_fresh"])
                self.assertIsNotNone(attributes["observed_at"])
                self.assertEqual(attributes["appliance_type"], appliance)
                self.assertEqual(attributes["program"], program)
                self.assertTrue(attributes["is_running"])
                self.assertEqual(attributes["remaining_time"], 15)
                self.assertEqual(attributes["program_duration"], 60)
                self.assertEqual(attributes["progress"], 75)
                self.assertEqual(attributes["elapsed_time"], 45)
                self.assertEqual(item.store.properties, before)
                account.async_execute_control.assert_not_called()

    def test_expired_or_failed_running_data_never_becomes_a_current_running_flag(self):
        mutations = (
            lambda item: item.timestamps.update({"2.1": 1019}),
            lambda item: item.store.properties["2.1"].update(last_reply_null=True),
            lambda item: item.store.properties["2.1"].update(last_code=-1),
            lambda item: item.store.properties["2.1"].update(last_source="listing"),
            lambda item: item.store.properties["2.1"].update(last_item={"code": 0}),
        )
        for mutation in mutations:
            entity, item, _ = self.entity()
            mutation(item)
            attributes = entity.extra_state_attributes
            self.assertFalse(attributes["observation_fresh"])
            self.assertIsNone(attributes["is_running"])
            self.assertIsNone(attributes["status"])
            self.assertIsNone(attributes["progress"])

    def test_offline_removed_or_unloading_devices_clear_the_consolidated_snapshot(self):
        for target, key, value in (("item", "online", False), ("item", "present", False),
                                   ("account", "stopped", True),
                                   ("account", "entity_discovery_suspended", True)):
            entity, item, account = self.entity()
            setattr(item if target == "item" else account, key, value)
            attributes = entity.extra_state_attributes
            for attribute in ("status", "is_running", "program", "remaining_time", "progress"):
                self.assertIsNone(attributes[attribute], (key, attribute))

    def test_each_field_requires_its_own_current_observation(self):
        entity, item, _ = self.entity()
        item.timestamps["2.13"] = 1019
        item.store.properties["2.3"].update(last_reply_null=True)
        attributes = entity.extra_state_attributes
        self.assertTrue(attributes["is_running"])
        self.assertIsNone(attributes["remaining_time"])
        self.assertIsNone(attributes["program"])
        self.assertIsNone(attributes["progress"])

    def test_other_sensors_vacuums_and_json_leaves_do_not_gain_laundry_attributes(self):
        for model, key, pointer in ((WASHER, "2.4", None), (WASHER, "2.1", "/value"),
                                    (VACUUM, "2.1", None), ("dreame.washer.unverified", "2.1", None)):
            entity, _, _ = self.entity(model, key, pointer)
            self.assertNotIn("appliance_type", entity.extra_state_attributes)


if __name__ == "__main__":
    unittest.main()
