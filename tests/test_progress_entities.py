"""Test source-backed telemetry and derived HA boundaries without an HA runtime."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from dreamehome.laundry import enum_label
from dreamehome.laundry_controls import control_available, control_definitions
from dreamehome.laundry_progress import laundry_cycle_metrics, progress_definitions
from dreamehome.observations import ObservationStore
from dreamehome.vacuum_controls import vacuum_command_available, vacuum_control_supported
from dreamehome.vacuum_telemetry import vacuum_telemetry_available
from dreamehome.presentation import cycle_presentation
from test_entity_lifecycle import entity_scope

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_home"
WASHER, DRYER, VACUUM = "dreame.washer.l9nacn", "dreame.dryer.l9nacn", "dreame.vacuum.r5023a"


def scope():
    namespace = entity_scope()
    class Sensor:
        @property
        def device_class(self):
            return getattr(self, "_attr_device_class", None)
    import math
    namespace.update(SensorEntity=Sensor, SensorDeviceClass=SimpleNamespace(BATTERY="battery", DURATION="duration", AREA="area"),
                     SensorStateClass=SimpleNamespace(MEASUREMENT="measurement"), math=math,
                     enum_label=enum_label, laundry_cycle_metrics=laundry_cycle_metrics,
                     vacuum_telemetry_available=vacuum_telemetry_available,
                     progress_definitions=progress_definitions, cycle_presentation=cycle_presentation,
                     PERCENTAGE="%", monotonic=lambda: 1200)
    tree = ast.parse((COMPONENT / "sensor.py").read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, "sensor.py", "exec"), namespace)
    return namespace


def state(model):
    values = {"2.1": 3, "2.3": 2 if model == WASHER else 0, "2.4": 1 if model == WASHER else 3,
              "3.4": 0, "3.14": 0, "2.2": 0}
    values.update({"2.12": 60, "2.13": 15} if model == WASHER else {"2.9": 60, "2.11": 15})
    store = ObservationStore(model)
    store.merge_properties([{"siid": int(key.split(".")[0]), "piid": int(key.split(".")[1]),
                             "value": value, "code": 0} for key, value in values.items()], source="mqtt")
    return SimpleNamespace(device=SimpleNamespace(model=model, did="fabricated-device"), store=store,
                           timestamps={key: 1200 for key in values}, present=True, online=True,
                           subscription=None, read_error=None)


def coordinator(item):
    listeners = []
    return SimpleNamespace(devices={"fabricated-device": item}, device_key=lambda _: "fabricated-key",
                           last_update_success=True, stopped=False, entity_discovery_suspended=False,
                           async_add_listener=lambda listener: listeners.append(listener) or (lambda: listeners.remove(listener)),
                           listeners=listeners)


class ProgressEntityTests(unittest.TestCase):
    def test_active_paused_and_completed_values_have_stable_ids(self):
        namespace = scope()
        for model in (WASHER, DRYER):
            item = state(model)
            account = coordinator(item)
            definitions = progress_definitions(model)
            entities = {definition["key"]: namespace["DreameCycleSensor"](account, item.device.did, definition)
                        for definition in definitions}
            self.assertEqual(entities["progress"].native_value, 75)
            self.assertEqual(entities["elapsed_time"].native_value, 45)
            self.assertTrue(entities["progress"].available)
            self.assertEqual(entities["progress"]._attr_native_unit_of_measurement, "%")
            self.assertEqual(entities["elapsed_time"].device_class, "duration")
            self.assertTrue(entities["progress"].extra_state_attributes["derived"])
            identity = entities["progress"]._attr_unique_id
            item.store.merge_properties([{"siid": 2, "piid": 1, "value": 2}], source="mqtt")
            self.assertEqual(entities["progress"].native_value, 75)
            self.assertEqual(entities["progress"]._attr_unique_id, identity)
            item.store.merge_properties([{"siid": 2, "piid": 1, "value": 0},
                                         {"siid": 2, "piid": 4, "value": 6 if model == WASHER else 2}], source="mqtt")
            self.assertIsNone(entities["progress"].native_value)
            self.assertFalse(entities["progress"].available)

    def test_stale_cached_null_failed_and_value_less_rows_do_not_make_progress(self):
        namespace = scope()
        for mutation in (lambda item: item.timestamps.update({"2.1": 1019}),
                         lambda item: item.store.properties["2.1"].update(last_source="listing"),
                         lambda item: item.store.properties["2.1"].update(last_reply_null=True),
                         lambda item: item.store.properties["2.1"].update(last_code=-1),
                         lambda item: item.store.properties["2.1"].update(last_code=False),
                         lambda item: item.store.properties["2.1"].update(last_item={"code": 0}),
                         lambda item: item.store.properties["2.12"].update(value=0)):
            item = state(WASHER)
            entity = namespace["DreameCycleSensor"](coordinator(item), item.device.did, progress_definitions(WASHER)[0])
            mutation(item)
            self.assertIsNone(entity.native_value)
            self.assertFalse(entity.available)

    def test_discovery_handles_later_models_and_stops_during_unload(self):
        namespace = scope()
        item = state(WASHER)
        account = coordinator(item)
        added, removals = [], []
        entry = SimpleNamespace(async_on_unload=removals.append)
        namespace["add_progress_entities"](account, entry, added.extend)
        self.assertEqual(len(added), 2)
        account.listeners[0]()
        self.assertEqual(len(added), 2)
        dryer = state(DRYER)
        account.devices["dryer"] = dryer
        account.entity_discovery_suspended = True
        account.listeners[0]()
        self.assertEqual(len(added), 2)
        account.entity_discovery_suspended = False
        account.listeners[0]()
        self.assertEqual(len(added), 4)
        account.stopped = True
        account.devices["unknown"] = state("dreame.washer.unverified")
        account.listeners[0]()
        self.assertEqual(len(added), 4)
        removals[0]()
        self.assertFalse(account.listeners)

    def test_duration_metadata_preserves_coordinate_identity_and_rejects_bad_values(self):
        namespace = scope()
        for model, coordinate, label in ((WASHER, "2.12", "Program duration"), (WASHER, "2.13", "Remaining time"),
                                         (DRYER, "2.9", "Program duration"), (DRYER, "2.11", "Remaining time")):
            item = state(model)
            entity = namespace["DreamePropertySensor"](coordinator(item), item.device.did, coordinate)
            self.assertEqual(entity._attr_name, label)
            self.assertEqual(entity.device_class, "duration")
            self.assertEqual(entity._attr_native_unit_of_measurement, "min")
            self.assertIn(f":prop:{coordinate}:state", entity._attr_unique_id)
            self.assertTrue(entity.available)
            for value in (-1, True, "5", {"remaining": 5}, float("inf")):
                item.store.merge_properties([{"siid": 2, "piid": int(coordinate.split(".")[1]), "value": value}])
                self.assertIsNone(entity.native_value)
                self.assertFalse(entity.available)
            # Unit metadata must not leak to unrelated fields or JSON leaves.
            unknown = namespace["property_definition"](model, "99.1")
            self.assertIsNone(unknown)
            leaf = namespace["property_definition"](model, coordinate, "/remaining")
            self.assertNotIn("unit", leaf)

        # The app renders --min for an unfinished AI Wash with raw remaining0.
        item = state(WASHER)
        item.store.merge_properties([{"siid": 2, "piid": 3, "value": 0},
                                     {"siid": 2, "piid": 13, "value": 0}], source="mqtt")
        remaining = namespace["DreamePropertySensor"](coordinator(item), item.device.did, "2.13")
        self.assertIsNone(remaining.native_value)
        item.store.merge_properties([{"siid": 2, "piid": 4, "value": 6}], source="mqtt")
        self.assertEqual(remaining.native_value, 0)

    def test_vacuum_observed_progress_time_and_area_have_exact_units_and_bounds(self):
        namespace = scope()
        item = state(VACUUM)
        values = {"2.1": 1, "4.1": 2, "4.7": 1, "4.25": 2,
                  "4.2": 45, "4.3": 18, "4.63": 40, "4.64": 60}
        for key, value in values.items():
            siid, piid = map(int, key.split("."))
            item.store.merge_properties([{"siid": siid, "piid": piid, "value": value}], source="rpc")
            item.timestamps[key] = 1200
        account = coordinator(item)
        for key, unit, label in (("4.2", "min", "Cleaning time"), ("4.3", "m²", "Cleaned area"),
                                  ("4.63", "%", "Cleaning progress"), ("4.64", "%", "Mop drying progress")):
            entity = namespace["DreamePropertySensor"](account, item.device.did, key)
            self.assertEqual(entity._attr_native_unit_of_measurement, unit)
            self.assertEqual(entity._attr_name, label)
            self.assertTrue(entity.available)
            if unit == "%":
                for value in (-1, 101, True):
                    item.store.properties[key]["value"] = value
                    self.assertFalse(entity.available)
                    self.assertIsNone(entity.native_value)

    def test_vacuum_progress_requires_fresh_live_context_and_reply(self):
        namespace = scope()
        item = state(VACUUM)
        values = {"2.1": 1, "4.1": 2, "4.7": 1, "4.25": 2,
                  "4.2": 45, "4.63": 40, "4.64": 60}
        for key, value in values.items():
            siid, piid = map(int, key.split("."))
            item.store.merge_properties([{"siid": siid, "piid": piid, "value": value}], source="rpc")
            item.timestamps[key] = 1200
        account = coordinator(item)
        progress = namespace["DreamePropertySensor"](account, item.device.did, "4.63")
        drying = namespace["DreamePropertySensor"](account, item.device.did, "4.64")
        history = namespace["DreamePropertySensor"](account, item.device.did, "4.2")
        self.assertTrue(progress.available)
        self.assertTrue(drying.available)
        item.timestamps["4.63"] = 1019
        self.assertFalse(progress.available)
        item.timestamps["4.63"] = 1200
        item.store.properties["4.63"]["last_reply_null"] = True
        self.assertFalse(progress.available)
        item.store.properties["4.63"]["last_reply_null"] = False
        item.timestamps["4.7"] = 1019
        self.assertFalse(progress.available)
        item.timestamps["4.7"] = 1200
        for key, value in (("2.1", 13), ("4.1", 6), ("4.7", 0), ("4.25", 0)):
            siid, piid = map(int, key.split("."))
            item.store.merge_properties([{"siid": siid, "piid": piid, "value": value}], source="rpc")
        self.assertFalse(progress.available)
        self.assertFalse(drying.available)
        self.assertTrue(history.available)

    def test_control_diagnostics_distinguish_support_and_fresh_eligibility(self):
        item = state(WASHER)
        namespace = scope()
        account = coordinator(item)
        account.control_observations = lambda did: namespace["fresh_observations"](item)
        account.control_ready = lambda did: True
        tree = ast.parse((COMPONENT / "diagnostics.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "control_diagnostics")
        scope_vars = {"control_available": control_available, "control_definitions": control_definitions,
                      "vacuum_control_supported": vacuum_control_supported, "vacuum_command_available": vacuum_command_available}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "diagnostics.py", "exec"), scope_vars)
        diagnostics = scope_vars["control_diagnostics"](account, item)
        self.assertEqual(len(diagnostics["supported_commands"]), 16)
        self.assertIn("pause", diagnostics["available_commands"])
        self.assertIn("stop", diagnostics["available_commands"])
        self.assertNotIn("start", diagnostics["available_commands"])
        self.assertNotIn(item.device.did, json.dumps(diagnostics))
        account.control_ready = lambda did: False
        self.assertFalse(scope_vars["control_diagnostics"](account, item)["available_commands"])


if __name__ == "__main__":
    unittest.main()
