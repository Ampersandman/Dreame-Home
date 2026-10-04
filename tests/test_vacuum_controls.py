"""Pinned encoders and isolated native vacuum boundaries, without live writes."""

import ast
from copy import deepcopy
from enum import IntFlag, StrEnum
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from dreamehome.catalog import load_catalog
from dreamehome.observations import ObservationStore
from dreamehome.vacuum_controls import (
    FAN_SPEEDS, SOURCE_REVISION, VACUUM_MODEL, prepare_vacuum_command,
    vacuum_command_available, vacuum_control_supported, vacuum_required_coordinates,
    vacuum_state,
)
from test_entity_lifecycle import entity_scope

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components/dreame_home"


def observations(**values):
    rows = {"2.1": 2, "2.2": 0, "3.1": 75, "3.2": 2, "4.1": 17,
            "4.7": 0, "4.4": 1, "4.25": 0, "4.26": 0, "4.47": 0,
            "4.50": '[{"k":"SuctionMax","v":0},{"k":"SmartHost","v":0}]', "4.60": 0}
    rows.update(values)
    return {key: {"value": value, "last_code": 0} for key, value in rows.items()}


class SourceEncoderTests(unittest.TestCase):
    def test_exact_model_uses_common_source_mappings_and_new_state_capability(self):
        model = next(row for row in load_catalog("models") if row["model"] == VACUUM_MODEL)
        self.assertEqual(model["device_info_row"], [0, 0, 104, 5])
        capabilities = dict(model["capability_data"])
        self.assertEqual(capabilities[load_catalog("enums")["DeviceCapability"]["members"]["NEW_STATE"]], 1)
        source_actions = {row["name"]: row for row in load_catalog("actions")}
        for command, name in (("start", "START"), ("pause", "PAUSE"),
                              ("stop", "STOP"), ("return_to_base", "CHARGE")):
            plan = prepare_vacuum_command(VACUUM_MODEL, command, observations=observations())
            self.assertEqual(plan["method"], "action")
            self.assertEqual({key: plan["action"][key] for key in ("siid", "aiid")}, source_actions[name]["mapping"])
            self.assertEqual(plan["action"]["in"], [])
            self.assertIn(SOURCE_REVISION, source_actions[name]["source"]["url"])
            self.assertNotIn("did", plan["action"])
        source_fan = next(row for row in load_catalog("properties") if row["name"] == "SUCTION_LEVEL")
        self.assertEqual(source_fan["mapping"], {"siid": 4, "piid": 4})
        source_enums = load_catalog("enums")["DreameVacuumSuctionLevel"]["members"]
        self.assertEqual(FAN_SPEEDS, {"silent": source_enums["QUIET"], "standard": source_enums["STANDARD"],
                                     "strong": source_enums["STRONG"], "turbo": source_enums["TURBO"]})

    def test_unconfirmed_models_and_unknown_commands_are_rejected(self):
        for model in ("dreame.vacuum.r5023", "dreame.vacuum.r5023a2", "dreame.washer.l9nacn"):
            self.assertFalse(vacuum_control_supported(model))
            self.assertIsNone(vacuum_state(model, observations())["activity"])
            self.assertEqual(vacuum_state(model, observations())["fan_speed_list"], [])
            with self.assertRaises(ValueError):
                prepare_vacuum_command(model, "start", observations=observations())
        for command in ("action", "send_command", "clean_room", "start_custom", "locate"):
            with self.assertRaises(ValueError):
                prepare_vacuum_command(VACUUM_MODEL, command, observations=observations())

    def test_fan_modes_and_exact_maximum_patch_do_not_mutate_input(self):
        rows = observations()
        original = deepcopy(rows)
        for name, code in FAN_SPEEDS.items():
            plan = prepare_vacuum_command(VACUUM_MODEL, "set_fan_speed", name, rows)
            self.assertEqual(plan, {"method": "set_properties", "properties": [{"siid": 4, "piid": 4, "value": code}]})
        rows["4.50"]["value"] = [{"k": "SuctionMax", "v": 1}, {"k": "OtherSetting", "v": 7}]
        saved = deepcopy(rows)
        plan = prepare_vacuum_command(VACUUM_MODEL, "set_fan_speed", "strong", rows)
        self.assertEqual(plan["properties"], [
            {"siid": 4, "piid": 50, "value": '{"k":"SuctionMax","v":0}'},
            {"siid": 4, "piid": 4, "value": 2},
        ])
        self.assertTrue(plan["sequential"])
        self.assertEqual(rows, saved)
        rows["4.50"] = original["4.50"]
        self.assertEqual(rows, original)

    def test_unknown_duplicate_or_invalid_maximum_setting_never_creates_patch(self):
        for value in (None, "invalid", [], [{"k": "Other", "v": 1}],
                      {"k": "SuctionMax", "v": True}, {"k": "SuctionMax", "v": "1"},
                      {"k": "SuctionMax", "v": 2}, {"k": "SuctionMax", "v": float("inf")},
                      [{"k": "SuctionMax", "v": 0}, {"k": "SuctionMax", "v": 1}]):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                prepare_vacuum_command(VACUUM_MODEL, "set_fan_speed", "turbo", observations(**{"4.50": value}))
        for value in (None, True, 0, 1, 4, float("inf"), "3", "Turbo", "quiet"):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                prepare_vacuum_command(VACUUM_MODEL, "set_fan_speed", value, observations())

    def test_invalid_context_replies_and_codes_never_enable_commands(self):
        for value in (None, True, "2", 2.0, float("nan"), {"status": 2}, 999):
            rows = observations(**{"2.1": value})
            self.assertFalse(vacuum_command_available(VACUUM_MODEL, "start", rows))
        # A reported error may project the UI to ERROR, but cannot make an
        # otherwise unknown vendor state safe for command routing.
        self.assertFalse(vacuum_command_available(
            VACUUM_MODEL, "start", observations(**{"2.1": 999, "2.2": 1})))
        for coordinate in ("2.1", "4.1", "4.7"):
            for value in (None, True, float("inf"), 999):
                rows = observations(**{coordinate: value})
                with self.assertRaises(ValueError):
                    prepare_vacuum_command(VACUUM_MODEL, "start", observations=rows)
            for update in ({"last_code": -4001}, {"last_code": False}, {"last_reply_null": True}):
                rows = observations()
                rows[coordinate].update(update)
                self.assertFalse(vacuum_command_available(VACUUM_MODEL, "start", rows))
        with self.assertRaises(ValueError):
            prepare_vacuum_command(VACUUM_MODEL, "start", "unexpected", observations())

    def test_special_tasks_use_only_verified_basic_variants(self):
        paused_docking = observations(**{"2.1": 3, "4.1": 1, "4.7": 11})
        self.assertEqual(prepare_vacuum_command(VACUUM_MODEL, "start", observations=paused_docking)["action"],
                         {"siid": 3, "aiid": 1, "in": []})
        mapping = observations(**{"2.1": 11, "4.1": 21, "4.7": 5})
        with self.assertRaises(ValueError):
            prepare_vacuum_command(VACUUM_MODEL, "start", observations=mapping)
        self.assertEqual(prepare_vacuum_command(VACUUM_MODEL, "stop", observations=mapping)["action"]["siid"], 3)
        for rows in (observations(**{"2.1": 3, "4.7": 1, "4.25": 3}),
                     observations(**{"2.1": 99, "4.7": 21}),
                     observations(**{"4.60": 1}), observations(**{"4.1": 15})):
            with self.assertRaises(ValueError):
                prepare_vacuum_command(VACUUM_MODEL, "start", observations=rows)
        for command, values in (("pause", {"2.1": 9}), ("stop", {"2.1": 8})):
            with self.assertRaises(ValueError):
                prepare_vacuum_command(VACUUM_MODEL, command, observations=observations(**values))

    def test_active_fan_guards_and_required_coordinates(self):
        running = observations(**{"2.1": 1, "4.1": 2, "4.7": 1})
        self.assertTrue(vacuum_command_available(VACUUM_MODEL, "set_fan_speed", running))
        self.assertEqual(vacuum_required_coordinates(VACUUM_MODEL, "set_fan_speed", running),
                         ("2.1", "4.1", "4.7", "4.4", "4.50", "4.26", "4.47"))
        for changed in ({"4.26": 1}, {"4.47": 1}, {"4.47": 2}, {"4.47": 4},
                        {"4.47": -1}, {"4.47": 999},
                        {"4.50": '{"k":"SuctionMax","v":0}'},
                        {"4.50": '[{"k":"SuctionMax","v":0},{"k":"SmartHost","v":1}]'},
                        {"2.1": 7}):
            rows = deepcopy(running)
            for key, value in changed.items(): rows[key]["value"] = value
            self.assertFalse(vacuum_command_available(VACUUM_MODEL, "set_fan_speed", rows))
        running["4.26"]["value"] = 1
        running["4.7"]["value"] = 2
        self.assertTrue(vacuum_command_available(VACUUM_MODEL, "set_fan_speed", running))


class StateProjectionTests(unittest.TestCase):
    def test_observed_states_dock_refinement_warnings_and_unknowns(self):
        expected = {1: "cleaning", 2: "idle", 3: "paused", 4: "error", 5: "returning",
                    6: "docked", 7: "cleaning", 12: "cleaning", 13: "docked", 0: "docked",
                    22: "docked", 24: "docked"}  # exact-model NEW_STATE: 22 is auto-empty.
        for code, activity in expected.items():
            self.assertEqual(vacuum_state(VACUUM_MODEL, observations(**{"2.1": code}))["activity"], activity)
        self.assertEqual(vacuum_state(VACUUM_MODEL, observations(**{"3.2": 3}))["activity"], "docked")
        self.assertEqual(vacuum_state(VACUUM_MODEL, observations(**{"4.7": 6}))["activity"], "paused")
        self.assertEqual(vacuum_state(VACUUM_MODEL, observations(**{"2.2": 1}))["activity"], "error")
        self.assertEqual(vacuum_state(VACUUM_MODEL, observations(**{"2.2": 47}))["activity"], "idle")
        unknown = vacuum_state(VACUUM_MODEL, observations(**{"2.1": 999, "4.4": 99}))
        self.assertIsNone(unknown["activity"])
        self.assertEqual(unknown["state_code"], 999)
        self.assertIsNone(unknown["fan_speed"])

    def test_battery_and_fan_do_not_manufacture_invalid_numeric_values(self):
        for value in (0, 100, 50.5):
            self.assertEqual(vacuum_state(VACUUM_MODEL, observations(**{"3.1": value}))["battery_level"], value)
        for value in (None, True, "75", -1, 101, 10**1000, float("nan"), float("inf"), [], {}):
            self.assertIsNone(vacuum_state(VACUUM_MODEL, observations(**{"3.1": value}))["battery_level"])
        for value in (True, "1", 1.0, -1, 4, None, float("inf")):
            self.assertIsNone(vacuum_state(VACUUM_MODEL, observations(**{"4.4": value}))["fan_speed"])
        store = ObservationStore(VACUUM_MODEL)
        store.merge_properties([{"siid": 2, "piid": 1, "value": 6}, {"siid": 3, "piid": 1, "value": 75}])
        self.assertEqual(vacuum_state(VACUUM_MODEL, store.snapshot())["activity"], "docked")


class Features(IntFlag):
    STATE = 1
    START = 2
    PAUSE = 4
    STOP = 8
    RETURN_HOME = 16
    FAN_SPEED = 32


class Activity(StrEnum):
    CLEANING = "cleaning"
    IDLE = "idle"
    PAUSED = "paused"
    DOCKED = "docked"
    RETURNING = "returning"
    ERROR = "error"


def vacuum_scope():
    scope = entity_scope()
    scope.update(StateVacuumEntity=type("StateVacuumEntity", (), {}), VacuumActivity=Activity,
                 VacuumEntityFeature=Features, vacuum_command_available=vacuum_command_available,
                 vacuum_control_supported=vacuum_control_supported, vacuum_state=vacuum_state)
    tree = ast.parse((COMPONENT / "vacuum.py").read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, "vacuum.py", "exec"), scope)
    return scope


class NativeVacuumBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope = vacuum_scope()
        store = ObservationStore(VACUUM_MODEL)
        store.properties.update(observations())
        self.state = SimpleNamespace(device=SimpleNamespace(model=VACUUM_MODEL), store=store,
                                     present=True, online=True, subscription=None)
        self.listeners, self.unload, self.added = [], [], []
        self.coordinator = SimpleNamespace(devices={"synthetic-device": self.state}, stopped=False,
            entity_discovery_suspended=False, last_update_success=True, device_key=lambda _: "synthetic-key",
            control_ready=lambda did: True, control_observations=lambda did: self.state.store.properties,
            async_add_listener=lambda fn: self.listeners.append(fn) or (lambda: self.listeners.remove(fn)),
            async_execute_vacuum=AsyncMock())
        self.entry = SimpleNamespace(runtime_data=self.coordinator, async_on_unload=self.unload.append)

    async def test_discovery_is_exact_dynamic_and_unregisters_its_listener(self):
        await self.scope["async_setup_entry"](None, self.entry, self.added.extend)
        self.assertEqual(len(self.added), 1)
        self.assertEqual(self.added[0]._attr_unique_id, "synthetic-key:vacuum")
        self.coordinator.devices["laundry"] = SimpleNamespace(device=SimpleNamespace(model="dreame.washer.l9nacn"), present=True)
        self.listeners[0]()
        self.assertEqual(len(self.added), 1)
        self.coordinator.entity_discovery_suspended = True
        self.coordinator.devices["later-vacuum"] = self.state
        self.listeners[0]()
        self.assertEqual(len(self.added), 1)
        self.coordinator.entity_discovery_suspended = False
        self.listeners[0]()
        self.assertEqual(len(self.added), 2)
        self.coordinator.stopped = True
        self.coordinator.devices["stopped-vacuum"] = self.state
        self.listeners[0]()
        self.assertEqual(len(self.added), 2)
        self.unload[0]()
        self.assertEqual(self.listeners, [])

    async def test_current_activity_features_and_availability_follow_memory(self):
        entity = self.scope["DreameVacuum"](self.coordinator, "synthetic-device")
        self.assertEqual(entity.activity, Activity.IDLE)
        self.assertTrue(entity.available)
        self.assertEqual(entity.fan_speed, "standard")
        self.assertIn(Features.FAN_SPEED, entity.supported_features)
        self.assertEqual(entity.extra_state_attributes["battery_level"], 75)
        self.coordinator.control_ready = lambda did: False
        self.assertEqual(entity.supported_features, Features.STATE)
        self.assertEqual(entity.fan_speed_list, [])
        self.assertTrue(entity.available)
        self.state.online = False
        self.assertFalse(entity.available)
        self.state.online = True
        self.coordinator.stopped = True
        self.assertFalse(entity.available)
        self.coordinator.stopped = False
        self.state.device.model = "dreame.vacuum.other"
        self.assertFalse(entity.available)
        self.assertIsNone(entity.activity)

    async def test_services_delegate_once_and_never_predict_state(self):
        entity = self.scope["DreameVacuum"](self.coordinator, "synthetic-device")
        original = deepcopy(self.state.store.properties)
        await entity.async_start()
        await entity.async_pause()
        await entity.async_stop()
        await entity.async_return_to_base()
        await entity.async_set_fan_speed("turbo")
        self.assertEqual([call.args for call in self.coordinator.async_execute_vacuum.await_args_list], [
            ("synthetic-device", "start"), ("synthetic-device", "pause"), ("synthetic-device", "stop"),
            ("synthetic-device", "return_to_base"), ("synthetic-device", "set_fan_speed", "turbo")])
        self.assertEqual(self.state.store.properties, original)
        self.coordinator.async_execute_vacuum.side_effect = RuntimeError("Synthetic rejection")
        with self.assertRaises(RuntimeError):
            await entity.async_start()
        self.assertEqual(self.coordinator.async_execute_vacuum.await_count, 6)

    async def test_foreign_status_or_task_never_inherits_commands_from_docked_activity(self):
        entity = self.scope["DreameVacuum"](self.coordinator, "synthetic-device")
        self.state.store.properties["2.1"]["value"] = 6
        self.assertEqual(entity.activity, Activity.DOCKED)
        self.assertIn(Features.START, entity.supported_features)
        for coordinate in ("4.1", "4.7"):
            original = self.state.store.properties[coordinate]["value"]
            self.state.store.properties[coordinate]["value"] = 999
            self.assertEqual(entity.activity, Activity.DOCKED)
            self.assertEqual(entity.supported_features, Features.STATE)
            for command in ("start", "pause", "stop", "return_to_base"):
                with self.assertRaises(ValueError):
                    prepare_vacuum_command(VACUUM_MODEL, command, observations=self.state.store.properties)
            self.state.store.properties[coordinate]["value"] = original
            self.assertIn(Features.START, entity.supported_features)
        self.coordinator.control_observations = lambda did: {}
        self.assertEqual(entity.supported_features, Features.STATE)
        self.coordinator.control_observations = lambda did: self.state.store.properties
        self.assertIn(Features.START, entity.supported_features)


if __name__ == "__main__":
    unittest.main()
