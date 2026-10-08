"""Retry exact read candidates without overriding cloud online or control gates."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from dreamehome.exceptions import AuthenticationError, DreameError, RateLimitError, TransportError
from dreamehome.laundry import laundry_read_pairs, laundry_schema
from dreamehome.observations import ObservationStore, VACUUM_INITIAL_READ_PAIRS, property_coordinate
from dreamehome.models import Device

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_home"
MODELS = ("dreame.washer.l9nacn", "dreame.dryer.l9nacn", "dreame.vacuum.r5023a")


def read_scope(clock):
    tree = ast.parse((COMPONENT / "coordinator.py").read_text(encoding="utf-8"))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DreameCoordinator")
    functions = [node for node in owner.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in ("_read", "_freshness")]
    scope = {"monotonic": lambda: clock[0], "VACUUM_INITIAL_READ_PAIRS": VACUUM_INITIAL_READ_PAIRS,
             "laundry_read_pairs": laundry_read_pairs, "laundry_schema": laundry_schema,
             "property_coordinate": property_coordinate, "AuthenticationError": AuthenticationError,
             "RateLimitError": RateLimitError, "DreameError": DreameError}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "coordinator.py", "exec"), scope)
    return scope


def candidates(model):
    return list(VACUUM_INITIAL_READ_PAIRS) if model == MODELS[2] else laundry_read_pairs(model)


def successful_rows(pairs):
    return [{"siid": siid, "piid": piid, "value": 1, "code": 0} for siid, piid in pairs]


class CandidateRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.scope = read_scope(self.clock)
        self.api = SimpleNamespace(read_properties=AsyncMock(return_value=[]))
        self.coordinator = SimpleNamespace(api=self.api)
        self.coordinator._freshness = lambda state, touched: self.scope["_freshness"](self.coordinator, state, touched)

    def state(self, model):
        return SimpleNamespace(device=SimpleNamespace(model=model), store=ObservationStore(model),
                               timestamps={}, read_error=None, initial_read_done=False,
                               initial_read_status="not_started", schema_coverage={})

    async def read(self, state):
        await self.scope["_read"](self.coordinator, state)

    async def test_empty_null_and_error_initial_replies_are_retried_and_recover(self):
        for model in MODELS:
            seeds = candidates(model)
            for failure in ("empty", "null", "error"):
                with self.subTest(model=model, failure=failure):
                    state = self.state(model)
                    first = ([] if failure == "empty" else
                             [{"siid": siid, "piid": piid,
                               "value": None if failure == "null" else 1,
                               "code": 0 if failure == "null" else -4001}
                              for siid, piid in seeds])
                    self.api.read_properties.reset_mock()
                    self.api.read_properties.side_effect = [first, successful_rows(seeds)]
                    await self.read(state)
                    self.assertTrue(state.initial_read_done)
                    self.assertNotEqual(state.initial_read_status, "complete")
                    self.assertEqual(state.timestamps, {})
                    self.clock[0] += 60
                    await self.read(state)
                    self.assertEqual(self.api.read_properties.await_count, 2)
                    self.assertEqual(self.api.read_properties.call_args.args[1], seeds)
                    self.assertEqual(state.initial_read_status, "complete")
                    self.assertTrue(all(row.get("value") == 1 for row in state.store.properties.values()))
                    self.assertEqual(set(state.timestamps), {f"{siid}.{piid}" for siid, piid in seeds})

    async def test_known_model_retries_previously_valued_address_after_failure(self):
        state = self.state(MODELS[0])
        state.initial_read_done = True
        # This exact source write-only field is read only after a real observation.
        state.store.merge_properties([{"siid": 2, "piid": 5, "value": 4}], source="mqtt")
        state.store.merge_properties([{"siid": 2, "piid": 5, "code": -4001}])
        self.api.read_properties.return_value = [{"siid": 2, "piid": 5, "value": 3, "code": 0}]
        await self.read(state)
        self.assertIn((2, 5), self.api.read_properties.call_args.args[1])
        self.assertEqual(state.store.properties["2.5"]["value"], 3)
        self.assertEqual(state.timestamps["2.5"], self.clock[0])

    async def test_unknown_model_has_no_seed_and_keeps_successful_observation_gate(self):
        state = self.state("dreame.washer.unverified")
        await self.read(state)
        self.api.read_properties.assert_not_called()
        state.store.merge_properties([
            {"siid": 9, "piid": 1, "value": 2, "code": 0},
            {"siid": 9, "piid": 2, "value": 4, "code": -4001},
            {"siid": 9, "piid": 3, "value": 5, "code": 0},
        ])
        state.store.merge_properties([{"siid": 9, "piid": 3, "code": -4001}])
        self.api.read_properties.return_value = []
        await self.read(state)
        self.assertEqual(self.api.read_properties.call_args.args[1], [(9, 1)])

    async def test_every_refresh_reserves_known_seeds_within_240_address_budget(self):
        for model in MODELS:
            with self.subTest(model=model):
                state = self.state(model)
                state.initial_read_done = True
                state.store.merge_properties(successful_rows([(100, index) for index in range(1, 301)]))
                self.api.read_properties.side_effect = None
                self.api.read_properties.return_value = []
                chosen = []
                for _ in range(2):
                    await self.read(state)
                    selected = self.api.read_properties.call_args.args[1]
                    self.assertEqual(len(selected), 240)
                    self.assertEqual(len(set(selected)), 240)
                    self.assertTrue(set(candidates(model)).issubset(selected))
                    chosen.append(set(selected))
                    self.clock[0] += 60
                self.assertNotEqual(chosen[0], chosen[1])

    async def test_read_status_recomputed_instead_of_retaining_stale_complete(self):
        state = self.state(MODELS[1])
        seeds = candidates(MODELS[1])
        self.api.read_properties.side_effect = [successful_rows(seeds), [],
                                               [{"siid": 3, "piid": 11, "value": None, "code": 0}],
                                               successful_rows(seeds)]
        for expected in ("complete", "empty", "partial", "complete"):
            await self.read(state)
            self.assertEqual(state.initial_read_status, expected)

    async def test_unrequested_coordinate_does_not_expand_retry_candidates(self):
        state = self.state(MODELS[0])
        self.api.read_properties.return_value = [{"siid": 200, "piid": 10, "value": 1, "code": 0}]
        await self.read(state)
        self.assertNotIn("200.10", state.store.properties)
        await self.read(state)
        self.assertNotIn((200, 10), self.api.read_properties.call_args.args[1])


class UpdateFailed(Exception):
    def __init__(self, message, *, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


def online_scope(clock):
    tree = ast.parse((COMPONENT / "coordinator.py").read_text(encoding="utf-8"))
    online = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "cloud_online")
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DreameCoordinator")
    functions = [node for node in owner.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in ("_async_update_data", "_refresh_online", "_discover")]
    scope = {"asyncio": asyncio, "monotonic": lambda: clock[0], "Device": Device,
             "laundry_schema": laundry_schema, "AuthenticationError": AuthenticationError,
             "ConfigEntryAuthFailed": AuthenticationError, "RateLimitError": RateLimitError,
             "DreameError": DreameError, "UpdateFailed": UpdateFailed}
    isolated = ast.Module(body=[online, ast.ClassDef(name="Coordinator", bases=[], keywords=[],
                                                    body=functions, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(isolated), "coordinator.py", "exec"), scope)
    return scope["Coordinator"]


class OnlineRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.coordinator = online_scope(self.clock)()
        self.device = Device.from_record({"did": "test-device", "model": MODELS[0], "online": False})
        self.state = SimpleNamespace(device=self.device, store=ObservationStore(self.device.model),
                                     present=True, online=False, online_checked=None,
                                     metadata_error=None, subscription=None, schema_coverage={},
                                     command_backoff_until=0, timestamps={})
        self.coordinator.devices = {self.device.did: self.state}
        self.coordinator.stopped = False
        self.coordinator.discovery_complete = True
        self.coordinator.last_inventory = self.clock[0]
        self.coordinator.subscriptions_enabled = False
        self.coordinator._command_locks = {}
        self.coordinator._read = AsyncMock()
        self.coordinator._cloud_data = AsyncMock()
        self.api = SimpleNamespace(get_device_info=AsyncMock(return_value={"online": False}),
                                   list_devices=AsyncMock(return_value=[self.device]))
        self.coordinator.api = self.api

    async def test_explicit_online_recovers_and_reads_during_same_poll_for_both_l9_models(self):
        for model in MODELS[:2]:
            with self.subTest(model=model):
                self.setUp()
                self.state.device = Device("test-device", model, "Laundry")
                self.api.get_device_info.return_value = {"online": True, "property": {"2.1": 2}}
                await self.coordinator._async_update_data()
                self.assertTrue(self.state.online)
                self.coordinator._read.assert_awaited_once_with(self.state)
                # Metadata alone supplies neither live values nor fresh control observations.
                self.assertEqual(self.state.store.properties, {})
                self.assertEqual(self.state.timestamps, {})
                self.api.list_devices.assert_not_awaited()

    async def test_offline_missing_and_nonboolean_online_never_trigger_device_rpc(self):
        for info in ({"online": False}, {}, {"online": 1}, {"online": "true"},
                     {"property": {"2.1": 2}}, {"deviceInfo": {"online": False}}):
            with self.subTest(info=info):
                self.setUp()
                self.api.get_device_info.return_value = info
                await self.coordinator._async_update_data()
                self.assertIs(self.state.online, False)
                self.coordinator._read.assert_not_awaited()

    async def test_nested_explicit_online_is_accepted(self):
        self.api.get_device_info.return_value = {"deviceInfo": {"online": True}}
        await self.coordinator._async_update_data()
        self.assertIs(self.state.online, True)
        self.coordinator._read.assert_awaited_once()

    async def test_return_online_keeps_old_values_but_requires_new_observations(self):
        self.state.store.merge_properties([{"siid": 2, "piid": 1, "value": 2, "code": 0}])
        self.state.timestamps["2.1"] = self.clock[0] - 60
        self.api.get_device_info.return_value = {"online": True}
        await self.coordinator._async_update_data()
        self.assertIs(self.state.online, True)
        self.assertEqual(self.state.store.properties["2.1"]["value"], 2)
        self.assertEqual(self.state.timestamps, {})

    async def test_offline_metadata_checks_are_capped_at_one_per_minute(self):
        await self.coordinator._async_update_data()
        self.clock[0] += 59
        await self.coordinator._async_update_data()
        self.api.get_device_info.assert_awaited_once()
        self.clock[0] += 1
        await self.coordinator._async_update_data()
        self.assertEqual(self.api.get_device_info.await_count, 2)
        self.coordinator._read.assert_not_awaited()

    async def test_inventory_refresh_does_not_duplicate_metadata_request(self):
        self.coordinator.discovery_complete = False
        await self.coordinator._async_update_data()
        self.api.list_devices.assert_awaited_once()
        self.api.get_device_info.assert_awaited_once()
        self.assertEqual(self.state.online_checked, self.clock[0])
        self.coordinator._read.assert_not_awaited()

    async def test_transport_failure_preserves_offline_and_is_rate_bounded(self):
        self.api.get_device_info.side_effect = TransportError("private response")
        await self.coordinator._async_update_data()
        self.assertIs(self.state.online, False)
        self.assertEqual(self.state.metadata_error, "TransportError")
        await self.coordinator._async_update_data()
        self.api.get_device_info.assert_awaited_once()
        self.coordinator._read.assert_not_awaited()

    async def test_authentication_and_rate_limit_keep_existing_account_failure_behavior(self):
        for error, expected in ((AuthenticationError("private response"), AuthenticationError),
                                (RateLimitError("180"), UpdateFailed)):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                self.api.get_device_info.side_effect = error
                with self.assertRaises(expected) as caught:
                    await self.coordinator._async_update_data()
                self.assertNotIn("private response", str(caught.exception))
                if isinstance(caught.exception, UpdateFailed):
                    self.assertEqual(caught.exception.retry_after, 180)
                self.assertIs(self.state.online, False)
                self.coordinator._read.assert_not_awaited()

    async def test_absent_stopped_backed_off_and_other_models_are_not_probed(self):
        for mode in ("absent", "stopped", "backoff", "other"):
            with self.subTest(mode=mode):
                self.setUp()
                if mode == "absent":
                    self.state.present = False
                elif mode == "stopped":
                    self.coordinator.stopped = True
                elif mode == "backoff":
                    self.state.command_backoff_until = self.clock[0] + 60
                else:
                    self.state.device = Device("test-device", MODELS[2], "Other")
                await self.coordinator._async_update_data()
                self.api.get_device_info.assert_not_awaited()
                self.coordinator._read.assert_not_awaited()

    async def test_metadata_waits_for_device_lock_and_stop_prevents_late_read(self):
        lock = asyncio.Lock()
        self.coordinator._command_locks[self.device.did] = lock
        await lock.acquire()
        entered, release = asyncio.Event(), asyncio.Event()
        async def metadata(did):
            self.assertTrue(lock.locked())
            entered.set()
            await release.wait()
            return {"online": True}
        self.api.get_device_info.side_effect = metadata
        task = asyncio.create_task(self.coordinator._async_update_data())
        await asyncio.sleep(0)
        self.api.get_device_info.assert_not_awaited()
        lock.release()
        await entered.wait()
        self.coordinator.stopped = True
        release.set()
        await task
        self.assertIs(self.state.online, False)
        self.coordinator._read.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
