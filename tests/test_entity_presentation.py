"""Registry cleanup preserves user choices, and running evidence has a clock."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from test_entity_lifecycle import entity_scope
from test_progress_entities import coordinator, scope, state, WASHER


class EntityPresentationTests(unittest.TestCase):
    def test_unknown_and_duplicate_readbacks_are_disabled_diagnostics_by_default(self):
        namespace = scope()
        item = state(WASHER)
        account = coordinator(item)
        for key in ("2.3", "3.4", "3.9", "99.1"):
            entity = namespace["DreamePropertySensor"](account, item.device.did, key)
            self.assertEqual(entity._attr_entity_category, "diagnostic")
            self.assertFalse(entity._attr_entity_registry_enabled_default)
        for key in ("2.1", "2.2", "2.4", "2.12", "2.13"):
            entity = namespace["DreamePropertySensor"](account, item.device.did, key)
            self.assertIsNone(entity._attr_entity_category)
            self.assertTrue(entity._attr_entity_registry_enabled_default)
        account.hass = SimpleNamespace(config=SimpleNamespace(language="de"))
        entity = namespace["DreamePropertySensor"](account, item.device.did, "2.1")
        self.assertEqual(entity._attr_name, "Betriebsstatus")
        self.assertEqual(entity._attr_unique_id, "fabricated-key:prop:2.1:state")

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
        rows = [row("prop:2.3:state"), row("prop:99.1:state"),
                row("prop:3.4:state", name="My readback"),
                row("prop:3.9:state", hidden_by="user"),
                row("prop:99.2:state", disabled_by="user"),
                row("prop:99.3:state", options={"sensor": {"display_precision": 3}}),
                row("prop:2.1:state", hidden_by="integration", entity_category="diagnostic"),
                row("control:select:program", entity_category="config"),
                row("control:switch:child_lock"),
                row("cycle:progress", entity_category="diagnostic"),
                row("prop:99.4:state", platform="other_integration"),
                row("prop:99.5:state", unique_id="unrelated-key:prop:99.5:state"),
                row("prop:99.6:state", labels={"User label"}),
                row("prop:99.7:state", area_id="fabricated-area")]
        calls = {}
        registry = SimpleNamespace(async_update_entity=lambda entity_id, **changes: calls.setdefault(entity_id, {}).update(changes))
        namespace["er"] = SimpleNamespace(async_get=lambda hass: registry,
                                            async_entries_for_config_entry=lambda registry, entry_id: rows,
                                            RegistryEntryDisabler=SimpleNamespace(USER="user"),
                                            RegistryEntryHider=SimpleNamespace(INTEGRATION="integration"))
        item = SimpleNamespace(device=SimpleNamespace(model=WASHER))
        account = SimpleNamespace(devices={"fabricated": item}, device_key=lambda _: "fixed-key")
        entry = SimpleNamespace(entry_id="fabricated-entry", runtime_data=account)
        namespace["async_migrate_entity_presentation"](object(), entry)
        self.assertEqual(calls[rows[0].entity_id], {"entity_category": "diagnostic", "hidden_by": "integration"})
        self.assertEqual(calls[rows[1].entity_id]["hidden_by"], "integration")
        for index in (2, 3, 4, 5):
            self.assertNotIn("hidden_by", calls.get(rows[index].entity_id, {}))
        self.assertEqual(calls[rows[6].entity_id], {"entity_category": None, "hidden_by": None})
        self.assertEqual(calls[rows[7].entity_id], {"entity_category": None})
        self.assertEqual(calls[rows[8].entity_id], {"entity_category": "config"})
        self.assertEqual(calls[rows[9].entity_id], {"entity_category": None})
        self.assertNotIn(rows[10].entity_id, calls)
        self.assertNotIn(rows[11].entity_id, calls)
        for index in (12, 13):
            self.assertNotIn("hidden_by", calls.get(rows[index].entity_id, {}))
        self.assertTrue(all(not any(key in changes for key in ("disabled_by", "new_entity_id", "name"))
                            for changes in calls.values()))


if __name__ == "__main__":
    unittest.main()
