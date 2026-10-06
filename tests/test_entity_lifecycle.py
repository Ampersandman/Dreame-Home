"""Isolated entity and MQTT lifetime boundaries; not an HA runtime test."""

import ast
import asyncio
import json
import math
from pathlib import Path
import threading
from time import monotonic
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

from dreamehome.exceptions import AuthenticationError, DreameError, RateLimitError
from dreamehome.laundry import enum_label, laundry_definition
from dreamehome.models import Device, Session
from dreamehome.mqtt import DeviceSubscription
from dreamehome.observations import ObservationStore, compound_fields, entity_fields
from dreamehome.privacy import SENSITIVE, redactor
from dreamehome.telemetry import telemetry_metadata

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_home"


class StubCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


def entity_scope():
    source = ast.parse((COMPONENT / "entity.py").read_text(encoding="utf-8"))
    source.body = [node for node in source.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    scope = {
        "math": math, "json": json, "Any": Any, "quote": quote, "callback": lambda f: f,
        "DeviceInfo": lambda **kwargs: kwargs, "EntityCategory": SimpleNamespace(DIAGNOSTIC="diagnostic"),
        "CoordinatorEntity": StubCoordinatorEntity, "compound_fields": compound_fields,
        "entity_fields": entity_fields, "SENSITIVE": SENSITIVE, "redactor": redactor, "DOMAIN": "dreame_home",
        "enum_label": enum_label, "laundry_definition": laundry_definition,
        "telemetry_metadata": telemetry_metadata, "monotonic": monotonic,
    }
    exec(compile(source, "entity.py", "exec"), scope)
    return scope


def coordinator_start(namespace):
    source = ast.parse((COMPONENT / "coordinator.py").read_text(encoding="utf-8"))
    owner = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "DreameCoordinator")
    function = next(node for node in owner.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_start_subscriptions")
    exec(compile(ast.Module(body=[function], type_ignores=[]), "coordinator.py", "exec"), namespace)
    return namespace[function.name]


def device_state():
    return SimpleNamespace(device=Device("device", "unknown.model", "Appliance"),
                           store=ObservationStore("unknown.model"), present=True, online=True,
                           read_error=None, cached_rows={}, subscription=None,
                           mqtt_error=None, mqtt_attempt=0)


class EntityIdentityTests(unittest.TestCase):
    def setUp(self):
        self.scope = entity_scope()
        self.state = device_state()
        self.listeners, self.added = [], []
        self.coordinator = SimpleNamespace(
            devices={"device": self.state}, entity_platforms={}, last_update_success=True,
            device_key=lambda state: "device-key",
            async_add_listener=lambda listener: self.listeners.append(listener) or (lambda: None),
        )
        self.entry = SimpleNamespace(async_on_unload=lambda callback: None)

    def register_both_platforms(self):
        base = self.scope["DreamePropertyEntity"]
        sensor = type("Sensor", (base,), {"_expected_boolean": False})
        binary = type("Binary", (base,), {"_expected_boolean": True})
        register = self.scope["add_observed_entities"]
        for boolean, factory in ((False, sensor), (True, binary)):
            register(self.coordinator, self.entry, self.added.extend, factory, boolean=boolean)

    def test_boolean_to_number_does_not_create_a_second_platform(self):
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": True}])
        self.register_both_platforms()
        self.assertEqual(len(self.added), 1)
        original = self.added[0]
        self.assertTrue(original.available)
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": 2}])
        for listener in self.listeners:
            listener()
        self.assertEqual(len(self.added), 1)
        self.assertFalse(original.available)

    def test_number_to_boolean_is_unavailable_on_its_original_platform(self):
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": 2}])
        self.register_both_platforms()
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": False}])
        for listener in self.listeners:
            listener()
        self.assertEqual(len(self.added), 1)
        self.assertFalse(self.added[0].available)

    def test_null_does_not_freeze_platform_before_a_real_observation(self):
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": None}])
        self.register_both_platforms()
        self.assertEqual(self.added, [])
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": True}])
        for listener in self.listeners:
            listener()
        self.assertEqual(len(self.added), 1)
        self.assertTrue(self.added[0]._expected_boolean)

    def test_setting_reordering_keeps_entity_identity_and_value(self):
        settings = [{"k": "AutoDry", "v": True}, {"k": "ExtrFreq", "v": 3}]
        self.state.store.merge_properties([{"siid": 4, "piid": 50, "value": json.dumps(settings)}])
        self.register_both_platforms()
        entities = {entity.pointer: entity for entity in self.added}
        identities = {path: entity._attr_unique_id for path, entity in entities.items()}
        self.state.store.merge_properties([{"siid": 4, "piid": 50, "value": json.dumps(list(reversed(settings)))}])
        for listener in self.listeners:
            listener()
        self.assertEqual(len(self.added), 3)
        self.assertEqual(entities["/@AutoDry/v"].value, True)
        self.assertEqual(entities["/@ExtrFreq/v"].value, 3)
        self.assertEqual(identities, {entity.pointer: entity._attr_unique_id for entity in self.added})

    def test_unkeyed_arrays_and_sensitive_setting_keys_do_not_expand(self):
        self.state.store.merge_properties([
            {"siid": 4, "piid": 50, "value": [{"k": "streamKey", "v": "private"}, {"k": "ordinary", "v": 4}]},
            {"siid": 4, "piid": 51, "value": [1, 2, 3]},
        ])
        readings = list(self.scope["readings"](self.state))
        self.assertNotIn(("4.50", "/@streamKey/v", "private"), readings)
        self.assertIn(("4.50", "/@ordinary/v", 4), readings)
        self.assertEqual([pointer for key, pointer, _ in readings if key == "4.51"], [None])


class MqttCancellationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.skipTest("Optional paho dependency not installed")
        self.mqtt = mqtt
        session = Session("access", "refresh", "account", 9999999999)
        self.api = SimpleNamespace(ensure_session=AsyncMock(return_value=session), region="eu", account_type="dreame", visitor_id="v")
        device = Device("device", "unknown.model", "Appliance", "owner", "broker.example:19973")
        self.subscription = DeviceSubscription(self.api, device, lambda payload: None)
        self.started, self.release = threading.Event(), threading.Event()
        self.operations = []

    def blocking_connect(self, *args):
        self.started.set()
        if not self.release.wait(3):
            raise TimeoutError("Fabricated connect wait expired")
        self.operations.append("connect completed")
        return 0

    async def wait_for_connect(self):
        self.assertTrue(await asyncio.to_thread(self.started.wait, 3))

    async def test_cancelled_start_drains_connect_before_disconnect(self):
        with patch.object(self.mqtt.Client, "connect", side_effect=self.blocking_connect), \
             patch.object(self.mqtt.Client, "loop_start") as loop_start, \
             patch.object(self.mqtt.Client, "disconnect", side_effect=lambda: self.operations.append("disconnected")), \
             patch.object(self.mqtt.Client, "loop_stop"):
            task = asyncio.create_task(self.subscription.start())
            try:
                await self.wait_for_connect()
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                done, _ = await asyncio.wait([task], timeout=0.03)
                self.assertFalse(done)
            finally:
                self.release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            loop_start.assert_not_called()
        self.assertEqual(self.operations, ["connect completed", "disconnected"])
        self.assertIsNone(self.subscription._client)
        self.assertIsNone(self.subscription._refresh_task)

    async def test_stop_during_start_owns_and_closes_the_pending_client(self):
        with patch.object(self.mqtt.Client, "connect", side_effect=self.blocking_connect), \
             patch.object(self.mqtt.Client, "loop_start") as loop_start, \
             patch.object(self.mqtt.Client, "disconnect", side_effect=lambda: self.operations.append("disconnected")), \
             patch.object(self.mqtt.Client, "loop_stop"):
            start = asyncio.create_task(self.subscription.start())
            await self.wait_for_connect()
            stop = asyncio.create_task(self.subscription.stop())
            await asyncio.sleep(0)
            self.release.set()
            await asyncio.gather(start, stop)
            loop_start.assert_not_called()
        self.assertEqual(self.operations, ["connect completed", "disconnected"])
        self.assertIsNone(self.subscription._client)
        self.assertIsNone(self.subscription._refresh_task)
        self.subscription._set_connected(True)
        self.assertFalse(self.subscription.connected)


class CoordinatorOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, cancel):
        item = device_state()
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        class Subscription:
            def __init__(self, api, device, callback):
                pass

            async def start(self):
                self.assert_owned = item.subscription is self
                started.set()
                await release.wait()

            async def stop(self):
                calls.append("stopped")

        coordinator = SimpleNamespace(devices={"device": item}, entry=SimpleNamespace(data={}),
                                      stopped=False, api=object(), _push=lambda state, payload: None,
                                      async_update_listeners=lambda: None)
        namespace = {"DeviceSubscription": Subscription, "monotonic": lambda: 1, "CONF_MQTT": "mqtt_enabled",
                     "AuthenticationError": AuthenticationError, "DreameError": DreameError,
                     "ConfigEntryAuthFailed": AuthenticationError}
        start = coordinator_start(namespace)
        task = asyncio.create_task(start(coordinator))
        await started.wait()
        subscription = item.subscription
        self.assertTrue(subscription.assert_owned)
        if cancel:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        else:
            coordinator.stopped = True
            release.set()
            await task
        self.assertEqual(calls, ["stopped"])
        self.assertIsNone(item.subscription)

    async def test_cancelled_coordinator_start_releases_owned_subscription(self):
        await self.exercise(cancel=True)

    async def test_late_success_after_shutdown_is_closed(self):
        await self.exercise(cancel=False)


class EntrySetupOrderingTests(unittest.IsolatedAsyncioTestCase):
    """A failed MQTT startup must leave no forwarded HA platforms behind."""

    def setup_scope(self, error=None):
        operations = []

        async def refresh():
            operations.append("refresh")

        async def start():
            operations.append("mqtt")
            if error is not None:
                raise error

        async def forward(*args):
            operations.append("forward")

        coordinator = SimpleNamespace(
            async_config_entry_first_refresh=AsyncMock(side_effect=refresh),
            async_start_subscriptions=AsyncMock(side_effect=start),
            async_stop=AsyncMock(),
        )
        api = object()
        entry = SimpleNamespace(
            data={"username": "local-user", "refresh_token": "local-refresh", "region": "eu",
                  "visitor_id": "visitor", "account_uid": "account"},
            async_on_unload=lambda callback: None,
        )
        hass = SimpleNamespace(
            async_add_executor_job=AsyncMock(),
            bus=SimpleNamespace(async_listen_once=lambda event, callback: lambda: None),
            config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock(side_effect=forward)),
        )
        source = ast.parse((COMPONENT / "__init__.py").read_text(encoding="utf-8"))
        function = next(node for node in source.body
                        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup_entry")
        namespace = {
            "load_catalog": lambda name: None,
            "control_definitions": lambda model: [],
            "progress_definitions": lambda model: [],
            "DreameHomeClient": lambda *args, **kwargs: api,
            "DreameCoordinator": lambda *args: coordinator,
            "async_get_clientsession": lambda hass: object(), "AiohttpTransport": lambda session: session,
            "CONF_USERNAME": "username", "CONF_REGION": "region", "CONF_REFRESH_TOKEN": "refresh_token",
            "CONF_VISITOR_ID": "visitor_id", "CONF_ACCOUNT_UID": "account_uid",
            "EVENT_HOMEASSISTANT_STOP": "stop", "PLATFORMS": ("sensor", "binary_sensor"),
            "ConfigEntryAuthFailed": AuthenticationError,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "__init__.py", "exec"), namespace)
        return namespace[function.name], hass, entry, coordinator, operations

    async def test_auth_failure_during_mqtt_start_stops_before_platform_setup(self):
        error = AuthenticationError("Expired session")
        setup, hass, entry, coordinator, operations = self.setup_scope(error)
        with self.assertRaises(AuthenticationError) as caught:
            await setup(hass, entry)
        self.assertIs(caught.exception, error)
        self.assertEqual(operations, ["refresh", "mqtt"])
        hass.config_entries.async_forward_entry_setups.assert_not_awaited()
        coordinator.async_stop.assert_awaited_once()

    async def test_cancelled_mqtt_start_stops_before_platform_setup(self):
        setup, hass, entry, coordinator, operations = self.setup_scope(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await setup(hass, entry)
        self.assertEqual(operations, ["refresh", "mqtt"])
        hass.config_entries.async_forward_entry_setups.assert_not_awaited()
        coordinator.async_stop.assert_awaited_once()

    async def test_successful_start_precedes_platform_setup(self):
        setup, hass, entry, coordinator, operations = self.setup_scope()
        self.assertTrue(await setup(hass, entry))
        self.assertEqual(operations, ["refresh", "mqtt", "forward"])
        self.assertIs(entry.runtime_data, coordinator)
        coordinator.async_stop.assert_not_awaited()


class EntryUnloadSuspensionTests(unittest.IsolatedAsyncioTestCase):
    def setup_scope(self, *, result=True, error=None):
        scope = entity_scope()
        state = device_state()
        state.subscription = SimpleNamespace(connected=True)
        state.store.merge_properties([{"siid": 2, "piid": 1, "value": 1}])
        listeners, added, operations = [], [], []
        coordinator = SimpleNamespace(
            devices={"device": state}, entity_platforms={},
            stopped=False, entity_discovery_suspended=False,
            async_add_listener=lambda listener: listeners.append(listener) or (lambda: None),
            async_update_listeners=lambda: [listener() for listener in listeners],
        )

        async def stop():
            operations.append("stopped")
            coordinator.stopped = True
            state.subscription = None

        coordinator.async_stop = AsyncMock(side_effect=stop)
        entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=lambda callback: None)
        scope["add_observed_entities"](
            coordinator, entry, added.extend, lambda _, did, key, pointer: (did, key, pointer), boolean=False)
        self.assertEqual(len(added), 1)

        async def unload_platforms(*args):
            operations.append("unloading")
            self.assertTrue(coordinator.entity_discovery_suspended)
            self.assertFalse(coordinator.stopped)
            self.assertTrue(state.subscription.connected)
            # Exercise the actual discovery callback while HA platform removal
            # is suspended. Observation is retained, but no addition is queued.
            await asyncio.sleep(0)
            state.store.merge_push({"method": "properties_changed",
                                    "params": [{"siid": 2, "piid": 2, "value": 4}]})
            coordinator.async_update_listeners()
            self.assertEqual(len(added), 1)
            self.assertNotIn(("device", "2.2", None), coordinator.entity_platforms)
            if error is not None:
                raise error
            return result

        hass = SimpleNamespace(config_entries=SimpleNamespace(
            async_unload_platforms=AsyncMock(side_effect=unload_platforms)))
        source = ast.parse((COMPONENT / "__init__.py").read_text(encoding="utf-8"))
        function = next(node for node in source.body
                        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_unload_entry")
        namespace = {"PLATFORMS": ("sensor", "binary_sensor")}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "__init__.py", "exec"), namespace)
        return namespace[function.name], hass, entry, state, added, operations

    async def test_successful_unload_blocks_mqtt_entity_additions_then_stops(self):
        unload, hass, entry, state, added, operations = self.setup_scope()
        self.assertTrue(await unload(hass, entry))
        self.assertEqual(operations, ["unloading", "stopped"])
        self.assertTrue(entry.runtime_data.entity_discovery_suspended)
        self.assertTrue(entry.runtime_data.stopped)
        self.assertIsNone(state.subscription)
        self.assertIn("2.2", state.store.properties)
        entry.runtime_data.async_update_listeners()
        self.assertEqual(len(added), 1)
        entry.runtime_data.async_stop.assert_awaited_once()

    async def test_failed_unload_restores_discovery_and_keeps_clients_usable(self):
        unload, hass, entry, state, added, operations = self.setup_scope(result=False)
        self.assertFalse(await unload(hass, entry))
        self.assertFalse(entry.runtime_data.entity_discovery_suspended)
        self.assertFalse(entry.runtime_data.stopped)
        self.assertTrue(state.subscription.connected)
        self.assertEqual(operations, ["unloading"])
        self.assertIn(("device", "2.2", None), added)
        entry.runtime_data.async_stop.assert_not_awaited()

    async def test_unload_exception_restores_discovery_without_stopping(self):
        for error in (RuntimeError("Fixture platform removal failed"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                unload, hass, entry, state, added, _ = self.setup_scope(error=error)
                with self.assertRaises(type(error)) as caught:
                    await unload(hass, entry)
                self.assertIs(caught.exception, error)
                self.assertFalse(entry.runtime_data.entity_discovery_suspended)
                self.assertFalse(entry.runtime_data.stopped)
                self.assertTrue(state.subscription.connected)
                self.assertIn(("device", "2.2", None), added)
                entry.runtime_data.async_stop.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
