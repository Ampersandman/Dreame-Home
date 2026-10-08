"""Isolated HA control boundaries; these tests do not run Home Assistant."""

import ast
from collections import Counter
import copy
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from urllib.parse import quote

from dreamehome.laundry_programs import program_catalog, program_option_pairs
from dreamehome.presentation import control_presentation

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_home"
MODEL = "dreame.washer.l9nacn"


class ValidationError(Exception):
    pass


class StubCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class StubPlatformEntity:
    pass


def load_scope(name, scope, *, only_class=None):
    module = ast.parse((COMPONENT / name).read_text(encoding="utf-8"))
    module.body = [node for node in module.body
                   if not isinstance(node, (ast.Import, ast.ImportFrom))
                   and (only_class is None or isinstance(node, ast.ClassDef) and node.name == only_class)]
    exec(compile(module, name, "exec"), scope)


def definition(key, kind, coordinate=None, **fields):
    return {"key": key, "kind": kind, "coordinate": coordinate, "label": key.title(), **fields}


class ControlBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.definitions = [
            definition("child_lock", "switch", "3.4"),
            definition("program", "select", "2.3", options=[
                {"value": 3, "label": "Wool"}, {"value": 17, "label": "Wool"},
                {"value": 6, "label": "Shirts"}]),
            definition("start", "button"),
            definition("delay", "number", "2.19", min=0, max=120, step=10, unit="min"),
        ]
        self.rows = {
            "2.1": {"value": 0, "last_code": 0},
            "2.3": {"value": 3, "last_code": 0},
            "3.4": {"value": 0, "last_code": 0},
            "2.19": {"value": 20, "last_code": 0},
        }
        self.state = SimpleNamespace(
            device=SimpleNamespace(model=MODEL, name="Laundry", raw={}), present=True, online=True,
            store=SimpleNamespace(properties=self.rows), subscription=None,
        )
        self.listeners, self.removers, self.added = [], [], []
        self.busy = False
        self.fresh = True
        self.coordinator = SimpleNamespace(
            devices={"device": self.state}, stopped=False, entity_discovery_suspended=False,
            last_update_success=True, device_key=lambda state: "device-key",
            async_execute_control=AsyncMock(),
        )
        self.coordinator.control_ready = lambda did: (
            not self.coordinator.stopped and not self.coordinator.entity_discovery_suspended
            and self.coordinator.last_update_success and not self.busy
            and self.coordinator.devices[did].present and self.coordinator.devices[did].online is True)
        self.coordinator.control_observations = lambda did: self.rows if self.fresh else {}

        def listen(listener):
            self.listeners.append(listener)
            return lambda: self.listeners.remove(listener)

        self.coordinator.async_add_listener = listen
        self.entry = SimpleNamespace(runtime_data=self.coordinator, async_on_unload=self.removers.append)
        self.scope = {
            "Counter": Counter, "quote": quote, "math": math, "callback": lambda function: function,
            "ServiceValidationError": ValidationError,
            "EntityCategory": SimpleNamespace(CONFIG="config"),
            "CoordinatorEntity": StubCoordinatorEntity,
            "control_definitions": lambda model: copy.deepcopy(self.definitions) if model == MODEL else [],
            "control_available": self.control_available,
            "control_options": self.control_options,
            "prepare_control_write": self.prepare_control_write,
            "SwitchEntity": StubPlatformEntity, "SelectEntity": StubPlatformEntity,
            "NumberEntity": StubPlatformEntity, "ButtonEntity": StubPlatformEntity,
            "NumberMode": SimpleNamespace(BOX="box"),
            "program_catalog": program_catalog, "program_option_pairs": program_option_pairs,
            "control_presentation": control_presentation,
            "presentation_language": lambda coordinator: getattr(getattr(getattr(coordinator, "hass", None), "config", None), "language", "en"),
        }
        load_scope("entity.py", self.scope, only_class="DreameEntity")
        load_scope("control.py", self.scope)
        for platform in ("switch", "select", "number", "button"):
            load_scope(f"{platform}.py", self.scope)

    def get_definition(self, key):
        return next(item for item in self.definitions if item["key"] == key)

    def valid_row(self, observations, coordinate):
        row = observations.get(coordinate, {})
        code = row.get("last_code")
        return (type(row.get("value")) is int
                and (code is None or type(code) is int and code == 0 or type(code) is str and code == "0")
                and not row.get("last_reply_null"))

    def control_available(self, model, key, observations):
        if model != MODEL or not self.valid_row(observations, "2.1"):
            return False
        descriptor = self.get_definition(key)
        coordinate = descriptor.get("coordinate")
        if coordinate and not self.valid_row(observations, coordinate):
            return False
        if descriptor["kind"] == "select":
            return any(option["value"] == observations[coordinate]["value"]
                       for option in descriptor["options"])
        return observations["2.1"]["value"] == 0

    def control_options(self, model, key, observations):
        return copy.deepcopy(self.get_definition(key).get("options", [])) if self.control_available(model, key, observations) else []

    def prepare_control_write(self, model, key, value, observations):
        if not self.control_available(model, key, observations):
            raise ValueError("Missing context")
        kind = self.get_definition(key)["kind"]
        if kind == "switch" and type(value) is not bool:
            raise ValueError("Switch requires Boolean input")
        if kind == "select" and (type(value) is not int or value not in
                                  {option["value"] for option in self.control_options(model, key, observations)}):
            raise ValueError("Unknown selection")
        if kind == "button" and value is not None:
            raise ValueError("Button takes no value")
        return {"method": "validated-fixture-command"}

    def entity(self, key, class_name):
        return self.scope[class_name](self.coordinator, "device", copy.deepcopy(self.get_definition(key)))

    async def test_switch_explicit_command_preserves_observed_state(self):
        entity = self.entity("child_lock", "DreameLaundrySwitch")
        before = copy.deepcopy(self.rows)
        self.assertTrue(entity.available)
        self.assertFalse(entity.is_on)
        self.coordinator.async_execute_control.assert_not_called()
        await entity.async_turn_on()
        self.coordinator.async_execute_control.assert_awaited_once_with("device", "child_lock", True)
        self.assertEqual(self.rows, before)
        self.assertFalse(entity.is_on)
        self.rows["3.4"]["value"] = 1
        self.assertTrue(entity.is_on)

    async def test_stale_offline_failed_api_busy_and_unload_block_commands(self):
        entity = self.entity("child_lock", "DreameLaundrySwitch")
        for obj, field in ((self, "fresh"), (self.state, "online"),
                           (self.coordinator, "last_update_success"), (self.state, "present")):
            with self.subTest(field=field):
                setattr(obj, field, False)
                self.assertFalse(entity.available)
                with self.assertRaises(ValidationError):
                    await entity.async_turn_on()
                setattr(obj, field, True)
        for field in ("stopped", "entity_discovery_suspended"):
            setattr(self.coordinator, field, True)
            with self.assertRaises(ValidationError):
                await entity.async_turn_on()
            setattr(self.coordinator, field, False)
        self.busy = True
        with self.assertRaises(ValidationError):
            await entity.async_turn_on()
        self.coordinator.async_execute_control.assert_not_called()

    async def test_switch_wrong_types_null_failed_and_latest_null_are_unavailable(self):
        entity = self.entity("child_lock", "DreameLaundrySwitch")
        for value in (True, "1", 1.0, 2, None):
            with self.subTest(value=value):
                self.rows["3.4"]["value"] = value
                self.assertIsNone(entity.is_on)
                self.assertFalse(entity.available)
        self.rows["3.4"] = {"value": 1, "last_code": -1}
        self.assertIsNone(entity.is_on)
        self.assertFalse(entity.available)
        self.rows["3.4"]["last_code"] = False
        self.assertIsNone(entity.is_on)
        self.assertFalse(entity.available)
        self.rows["3.4"] = {"value": 1, "last_code": 0, "last_reply_null": True}
        self.assertTrue(entity.is_on)  # Retain readback, but reject a new command.
        self.assertFalse(entity.available)
        with self.assertRaises(ValidationError):
            await entity.async_turn_off()

    async def test_select_duplicate_names_map_to_distinct_exact_codes(self):
        entity = self.entity("program", "DreameLaundrySelect")
        self.assertEqual(entity.options, ["Wool (3)", "Wool (17)", "Shirts"])
        self.assertEqual(entity.current_option, "Wool (3)")
        before = copy.deepcopy(self.rows)
        await entity.async_select_option("Wool (17)")
        self.coordinator.async_execute_control.assert_awaited_once_with("device", "program", 17)
        self.assertEqual(self.rows, before)
        self.assertEqual(entity.current_option, "Wool (3)")
        for invalid in ("Wool", "17", 17, True):
            with self.assertRaises(ValidationError):
                await entity.async_select_option(invalid)
        self.assertEqual(self.coordinator.async_execute_control.await_count, 1)

    async def test_select_unknown_typed_or_duplicate_codes_fail_closed(self):
        entity = self.entity("program", "DreameLaundrySelect")
        for value in (True, 3.0, "3", 999, None):
            self.rows["2.3"]["value"] = value
            self.assertIsNone(entity.current_option)
            self.assertFalse(entity.available)
        self.rows["2.3"]["value"] = 3
        entity.definition["options"].append({"value": 3, "label": "Other"})
        self.assertEqual(entity.options, [])
        self.assertIsNone(entity.current_option)
        with self.assertRaises(ValidationError):
            await entity.async_select_option("Other")
        self.coordinator.async_execute_control.assert_not_called()

    async def test_select_filtered_duplicate_label_keeps_stable_suffix(self):
        entity = self.entity("program", "DreameLaundrySelect")
        self.scope["control_options"] = lambda *args: [{"value": 3, "label": "Wool"}]
        self.assertEqual(entity.options, ["Wool (3)"])
        self.assertEqual(entity.current_option, "Wool (3)")
        with self.assertRaises(ValidationError):
            await entity.async_select_option("Wool (17)")

    async def test_filtered_current_code_can_be_replaced_with_an_allowed_choice(self):
        entity = self.entity("program", "DreameLaundrySelect")
        self.scope["control_options"] = lambda *args: [{"value": 17, "label": "Wool"}]
        self.assertEqual(entity.options, ["Wool (17)"])
        self.assertEqual(entity.current_option, "Wool (3)")
        self.assertTrue(entity.available)
        with self.assertRaises(ValidationError):
            await entity.async_select_option("Wool (3)")
        await entity.async_select_option("Wool (17)")
        self.coordinator.async_execute_control.assert_awaited_once_with("device", "program", 17)

    async def test_buttons_never_submit_on_setup_or_availability(self):
        entity = self.entity("start", "DreameLaundryButton")
        self.assertTrue(entity.available)
        self.coordinator.async_execute_control.assert_not_called()
        await entity.async_press()
        self.coordinator.async_execute_control.assert_awaited_once_with("device", "start", None)
        self.fresh = False
        self.assertFalse(entity.available)
        with self.assertRaises(ValidationError):
            await entity.async_press()
        self.assertEqual(self.coordinator.async_execute_control.await_count, 1)

    async def test_gateway_failure_propagates_once_without_state_changes(self):
        entity = self.entity("child_lock", "DreameLaundrySwitch")
        before = copy.deepcopy(self.rows)
        error = RuntimeError("Fabricated command rejection")
        self.coordinator.async_execute_control.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            await entity.async_turn_on()
        self.assertIs(caught.exception, error)
        self.coordinator.async_execute_control.assert_awaited_once()
        self.assertEqual(self.rows, before)

    async def test_real_encoder_and_descriptors_accept_only_explicit_known_commands(self):
        from dreamehome.laundry_controls import (
            control_available, control_definitions, control_options, prepare_control_write,
        )

        self.definitions = control_definitions(MODEL)
        self.scope.update(control_available=control_available, control_definitions=control_definitions,
                          control_options=control_options, prepare_control_write=prepare_control_write)
        self.rows.update({"2.1": {"value": 1, "last_code": 0},
                          "2.3": {"value": 0, "last_code": 0},
                          "3.4": {"value": 0, "last_code": None}})
        entity = self.entity("child_lock", "DreameLaundrySwitch")
        self.assertTrue(entity.available)
        self.assertFalse(entity.is_on)
        await entity.async_turn_on()
        self.coordinator.async_execute_control.assert_awaited_once_with("device", "child_lock", True)
        select = self.entity("program", "DreameLaundrySelect")
        target = next(label for label, code in select.selectable_pairs() if code == 22)
        await select.async_select_option(target)
        self.coordinator.async_execute_control.assert_awaited_with("device", "program", 22)
        self.assertEqual(self.rows["2.3"]["value"], 0)
        self.assertEqual(self.rows["3.4"]["value"], 0)
        self.rows["3.4"]["last_reply_null"] = True
        with self.assertRaises(ValidationError):
            await entity.async_turn_off()
        self.assertEqual(self.coordinator.async_execute_control.await_count, 2)

    async def test_german_ha_uses_english_program_names_and_preserves_wire_identity(self):
        from dreamehome.laundry_controls import control_available, control_definitions, control_options, prepare_control_write
        self.definitions = control_definitions(MODEL)
        self.scope.update(control_available=control_available, control_definitions=control_definitions,
                          control_options=control_options, prepare_control_write=prepare_control_write)
        self.coordinator.hass = SimpleNamespace(config=SimpleNamespace(language="de-DE"))
        self.rows.update({"2.1": {"value": 1, "last_code": 0}, "2.3": {"value": 0, "last_code": 0}})
        entity = self.entity("program", "DreameLaundrySelect")
        self.assertEqual(entity._attr_name, "Selected program")
        self.assertIsNone(entity._attr_entity_category)
        self.assertEqual(entity.current_option, "AI Wash")
        self.assertEqual(len(entity.options), 15)
        self.assertIn("Quick Wash", entity.options)
        self.assertIn("Underwear", entity.options)
        self.assertNotIn("Silk", entity.options)
        attributes = entity.extra_state_attributes
        self.assertEqual(attributes["control_key"], "program")
        self.assertEqual(attributes["raw_code"], 0)
        self.assertEqual(len(attributes["program_catalog"]), 15)
        for row in attributes["program_catalog"]:
            self.assertIn(row["option"], entity.options)
            self.assertTrue(row["selectable"])
            self.assertNotIn("provenance", row)
            self.assertNotIn("source", row)
            self.assertNotIn("source_label", row)
            self.assertEqual(set(row["labels"]), {"en"})
            self.assertEqual(set(row["group_labels"]), {"en"})
        with self.assertRaises(ValidationError):
            await entity.async_select_option("Schnellwäsche")
        await entity.async_select_option("Quick Wash")
        self.coordinator.async_execute_control.assert_awaited_once_with("device", "program", 1)
        self.assertEqual(self.rows["2.3"]["value"], 0)
        self.fresh = False
        self.assertFalse(entity.available)
        self.assertFalse(any(row["selectable"] for row in entity.extra_state_attributes["program_catalog"]))

    async def test_app_name_corrections_submit_exact_original_codes(self):
        from dreamehome.laundry_controls import control_available, control_definitions, control_options, prepare_control_write
        self.scope.update(control_available=control_available, control_definitions=control_definitions,
                          control_options=control_options, prepare_control_write=prepare_control_write)
        self.coordinator.hass = SimpleNamespace(config=SimpleNamespace(language="de-DE"))
        for model, current, label, expected in ((MODEL, 0, "Underwear", 8),
                                               ("dreame.dryer.l9nacn", 7, "Baby Care", 7),
                                               ("dreame.dryer.l9nacn", 7, "Underwear", 8)):
            with self.subTest(model=model, label=label):
                self.state.device.model = model
                self.definitions = control_definitions(model)
                self.rows.update({"2.1": {"value": 1, "last_code": 0},
                                  "2.3": {"value": current, "last_code": 0},
                                  "3.4": {"value": 0, "last_code": 0}})
                entity = self.entity("program", "DreameLaundrySelect")
                self.assertIn(label, entity.options)
                old_label = "Towels" if expected == 7 else "Delicates"
                with self.assertRaises(ValidationError):
                    await entity.async_select_option(old_label)
                before = copy.deepcopy(self.rows)
                await entity.async_select_option(label)
                self.coordinator.async_execute_control.assert_awaited_with("device", "program", expected)
                self.assertEqual(self.rows, before)
                raw = prepare_control_write(model, "program", expected, self.rows)
                self.assertEqual(raw["properties"], [{"siid": 2, "piid": 3, "value": expected}])

    async def test_control_categories_keys_and_ids_remain_stable(self):
        from dreamehome.laundry_controls import control_definitions
        self.definitions = control_definitions(MODEL)
        for key, class_name, category in (("program", "DreameLaundrySelect", None),
                                         ("temperature", "DreameLaundrySelect", None),
                                         ("fresh_air_circulation", "DreameLaundrySwitch", None),
                                         ("child_lock", "DreameLaundrySwitch", None),
                                         ("night_mode", "DreameLaundrySwitch", None),
                                         ("start", "DreameLaundryButton", None)):
            entity = self.entity(key, class_name)
            self.assertEqual(entity._attr_entity_category, category)
            self.assertEqual(entity.extra_state_attributes["control_key"], key)
            self.assertIn(f":control:{self.get_definition(key)['kind']}:{key}", entity._attr_unique_id)
        self.coordinator.async_execute_control.assert_not_called()

    async def test_bounded_number_rejects_invalid_values_without_coercing_boolean(self):
        entity = self.entity("delay", "DreameLaundryNumber")
        self.assertEqual(entity.native_value, 20)
        before = copy.deepcopy(self.rows)
        for value in (True, "30", None, float("nan"), float("inf"), -10, 130, 25):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                await entity.async_set_native_value(value)
        self.coordinator.async_execute_control.assert_not_called()
        await entity.async_set_native_value(30.0)
        self.coordinator.async_execute_control.assert_awaited_once_with("device", "delay", 30.0)
        self.assertEqual(self.rows, before)
        self.assertEqual(entity.native_value, 20)

    async def test_number_factory_omits_incomplete_or_invalid_ranges(self):
        for extra in ({}, {"min": 0, "max": 10}, {"min": 0, "max": 10, "step": 0},
                      {"min": 10, "max": 0, "step": 1}, {"min": 0, "max": 10, "step": True}):
            self.assertIsNone(self.scope["number_factory"](
                self.coordinator, "device", definition("unsafe", "number", "2.19", **extra)))

    async def test_discovery_is_stable_dynamic_and_suspended_during_unload(self):
        register = self.scope["add_control_entities"]
        factory = self.scope["DreameLaundrySwitch"]
        register(self.coordinator, self.entry, self.added.extend, factory, kind="switch")
        self.assertEqual(len(self.added), 1)
        self.assertEqual(self.added[0]._attr_unique_id, "device-key:control:switch:child_lock")
        self.assertIsNone(self.added[0]._attr_entity_category)
        self.listeners[0]()
        self.assertEqual(len(self.added), 1)
        second = copy.deepcopy(self.state)
        second.device.model = "dreame.vacuum.r5023a"
        self.coordinator.devices["vacuum"] = second
        self.listeners[0]()
        self.assertEqual(len(self.added), 1)
        second.device.model = MODEL
        self.coordinator.entity_discovery_suspended = True
        self.listeners[0]()
        self.assertEqual(len(self.added), 1)
        self.coordinator.entity_discovery_suspended = False
        self.listeners[0]()
        self.assertEqual(len(self.added), 2)
        self.removers[0]()
        self.assertEqual(self.listeners, [])
        self.coordinator.async_execute_control.assert_not_called()


class ExactControlDescriptorTests(unittest.TestCase):
    def test_exact_model_descriptors_have_safe_unique_entity_definitions(self):
        from dreamehome.laundry_controls import control_definitions

        self.assertEqual(list(control_definitions("dreame.vacuum.r5023a")), [])
        self.assertEqual(list(control_definitions("dreame.washer.l9nacn.extra")), [])
        scope = {"Counter": Counter}
        module = ast.parse((COMPONENT / "control.py").read_text(encoding="utf-8"))
        function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "option_pairs")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "control.py", "exec"), scope)
        for model in ("dreame.washer.l9nacn", "dreame.dryer.l9nacn"):
            definitions = control_definitions(model)
            self.assertTrue(definitions)
            self.assertEqual(len({item["key"] for item in definitions}), len(definitions))
            self.assertFalse(any(item["kind"] == "number" for item in definitions))
            self.assertEqual({item["key"] for item in definitions if item["kind"] == "button"},
                             {"start", "pause", "stop"})
            for item in definitions:
                with self.subTest(model=model, key=item["key"]):
                    self.assertTrue(item["label"])
                    if item["kind"] in ("switch", "select"):
                        self.assertRegex(item["coordinate"], r"^\d+\.\d+$")
                    if item["kind"] == "select":
                        self.assertEqual(len(scope["option_pairs"](item["options"])), len(item["options"]))


if __name__ == "__main__":
    unittest.main()
