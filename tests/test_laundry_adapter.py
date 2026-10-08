"""Offline source schema and beta read boundaries; no HA runtime or account."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from dreamehome.exceptions import AuthenticationError, DreameError, RateLimitError
from dreamehome.laundry import (
    LaundrySchema, enum_label, laundry_cloud_read_keys, laundry_cloud_values,
    laundry_definition, laundry_read_pairs, laundry_schema,
)
from dreamehome.observations import ObservationStore, VACUUM_INITIAL_READ_PAIRS, property_coordinate
from test_component_contract import isolated
from test_entity_lifecycle import entity_scope

WASHER = "dreame.washer.l9nacn"
DRYER = "dreame.dryer.l9nacn"
COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_home"


class ExactSchemaTests(unittest.TestCase):
    def test_exact_models_seed_only_source_read_or_notify_coordinates(self):
        washer, dryer = laundry_schema(WASHER), laundry_schema(DRYER)
        self.assertEqual(len(washer.properties), 27)
        self.assertEqual(len(washer.read_pairs), 24)
        self.assertEqual(len(dryer.read_pairs), 17)
        self.assertEqual(washer.direct_read_pairs, ((3, 14),))
        self.assertEqual(dryer.direct_read_pairs, ((3, 14),))
        self.assertTrue({(2, 5), (2, 19), (3, 5)}.isdisjoint(washer.read_pairs))
        for model in ("dreame.washer.l9", "dreame.dryer.l9nacn2", "dreame.vacuum.r5023a"):
            self.assertIsNone(laundry_schema(model))
            self.assertEqual(laundry_read_pairs(model), [])

    def test_coverage_distinguishes_null_failures_and_actual_observed_write_fields(self):
        coverage = laundry_schema(WASHER).coverage({
            "2.1": {"value": 3, "last_code": 0},
            "2.2": {"value": 0, "last_code": -4001},
            "2.4": {"value": None, "last_code": 0},
            "2.5": {"value": 1, "last_code": 0},
        })
        self.assertFalse(coverage["source_live_verified"])
        self.assertNotIn("controls_enabled", coverage)
        self.assertFalse(coverage["all_candidate_values_observed"])
        self.assertEqual(coverage["successful_value_count"], 1)
        self.assertEqual(coverage["successful_observed_count"], 2)
        self.assertEqual(coverage["failed_coordinates"], ["2.2"])

    def test_only_explicit_scalar_enum_mappings_translate(self):
        definition = laundry_definition(WASHER, "2.1")
        self.assertEqual(enum_label(definition, 3), "Running")
        for value in (True, "3", 3.0, 99, {"value": 3}):
            self.assertIsNone(enum_label(definition, value))
        # Domestic/export program tables are not copied onto a property with
        # no explicit mapping; inferred Boolean mappings keep their wire value.
        self.assertIsNone(enum_label({"name": "Program"}, 1))
        self.assertIsNone(enum_label({"value_list_inferred": True,
                                      "value_list": [{"value": 1, "label": "On"}]}, 1))
        self.assertIsNone(laundry_definition(DRYER, "4.7"))

    def test_compound_leaf_requires_its_own_mapping(self):
        root = {"name": "Phase", "unit": "min", "value_list": [{"value": 1, "label": "Running"}],
                "fields": {"/stage": {"name": "Stage", "value_list": [{"value": 1, "label": "Rinsing"}]}}}
        schema = LaundrySchema(WASHER, {"2.4": root}, ((2, 4),), (), {}, False)
        self.assertEqual(enum_label(schema.definition("2.4", "/stage"), 1), "Rinsing")
        unknown = schema.definition("2.4", "/remaining")
        self.assertIsNone(enum_label(unknown, 1))
        self.assertNotIn("unit", unknown)


class InitialReadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = SimpleNamespace(read_properties=AsyncMock(return_value=[]))
        freshness = isolated("coordinator.py", "_freshness", {"monotonic": lambda: 733}, owner="DreameCoordinator")
        self.coordinator = SimpleNamespace(api=self.api, _freshness=lambda state, touched: freshness(None, state, touched))
        self.read = isolated("coordinator.py", "_read", {
            "monotonic": lambda: 733, "VACUUM_INITIAL_READ_PAIRS": VACUUM_INITIAL_READ_PAIRS,
            "AuthenticationError": AuthenticationError, "RateLimitError": RateLimitError,
            "DreameError": DreameError, "laundry_read_pairs": laundry_read_pairs,
            "laundry_schema": laundry_schema,
            "property_coordinate": property_coordinate,
        }, owner="DreameCoordinator")

    def state(self, model):
        return SimpleNamespace(device=SimpleNamespace(model=model), store=ObservationStore(model),
                               timestamps={}, read_error=None, initial_read_done=False,
                               initial_read_status="not_started", schema_coverage={})

    async def test_exact_initial_plan_matches_only_returned_requested_coordinates(self):
        state = self.state(WASHER)
        self.api.read_properties.return_value = [
            {"siid": "2", "piid": "1", "value": 1, "code": 0},
            {"siid": 2, "piid": 2, "value": 4, "code": -4001},
            {"siid": 2, "piid": 5, "value": 4, "code": 0},
        ]
        await self.read(self.coordinator, state)
        self.assertEqual(self.api.read_properties.call_args.args[1], laundry_read_pairs(WASHER))
        self.assertNotIn("2.5", state.store.properties)
        self.assertNotIn("value", state.store.properties["2.2"])
        self.assertEqual(state.initial_read_status, "partial")
        self.assertEqual(state.schema_coverage["successful_value_count"], 1)
        self.api.read_properties.reset_mock()
        self.api.read_properties.return_value = []
        await self.read(self.coordinator, state)
        self.assertEqual(self.api.read_properties.call_args.args[1], laundry_read_pairs(WASHER))

    async def test_successful_mqtt_observation_allows_reading_a_write_only_source_field(self):
        state = self.state(WASHER)
        state.initial_read_done = True
        state.store.merge_properties([{"siid": 2, "piid": 5, "value": 4}], source="mqtt")
        await self.read(self.coordinator, state)
        self.assertEqual(self.api.read_properties.call_args.args[1], laundry_read_pairs(WASHER) + [(2, 5)])

    async def test_null_reply_does_not_count_as_complete_or_create_an_entity(self):
        state = self.state(DRYER)
        self.api.read_properties.return_value = [
            {"siid": siid, "piid": piid, "value": None if (siid, piid) == (3, 11) else 0, "code": 0}
            for siid, piid in laundry_read_pairs(DRYER)
        ]
        await self.read(self.coordinator, state)
        self.assertEqual(state.initial_read_status, "partial")
        self.assertEqual(state.schema_coverage["successful_value_count"], 16)
        scope = entity_scope()
        coordinator = SimpleNamespace(devices={"device": state}, entity_platforms={},
                                      async_add_listener=lambda callback: lambda: None)
        added = []
        scope["add_observed_entities"](coordinator, SimpleNamespace(async_on_unload=lambda callback: None),
                                        added.extend, lambda _, __, key, ___: key, boolean=False)
        self.assertNotIn("3.11", added)

    async def test_failed_and_null_replies_do_not_advance_value_freshness(self):
        state = self.state(DRYER)
        state.initial_read_done = True
        state.store.merge_properties([{"siid": 5, "piid": 1, "value": 2}], source="mqtt")
        state.timestamps["5.1"] = 10
        self.api.read_properties.return_value = [{"siid": 5, "piid": 1, "value": None, "code": 0}]
        await self.read(self.coordinator, state)
        self.assertEqual(state.timestamps["5.1"], 10)
        self.api.read_properties.return_value = [{"siid": 5, "piid": 1, "value": 4, "code": -4001}]
        await self.read(self.coordinator, state)
        self.assertEqual(state.timestamps["5.1"], 10)


class CloudSettingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = SimpleNamespace(get_device_data=AsyncMock(return_value={"prop.s_auto_upgrade": "0"}))
        self.coordinator = SimpleNamespace(api=self.api)
        self.read = isolated("coordinator.py", "_cloud_data", {
            "laundry_cloud_read_keys": laundry_cloud_read_keys,
            "laundry_cloud_values": laundry_cloud_values,
            "AuthenticationError": AuthenticationError, "RateLimitError": RateLimitError,
            "DreameError": DreameError,
        }, owner="DreameCoordinator")
        self.state = SimpleNamespace(device=SimpleNamespace(model=WASHER, did="device"),
                                     store=ObservationStore(WASHER), cached_rows={},
                                     cloud_data_keys=set(), cloud_data_error=None,
                                     present=True, online=False, read_error=None,
                                     subscription=None)

    async def test_known_key_preserves_raw_strings_and_ignores_other_identity_envelope(self):
        self.api.get_device_data.return_value = {"device": {"prop.s_auto_upgrade": "1", "uid": "private"},
                                                "other-device": {"prop.s_auto_upgrade": "0"}}
        await self.read(self.coordinator, self.state)
        self.api.get_device_data.assert_awaited_once_with("device", ["prop.s_auto_upgrade"])
        self.assertEqual(self.state.store.cached, {"prop.s_auto_upgrade": "1"})
        self.assertEqual(laundry_cloud_read_keys("dreame.washer.unverified"), [])
        scope = entity_scope()
        coordinator = SimpleNamespace(devices={"device": self.state}, device_key=lambda _: "key",
                                      last_update_success=True)
        entity = scope["DreamePropertyEntity"](coordinator, "device", "cached:prop.s_auto_upgrade")
        self.assertEqual(entity._attr_name, "Automatic firmware updates")
        self.assertEqual(entity.value, "1")
        self.assertTrue(entity.available)  # A cloud setting is readable while the appliance is offline.
        self.assertEqual(entity.extra_state_attributes["source"], "cloud_userdata")

    async def test_missing_value_does_not_create_default_or_write(self):
        self.api.get_device_data.return_value = {"device": {"prop.s_auto_upgrade": {}}}
        await self.read(self.coordinator, self.state)
        self.assertEqual(self.state.store.cached, {})
        self.assertIsNone(self.state.cloud_data_error)

    async def test_cloud_setting_failure_is_local_but_authentication_propagates(self):
        from dreamehome.exceptions import TransportError
        self.state.online = True
        await self.read(self.coordinator, self.state)
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": 1}])
        self.api.get_device_data.side_effect = TransportError("offline")
        await self.read(self.coordinator, self.state)
        self.assertEqual(self.state.cloud_data_error, "TransportError")
        self.assertIsNone(self.state.read_error)
        scope = entity_scope()
        coordinator = SimpleNamespace(devices={"device": self.state}, device_key=lambda _: "key",
                                      last_update_success=True)
        setting = scope["DreamePropertyEntity"](coordinator, "device", "cached:prop.s_auto_upgrade")
        telemetry = scope["DreamePropertyEntity"](coordinator, "device", "2.1")
        self.assertFalse(setting.available)
        self.assertTrue(telemetry.available)
        self.api.get_device_data.side_effect = AuthenticationError("expired")
        with self.assertRaises(AuthenticationError):
            await self.read(self.coordinator, self.state)


class FriendlySensorTests(unittest.TestCase):
    def sensor_scope(self):
        scope = entity_scope()

        class Sensor:
            @property
            def device_class(self):
                return getattr(self, "_attr_device_class", None)

        source = ast.parse((COMPONENT / "sensor.py").read_text(encoding="utf-8"))
        source.body = [node for node in source.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        import math
        from dreamehome.laundry_progress import laundry_cycle_metrics, progress_definitions
        from dreamehome.laundry_summary import laundry_appliance_summary
        from dreamehome.presentation import cycle_presentation
        from dreamehome.vacuum_telemetry import vacuum_telemetry_available
        scope.update(SensorEntity=Sensor, SensorDeviceClass=SimpleNamespace(BATTERY="battery", DURATION="duration", AREA="area"),
                     SensorStateClass=SimpleNamespace(MEASUREMENT="measurement"),
                     laundry_cycle_metrics=laundry_cycle_metrics, progress_definitions=progress_definitions,
                     laundry_appliance_summary=laundry_appliance_summary,
                     cycle_presentation=cycle_presentation,
                     vacuum_telemetry_available=vacuum_telemetry_available,
                     PERCENTAGE="%", enum_label=enum_label, math=math, monotonic=lambda: 1200)
        exec(compile(source, "sensor.py", "exec"), scope)
        return scope

    def test_entity_name_enum_raw_code_and_literal_unit_follow_exact_schema(self):
        scope = self.sensor_scope()
        store = ObservationStore(WASHER)
        store.merge_properties([{"siid": 2, "piid": 1, "value": 3}, {"siid": 2, "piid": 13, "value": 54}])
        state = SimpleNamespace(device=SimpleNamespace(model=WASHER), store=store)
        coordinator = SimpleNamespace(devices={"device": state}, device_key=lambda _: "key")
        status = scope["DreamePropertySensor"](coordinator, "device", "2.1")
        self.assertEqual(status._attr_name, "Operation state")
        self.assertEqual(status.native_value, "Running")
        self.assertEqual(status.extra_state_attributes["raw_code"], 3)
        remaining = scope["DreamePropertySensor"](coordinator, "device", "2.13")
        self.assertEqual(remaining._attr_native_unit_of_measurement, "min")
        self.assertEqual(remaining.native_value, 54)
        store.merge_properties([{"siid": 2, "piid": 13, "value": "unrecognized"}])
        self.assertIsNone(remaining.native_value)

    def test_program_readback_uses_english_app_label_without_changing_observation(self):
        from dreamehome.catalog import load_catalog
        scope = self.sensor_scope()
        for model, raw, expected, source in ((WASHER, 8, "Underwear", "Delicates"),
                                              (WASHER, 11, "Anti-Allergen", "Allergy Care"),
                                              (DRYER, 7, "Baby Care", "Towels"),
                                              (DRYER, 8, "Underwear", "Delicates")):
            with self.subTest(model=model, raw=raw):
                store = ObservationStore(model)
                store.merge_properties([{"siid": 2, "piid": 3, "value": raw},
                                         {"siid": 2, "piid": 1, "value": 3}])
                state = SimpleNamespace(device=SimpleNamespace(model=model), store=store,
                                        present=True, online=True, timestamps={"2.1": 1200, "2.3": 1200})
                coordinator = SimpleNamespace(devices={"device": state}, device_key=lambda _: "key",
                                              stopped=False, entity_discovery_suspended=False,
                                              hass=SimpleNamespace(config=SimpleNamespace(language="de-DE")))
                sensor = scope["DreamePropertySensor"](coordinator, "device", "2.3")
                self.assertEqual(sensor._attr_name, "Active program")
                self.assertEqual(sensor.native_value, expected)
                self.assertEqual(enum_label(sensor.definition, raw), expected)
                self.assertEqual(sensor.extra_state_attributes["raw_code"], raw)
                self.assertEqual(store.properties["2.3"]["value"], raw)
                self.assertEqual(scope["presentation_language"](coordinator), "en")
                source_rows = next(row for row in load_catalog("l9_washer" if model == WASHER else "l9_dryer")["properties"]
                                   if row["siid"] == 2 and row["piid"] == 3)["value_list"]
                self.assertEqual(next(row["label"] for row in source_rows if row["value"] == raw), source)

    def test_numeric_roots_reject_compounds_and_keep_leaf_observations(self):
        scope = self.sensor_scope()
        for model, pair, unit in ((WASHER, (2, 13), "min"),
                                  ("dreame.vacuum.r5023a", (3, 1), "%")):
            with self.subTest(model=model):
                store = ObservationStore(model)
                store.merge_properties([{"siid": pair[0], "piid": pair[1], "value": 54}])
                state = SimpleNamespace(device=SimpleNamespace(model=model), store=store,
                                        present=True, online=True, subscription=None, read_error=None)
                coordinator = SimpleNamespace(devices={"device": state}, device_key=lambda _: "key",
                                              last_update_success=True)
                key = f"{pair[0]}.{pair[1]}"
                sensor = scope["DreamePropertySensor"](coordinator, "device", key)
                self.assertEqual(sensor._attr_native_unit_of_measurement, unit)
                self.assertEqual(sensor.native_value, 54)
                self.assertTrue(sensor.available)
                for value in ({"remaining": 53}, [{"k": "remaining", "v": 52}],
                              '{"remaining":51}', "invalid", True, float("inf")):
                    store.merge_properties([{"siid": pair[0], "piid": pair[1], "value": value}])
                    self.assertIsNone(sensor.native_value)
                    self.assertFalse(sensor.available)
                    self.assertEqual(sensor.observation["value"], value)
                store.merge_properties([{"siid": pair[0], "piid": pair[1], "value": {"remaining": 50}}])
                self.assertIn((key, "/remaining", 50), list(scope["readings"](state)))
                store.merge_properties([{"siid": pair[0], "piid": pair[1], "value": 49}])
                self.assertEqual(sensor.native_value, 49)
                self.assertTrue(sensor.available)
                if model == "dreame.vacuum.r5023a":
                    for value in (-1, 101):
                        store.merge_properties([{"siid": pair[0], "piid": pair[1], "value": value}])
                        self.assertIsNone(sensor.native_value)
                        self.assertFalse(sensor.available)

    def test_unitless_structured_roots_remain_available(self):
        scope = self.sensor_scope()
        store = ObservationStore(WASHER)
        store.merge_properties([{"siid": 99, "piid": 1, "value": {"remaining": 53}}])
        state = SimpleNamespace(device=SimpleNamespace(model=WASHER), store=store,
                                present=True, online=True, subscription=None, read_error=None)
        coordinator = SimpleNamespace(devices={"device": state}, device_key=lambda _: "key",
                                      last_update_success=True)
        sensor = scope["DreamePropertySensor"](coordinator, "device", "99.1")
        self.assertEqual(sensor.native_value, "structured")
        self.assertTrue(sensor.available)
        self.assertIn(("99.1", "/remaining", 53), list(scope["readings"](state)))

    def test_cached_semantic_credentials_are_redacted_before_entity_projection(self):
        scope = entity_scope()
        state = SimpleNamespace(store=SimpleNamespace(cached={"settings": {"key": "refresh_token", "value": "private"}}),
                                cached_rows={})
        projected = scope["cached_row"](state, "settings")
        self.assertNotEqual(projected["entity_fields"]["/value"], "private")
        self.assertEqual(state.store.cached["settings"]["value"], "private")


if __name__ == "__main__":
    unittest.main()
