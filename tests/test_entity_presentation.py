"""Registry cleanup preserves user choices, and running evidence has a clock."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from dreamehome.laundry_controls import control_definitions
from dreamehome.presentation import control_presentation, cycle_presentation, property_presentation
import test_control_entities as controls
from test_entity_lifecycle import entity_scope
from test_progress_entities import coordinator, scope, state, WASHER, DRYER


class EntityPresentationTests(unittest.TestCase):
    def test_unknown_and_duplicate_readbacks_are_disabled_diagnostics_by_default(self):
        namespace = scope()
        item = state(WASHER)
        account = coordinator(item)
        for key in ("2.2", "2.11", "3.4", "3.9", "99.1"):
            entity = namespace["DreamePropertySensor"](account, item.device.did, key)
            self.assertEqual(entity._attr_entity_category, "diagnostic")
            self.assertFalse(entity._attr_entity_registry_enabled_default)
        for key in ("2.1", "2.3", "2.4", "2.12", "2.13", "3.14"):
            entity = namespace["DreamePropertySensor"](account, item.device.did, key)
            self.assertIsNone(entity._attr_entity_category)
            self.assertTrue(entity._attr_entity_registry_enabled_default)
        account.hass = SimpleNamespace(config=SimpleNamespace(language="de"))
        entity = namespace["DreamePropertySensor"](account, item.device.did, "2.1")
        self.assertEqual(entity._attr_name, "Operation state")
        self.assertEqual(entity._attr_unique_id, "fabricated-key:prop:2.1:state")

    def test_supported_settings_and_actions_are_controls_with_stable_ids_and_icons(self):
        boundary = controls.ControlBoundaryTests(methodName="runTest")
        boundary.setUp()
        for model in (WASHER, DRYER):
            boundary.state.device.model = model
            definitions = control_definitions(model)
            self.assertEqual(len(definitions), 16 if model == WASHER else 12)
            self.assertFalse({"power", "delay_time", "delay_enabled", "door_lock"}
                             & {row["key"] for row in definitions})
            for definition in definitions:
                with self.subTest(model=model, key=definition["key"]):
                    entity = boundary.scope["DreameControlEntity"](boundary.coordinator, "device", definition)
                    presentation = control_presentation(model, definition["key"], "de")
                    self.assertIsNone(entity._attr_entity_category)
                    self.assertTrue(entity._attr_entity_registry_enabled_default)
                    self.assertEqual(entity._attr_icon, presentation["icon"])
                    self.assertEqual(entity._attr_name, presentation["label"])
                    self.assertEqual(entity._attr_unique_id,
                                     f"device-key:control:{definition['kind']}:{definition['key']}")
            self.assertEqual(control_presentation(model, "program")["label"], "Selected program")
            self.assertEqual(control_presentation(model, "stop")["label"], "Stop and power off")

    def test_source_readiness_and_program_readback_are_main_sensors_without_new_coordinates(self):
        namespace = scope()
        for model in (WASHER, DRYER):
            item = state(model)
            account = coordinator(item)
            for coordinate, name, icon in (("2.3", "Active program", "mdi:format-list-bulleted"),
                                           ("3.14", "Remote start", "mdi:remote")):
                with self.subTest(model=model, coordinate=coordinate):
                    entity = namespace["DreamePropertySensor"](account, item.device.did, coordinate)
                    self.assertIsNone(entity._attr_entity_category)
                    self.assertTrue(entity._attr_entity_registry_enabled_default)
                    self.assertEqual(entity._attr_name, name)
                    self.assertEqual(entity._attr_icon, icon)
                    self.assertEqual(entity._attr_unique_id, f"fabricated-key:prop:{coordinate}:state")
            diagnostic = namespace["DreamePropertySensor"](account, item.device.did, "99.1")
            self.assertEqual(diagnostic._attr_icon, "mdi:code-braces")
            self.assertEqual(property_presentation(model, "2.2")["entity_category"], "diagnostic")
            delay = "2.11" if model == WASHER else "2.12"
            self.assertFalse(property_presentation(model, delay)["enabled_default"])
            self.assertEqual(cycle_presentation("progress")["label"], "Program progress")
            self.assertEqual(cycle_presentation("finish_time"),
                             {"label": "Program finish time", "icon": "mdi:clock-end"})

    def test_running_receipt_clock_and_freshness_reject_retained_null_failed_and_expired_state(self):
        namespace = scope()
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
        namespace["datetime"] = FixedDatetime
        namespace["monotonic"] = lambda: 1200
        item = state(WASHER)
        item.timestamps["2.1"] = 1170
        entity = namespace["DreamePropertySensor"](coordinator(item), item.device.did, "2.1")
        attributes = entity.extra_state_attributes
        self.assertEqual(attributes["raw_code"], 3)
        self.assertTrue(attributes["observation_fresh"])
        self.assertEqual(attributes["observed_at"], "2026-10-07T11:59:30+00:00")
        for mutation in (lambda: item.timestamps.update({"2.1": 1019}),
                         lambda: item.store.properties["2.1"].update(last_reply_null=True),
                         lambda: item.store.properties["2.1"].update(last_code=-1),
                         lambda: item.store.properties["2.1"].update(last_source="listing"),
                         lambda: item.store.properties["2.1"].update(last_item={"code": 0})):
            item.timestamps["2.1"] = 1170
            item.store.properties["2.1"].update(last_reply_null=False, last_code=0, last_source="mqtt", last_item={"value": 3})
            mutation()
            self.assertEqual(entity.extra_state_attributes["raw_code"], 3)
            self.assertFalse(entity.extra_state_attributes["observation_fresh"])
        item.timestamps["2.1"] = 1201
        self.assertIsNone(entity.extra_state_attributes["observed_at"])

    def test_registry_migration_hides_legacy_raw_without_disabling_or_renaming(self):
        namespace = entity_scope()
        def row(suffix, **changes):
            defaults = dict(entity_id="sensor." + suffix.replace(":", "_"), unique_id="fixed-key:" + suffix,
                            platform="dreame_home", entity_category=None, hidden_by=None,
                            disabled_by=None, name=None, icon=None, options={})
            return SimpleNamespace(**(defaults | changes))
        rows = [row("prop:2.3:state", entity_category="diagnostic", hidden_by="integration", disabled_by="integration"),
                row("prop:99.1:state"),
                row("prop:3.4:state", name="My readback"),
                row("prop:3.9:state", hidden_by="user"),
                row("prop:99.2:state", disabled_by="user"),
                row("prop:99.3:state", options={"sensor": {"display_precision": 3}}),
                row("prop:2.1:state", hidden_by="integration", entity_category="diagnostic"),
                row("control:select:program", entity_category="config"),
                row("control:switch:child_lock", entity_category="config"),
                row("cycle:progress", entity_category="diagnostic"),
                row("prop:99.4:state", platform="other_integration"),
                row("prop:99.5:state", unique_id="unrelated-key:prop:99.5:state"),
                row("prop:99.6:state", labels={"User label"}),
                row("prop:99.7:state", area_id="fabricated-area"),
                row("prop:3.14:state", entity_category="diagnostic", disabled_by="integration",
                    hidden_by="integration", name="My permission", icon="mdi:star"),
                row("prop:3.14:state", entity_id="sensor.user_permission", disabled_by="user", hidden_by="user"),
                row("prop:2.3:state", entity_id="sensor.user_program", disabled_by="user"),
                row("prop:3.14:state", entity_id="sensor.hidden_permission", disabled_by="integration", hidden_by="user"),
                row("prop:99.8:state", disabled_by="integration", hidden_by="integration"),
                row("prop:2.2:state"), row("prop:2.11:state"),
                row("control:switch:night_mode", entity_category="config")]
        calls = {}
        registry = SimpleNamespace(async_update_entity=lambda entity_id, **changes: calls.setdefault(entity_id, {}).update(changes))
        namespace["er"] = SimpleNamespace(async_get=lambda hass: registry,
                                            async_entries_for_config_entry=lambda registry, entry_id: rows,
                                            RegistryEntryDisabler=SimpleNamespace(USER="user", INTEGRATION="integration"),
                                            RegistryEntryHider=SimpleNamespace(INTEGRATION="integration"))
        item = SimpleNamespace(device=SimpleNamespace(model=WASHER))
        account = SimpleNamespace(devices={"fabricated": item}, device_key=lambda _: "fixed-key")
        entry = SimpleNamespace(entry_id="fabricated-entry", runtime_data=account)
        namespace["async_migrate_entity_presentation"](object(), entry)
        self.assertEqual(calls[rows[0].entity_id], {"entity_category": None, "hidden_by": None, "disabled_by": None})
        self.assertEqual(calls[rows[1].entity_id]["hidden_by"], "integration")
        for index in (2, 3, 4, 5):
            self.assertNotIn("hidden_by", calls.get(rows[index].entity_id, {}))
        self.assertEqual(calls[rows[6].entity_id], {"entity_category": None, "hidden_by": None})
        self.assertEqual(calls[rows[7].entity_id], {"entity_category": None})
        self.assertEqual(calls[rows[8].entity_id], {"entity_category": None})
        self.assertEqual(calls[rows[9].entity_id], {"entity_category": None})
        self.assertNotIn(rows[10].entity_id, calls)
        self.assertNotIn(rows[11].entity_id, calls)
        for index in (12, 13):
            self.assertNotIn("hidden_by", calls.get(rows[index].entity_id, {}))
        self.assertEqual(calls[rows[14].entity_id], {"entity_category": None, "hidden_by": None, "disabled_by": None})
        self.assertNotIn(rows[15].entity_id, calls)
        self.assertNotIn(rows[16].entity_id, calls)
        self.assertEqual(calls[rows[17].entity_id], {"disabled_by": None})
        self.assertEqual(calls[rows[18].entity_id], {"entity_category": "diagnostic"})
        for index in (19, 20):
            self.assertEqual(calls[rows[index].entity_id], {"entity_category": "diagnostic", "hidden_by": "integration"})
        self.assertEqual(calls[rows[21].entity_id], {"entity_category": None})
        self.assertTrue(all(not any(key in changes for key in ("new_entity_id", "name", "icon", "unique_id"))
                            for changes in calls.values()))
        promoted_ids = {rows[index].entity_id for index in (0, 14, 17)}
        self.assertEqual({entity_id for entity_id, changes in calls.items() if "disabled_by" in changes}, promoted_ids)


if __name__ == "__main__":
    unittest.main()
