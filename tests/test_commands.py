"""Exercise actual command gateway bodies with fake transports, without HA."""

import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from dreamehome.exceptions import AuthenticationError, DreameError, RateLimitError, TransportError
from dreamehome.laundry_controls import prepare_control_write
from dreamehome.vacuum_controls import prepare_vacuum_command

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_home"


class HomeAssistantError(Exception):
    pass


class ServiceValidationError(HomeAssistantError):
    pass


def gateway_type(clock):
    tree = ast.parse((COMPONENT / "coordinator.py").read_text(encoding="utf-8"))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DreameCoordinator")
    wanted = {"control_ready", "control_observations", "async_execute_control", "async_execute_vacuum",
              "_async_execute", "_send_command", "async_stop", "_async_update_data"}
    body = [node for node in owner.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in wanted]
    ack = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "command_acknowledged")
    scope = {"asyncio": asyncio, "monotonic": lambda: clock[0], "prepare_control_write": prepare_control_write,
             "prepare_vacuum_command": prepare_vacuum_command, "HomeAssistantError": HomeAssistantError,
             "ServiceValidationError": ServiceValidationError, "AuthenticationError": AuthenticationError,
             "DreameError": DreameError, "RateLimitError": RateLimitError, "ConfigEntryAuthFailed": AuthenticationError,
             "_LOGGER": logging.getLogger(__name__)}
    isolated = ast.Module(body=[ack, ast.ClassDef(name="Gateway", bases=[], keywords=[], body=body, decorator_list=[])],
                          type_ignores=[])
    exec(compile(ast.fix_missing_locations(isolated), "coordinator.py", "exec"), scope)
    return scope["Gateway"], scope["command_acknowledged"]


def observations(**overrides):
    values = {"2.1": 1, "2.2": 0, "2.3": 2, "3.4": 0, "3.14": 1}
    values.update(overrides)
    return {key: {"value": value, "last_code": 0, "last_reply_null": False,
                  "last_source": "rpc", "last_item": {"value": value}}
            for key, value in values.items()}


class CommandGatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = [1000.0]
        kind, self.ack = gateway_type(self.clock)
        self.gateway = kind()
        self.state = SimpleNamespace(device=SimpleNamespace(did="fabricated-device", model="dreame.washer.l9nacn"),
                                     store=SimpleNamespace(properties=observations()),
                                     timestamps={key: 999.0 for key in observations()}, present=True, online=True,
                                     command_busy=False, command_observation_floor=0, command_backoff_until=0,
                                     last_command_status=None,
                                     subscription=None)
        self.gateway.devices = {"fabricated-device": self.state}
        self.gateway.stopped = False
        self.gateway.entity_discovery_suspended = False
        self.gateway.last_update_success = True
        self.gateway._command_locks = {}
        self.gateway._command_tasks = set()
        self.gateway._stop_lock = asyncio.Lock()
        self.gateway.async_update_listeners = Mock()
        self.gateway.async_set_update_error = Mock()
        self.gateway.async_shutdown = AsyncMock()
        self.gateway._read = AsyncMock()
        self.gateway.entry = SimpleNamespace(async_start_reauth=Mock())
        self.gateway.hass = object()
        self.gateway.api = SimpleNamespace(ensure_session=AsyncMock(),
                                           action=AsyncMock(return_value={"code": 0}),
                                           write_properties=AsyncMock(return_value=[{"code": 0}]))

    async def press(self, key="start"):
        await self.gateway.async_execute_control("fabricated-device", key)

    def refresh(self):
        self.state.timestamps = {key: self.clock[0] for key in self.state.store.properties}

    async def test_start_uses_exact_encoder_and_readback_without_prediction(self):
        before = dict(self.state.store.properties["2.1"])
        await self.press()
        self.gateway.api.action.assert_awaited_once_with(self.state.device, 2, 2, [{"piid": 2, "value": 1}])
        self.gateway._read.assert_awaited_once_with(self.state)
        self.assertEqual(self.state.store.properties["2.1"], before)
        self.assertEqual(self.state.last_command_status, "accepted")
        self.assertFalse(self.state.command_busy)
        self.assertEqual(self.gateway.control_observations("fabricated-device"), {})

    async def test_offline_busy_stale_unknown_and_failed_rows_never_transmit(self):
        for mutation in (lambda: setattr(self.state, "online", False),
                         lambda: setattr(self.state, "command_busy", True),
                         lambda: self.state.timestamps.update({"2.1": 100.0}),
                         lambda: self.state.store.properties["2.1"].update(value=99),
                         lambda: self.state.store.properties["2.1"].update(last_code=False),
                         lambda: self.state.store.properties["2.1"].update(last_source="metadata"),
                         lambda: self.state.store.properties["2.1"].update(last_item={"code": 0}),
                         lambda: self.state.store.properties["2.1"].update(last_reply_null=True)):
            self.setUp()
            mutation()
            with self.assertRaises(ServiceValidationError):
                await self.press()
            self.gateway.api.ensure_session.assert_not_awaited()
            self.gateway.api.action.assert_not_awaited()

    async def test_session_wait_revalidates_state_before_transmission(self):
        async def renew():
            self.state.store.properties["3.4"]["value"] = 1
        self.gateway.api.ensure_session.side_effect = renew
        with self.assertRaises(ServiceValidationError):
            await self.press()
        self.gateway.api.action.assert_not_awaited()
        self.gateway._read.assert_not_awaited()
        self.assertFalse(self.state.command_busy)

    async def test_ack_requires_success_complete_rows_and_matching_coordinates(self):
        expected = [{"siid": 3, "piid": 4}]
        for reply in (None, [], [{"value": 0}], [{"code": False}], [{"code": -1}],
                      [{"code": 0}, {"code": 0}], [{"code": 0, "siid": 4}], [{"code": 0, "piid": "5"}]):
            with self.subTest(reply=reply), self.assertRaises(HomeAssistantError):
                self.ack(reply, expected)
        self.ack([{"code": "0", "siid": "3", "piid": 4}], expected)
        self.ack({"code": 0, "siid": 2, "aiid": 1}, [{"siid": 2, "aiid": 1}], action=True)

    async def test_auth_failure_is_not_replayed_and_starts_reauthentication(self):
        self.gateway.api.action.side_effect = AuthenticationError("fabricated-secret")
        with self.assertRaises(HomeAssistantError) as caught:
            await self.press()
        self.assertNotIn("fabricated-secret", str(caught.exception))
        self.gateway.api.action.assert_awaited_once()
        self.gateway.entry.async_start_reauth.assert_called_once_with(self.gateway.hass)
        self.gateway.async_set_update_error.assert_called_once()
        self.gateway._read.assert_awaited_once()
        self.assertEqual(self.state.last_command_status, "reauthentication_required")

    async def test_transport_rate_limit_and_rejection_are_not_replayed(self):
        for error, status in ((TransportError("secret"), "unconfirmed"),
                              (RateLimitError("180"), "rate_limited"),
                              (None, "rejected_or_unconfirmed")):
            self.setUp()
            self.gateway.api.action.side_effect = error
            self.gateway.api.action.return_value = {"code": -1}
            with self.assertRaises(HomeAssistantError) as caught:
                await self.press()
            self.assertNotIn("secret", str(caught.exception))
            self.gateway.api.action.assert_awaited_once()
            if status == "rate_limited":
                self.gateway._read.assert_not_awaited()
                self.assertFalse(self.gateway.control_ready("fabricated-device"))
                self.assertEqual(self.state.command_backoff_until, 1180)
                self.gateway.discovery_complete = True
                self.gateway.last_inventory = self.clock[0]
                self.gateway.subscriptions_enabled = False
                self.gateway._discover = AsyncMock()
                await self.gateway._async_update_data()
                self.gateway._read.assert_not_awaited()
            else:
                self.gateway._read.assert_awaited_once()
            self.assertEqual(self.state.last_command_status, status)
            self.assertFalse(self.state.command_busy)

    async def test_readback_failure_preserves_accepted_result(self):
        self.gateway._read.side_effect = TransportError("secret")
        await self.press()
        self.assertEqual(self.state.last_command_status, "accepted")
        self.assertFalse(self.state.command_busy)

    async def test_per_device_lock_revalidates_queued_command_after_readback(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def action(*args):
            entered.set()
            await release.wait()
            return {"code": 0}
        async def readback(state):
            state.store.properties["2.1"]["value"] = 3
            self.refresh()
        self.gateway.api.action.side_effect = action
        self.gateway._read.side_effect = readback
        first = asyncio.create_task(self.press())
        await entered.wait()
        second = asyncio.create_task(self.press())
        await asyncio.sleep(0)
        self.assertEqual(self.gateway.api.action.await_count, 1)
        release.set()
        await first
        with self.assertRaises(ServiceValidationError):
            await second
        self.gateway.api.action.assert_awaited_once()

    async def test_sequential_vacuum_patch_stops_after_first_failed_ack(self):
        plan = {"method": "set_properties", "sequential": True, "properties": [
            {"siid": 4, "piid": 50, "value": '{"k":"SuctionMax","v":0}'},
            {"siid": 4, "piid": 4, "value": 2}]}
        self.gateway.api.write_properties.return_value = [{"code": -1}]
        with self.assertRaises(HomeAssistantError):
            await self.gateway._send_command(self.state, plan)
        self.gateway.api.write_properties.assert_awaited_once()
        self.gateway.api.write_properties.reset_mock()
        self.gateway.api.write_properties.return_value = [{"code": 0}]
        await self.gateway._send_command(self.state, plan)
        self.assertEqual(self.gateway.api.write_properties.await_count, 2)
        self.assertEqual(self.gateway.api.write_properties.call_args.args[1], [(4, 4, 2)])

    async def test_shutdown_cancels_transmitting_and_queued_commands(self):
        entered = asyncio.Event()
        async def action(*args):
            entered.set()
            await asyncio.Event().wait()
        self.gateway.api.action.side_effect = action
        first = asyncio.create_task(self.press())
        await entered.wait()
        second = asyncio.create_task(self.press())
        await asyncio.sleep(0)
        await self.gateway.async_stop()
        results = await asyncio.gather(first, second, return_exceptions=True)
        self.assertTrue(all(isinstance(result, asyncio.CancelledError) for result in results))
        self.assertFalse(self.state.command_busy)
        self.assertEqual(self.gateway._command_tasks, set())
        self.assertEqual(self.state.last_command_status, "unconfirmed")
        self.gateway._read.assert_not_awaited()
        self.gateway.async_shutdown.assert_awaited_once()

    async def test_cancelled_readback_always_releases_busy_flag(self):
        entered = asyncio.Event()
        async def readback(state):
            entered.set()
            await asyncio.Event().wait()
        self.gateway._read.side_effect = readback
        task = asyncio.create_task(self.press())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.state.command_busy)
        self.assertFalse(self.gateway._command_tasks)

    async def test_poll_waits_for_command_and_its_readback(self):
        self.gateway.discovery_complete = True
        self.gateway.last_inventory = self.clock[0]
        self.gateway.subscriptions_enabled = False
        self.gateway._discover = AsyncMock()
        entered, release = asyncio.Event(), asyncio.Event()
        async def action(*args):
            entered.set()
            await release.wait()
            return {"code": 0}
        self.gateway.api.action.side_effect = action
        task = asyncio.create_task(self.press())
        await entered.wait()
        poll = asyncio.create_task(self.gateway._async_update_data())
        await asyncio.sleep(0)
        self.gateway._read.assert_not_awaited()
        release.set()
        await asyncio.gather(task, poll)
        self.assertEqual(self.gateway._read.await_count, 2)

        # A poll already waiting on the device lock must recheck a new cooldown.
        self.setUp()
        self.gateway.discovery_complete = True
        self.gateway.last_inventory = self.clock[0]
        self.gateway.subscriptions_enabled = False
        self.gateway._discover = AsyncMock()
        entered, release = asyncio.Event(), asyncio.Event()
        async def limited(*args):
            entered.set()
            await release.wait()
            raise RateLimitError("180")
        self.gateway.api.action.side_effect = limited
        task = asyncio.create_task(self.press())
        await entered.wait()
        poll = asyncio.create_task(self.gateway._async_update_data())
        await asyncio.sleep(0)
        release.set()
        with self.assertRaises(HomeAssistantError):
            await task
        await poll
        self.gateway._read.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
