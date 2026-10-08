"""Account discovery, bounded observation and explicit appliance commands."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from time import monotonic

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.exceptions import AuthenticationError, DreameError, RateLimitError
from .api.laundry import laundry_cloud_read_keys, laundry_cloud_values, laundry_read_pairs, laundry_schema
from .api.laundry_controls import prepare_control_write
from .api.models import Device
from .api.mqtt import DeviceSubscription
from .api.observations import ObservationStore, VACUUM_INITIAL_READ_PAIRS, property_coordinate
from .api.privacy import redactor
from .api.vacuum_controls import prepare_vacuum_command
from .const import CONF_MQTT, DOMAIN, INTEGRATION_NAME
from .diagnostics import diagnostic_value

_LOGGER = logging.getLogger(__name__)


def command_acknowledged(result, expected, *, action=False):
    """Require explicit success and validate any supplied coordinate correlation."""
    rows = [result] if action and isinstance(result, dict) else result
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise HomeAssistantError("Dreame did not acknowledge the complete command; check the device state")
    for row, requested in zip(rows, expected):
        if not isinstance(row, dict) or "code" not in row:
            raise HomeAssistantError("Dreame returned an unconfirmed command result; check the device state")
        code = row["code"]
        if type(code) not in (int, str) or code not in (0, "0"):
            raise HomeAssistantError("Dreame rejected the appliance command")
        for key in ("siid", "aiid" if action else "piid"):
            if key in row and (type(row[key]) not in (int, str) or str(row[key]) != str(requested[key])):
                raise HomeAssistantError("Dreame returned a command result for another property or action")


def cloud_online(raw):
    value = raw.get("online", (raw.get("deviceInfo") or {}).get("online"))
    if isinstance(value, bool):
        return value
    return None


@dataclass
class DeviceState:
    device: Device
    store: ObservationStore
    present: bool = True
    online: bool | None = None
    metadata_error: str | None = None
    read_error: str | None = None
    initial_read_done: bool = False
    initial_read_status: str = "not_started"
    schema_coverage: dict = field(default_factory=dict)
    cloud_data_error: str | None = None
    cloud_data_keys: set[str] = field(default_factory=set)
    subscription: DeviceSubscription | None = None
    mqtt_error: str | None = None
    mqtt_attempt: float = 0
    timestamps: dict[str, float] = field(default_factory=dict)
    cached_rows: dict = field(default_factory=dict)
    command_busy: bool = False
    command_observation_floor: float = 0
    command_backoff_until: float = 0
    last_command_status: str | None = None


class DreameCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        super().__init__(hass, _LOGGER, name=INTEGRATION_NAME, config_entry=entry,
                         update_interval=timedelta(seconds=60))
        self.entry, self.api = entry, api
        self.devices = {}
        self.entity_platforms = {}
        self.entity_discovery_suspended = False
        self.last_inventory = 0
        self.stopped = False
        self.subscriptions_enabled = False
        self.discovery_complete = False
        self._stop_lock = asyncio.Lock()
        self._command_locks = {}
        self._command_tasks = set()

    def control_ready(self, did):
        state = self.devices.get(did)
        return bool(state and not self.stopped and not self.entity_discovery_suspended
                    and state.present and state.online is True and self.last_update_success
                    and not state.command_busy and monotonic() >= state.command_backoff_until)

    def control_observations(self, did):
        """Only fresh, confirmed observations may enable state-dependent commands."""
        state = self.devices.get(did)
        if state is None:
            return {}
        now = monotonic()
        return {key: row for key, row in state.store.properties.items()
                if row.get("value") is not None and not row.get("last_reply_null", False)
                and row.get("last_source") in ("rpc", "mqtt")
                and row.get("last_item", {}).get("value") is not None
                and (row.get("last_code") is None
                     or type(row.get("last_code")) is int and row["last_code"] == 0
                     or type(row.get("last_code")) is str and row["last_code"] == "0")
                and key in state.timestamps and 0 <= now - state.timestamps[key] <= 180
                and state.timestamps[key] >= state.command_observation_floor}

    async def async_execute_control(self, did, key, value=None):
        await self._async_execute(did, prepare_control_write, key, value)

    async def async_execute_vacuum(self, did, command, value=None):
        await self._async_execute(did, prepare_vacuum_command, command, value)

    async def _async_execute(self, did, prepare, key, value):
        task = asyncio.current_task()
        self._command_tasks.add(task)
        state = None
        attempted = False
        readback_allowed = True
        try:
            async with self._command_locks.setdefault(did, asyncio.Lock()):
                if not self.control_ready(did):
                    raise ServiceValidationError("The appliance is offline, busy or unavailable")
                state = self.devices[did]
                try:
                    plan = prepare(state.device.model, key, value, self.control_observations(did))
                except (ValueError, TypeError, KeyError) as error:
                    # Helpers emit fixed validation messages, never account data.
                    raise ServiceValidationError(str(error)) from None
                state.command_busy = True
                self.async_update_listeners()
                try:
                    # Renew before transmitting a command, then never replay it.
                    await self.api.ensure_session()
                    if (self.stopped or self.entity_discovery_suspended or self.devices.get(did) is not state
                            or not state.present or state.online is not True or not self.last_update_success):
                        raise ServiceValidationError("The appliance is no longer available")
                    try:
                        plan = prepare(state.device.model, key, value, self.control_observations(did))
                    except (ValueError, TypeError, KeyError) as error:
                        raise ServiceValidationError(str(error)) from None
                    attempted = True
                    state.command_observation_floor = monotonic()
                    state.last_command_status = "pending"
                    await self._send_command(state, plan)
                    state.last_command_status = "accepted"
                except AuthenticationError:
                    state.last_command_status = "reauthentication_required"
                    self.entry.async_start_reauth(self.hass)
                    self.async_set_update_error(ConfigEntryAuthFailed("Dreame session requires reauthentication"))
                    raise HomeAssistantError("Sign in to Dreame Home again; the command was not replayed") from None
                except RateLimitError as error:
                    state.last_command_status = "rate_limited"
                    readback_allowed = False
                    try:
                        retry = max(60, min(3600, float(error.retry_after or 60)))
                    except (TypeError, ValueError):
                        retry = 60
                    state.command_backoff_until = monotonic() + retry
                    raise HomeAssistantError("Dreame cloud rate limit reached; the command was not replayed") from None
                except asyncio.CancelledError:
                    readback_allowed = False
                    if attempted:
                        state.last_command_status = "unconfirmed"
                    raise
                except DreameError:
                    state.last_command_status = "unconfirmed"
                    raise HomeAssistantError("Dreame did not confirm the command; check the device state before trying again") from None
                except HomeAssistantError:
                    if state.last_command_status == "pending":
                        state.last_command_status = "rejected_or_unconfirmed"
                    raise
                finally:
                    try:
                        if attempted and readback_allowed and not self.stopped and not self.entity_discovery_suspended:
                            # A readback failure does not turn an accepted command
                            # into a reported write failure. Never predict state.
                            try:
                                await self._read(state)
                            except AuthenticationError:
                                self.entry.async_start_reauth(self.hass)
                                self.async_set_update_error(ConfigEntryAuthFailed("Dreame session requires reauthentication"))
                            except DreameError:
                                _LOGGER.debug("Dreame command readback could not complete")
                    finally:
                        state.command_busy = False
                        if not self.stopped:
                            self.async_update_listeners()
        finally:
            self._command_tasks.discard(task)

    async def _send_command(self, state, plan):
        if plan.get("method") == "set_properties":
            properties = plan["properties"]
            groups = [[row] for row in properties] if plan.get("sequential") else [properties]
            for rows in groups:
                result = await self.api.write_properties(
                    state.device, [(row["siid"], row["piid"], row["value"]) for row in rows])
                command_acknowledged(result, rows)
        elif plan.get("method") == "action":
            action = plan["action"]
            result = await self.api.action(state.device, action["siid"], action["aiid"], action["in"])
            command_acknowledged(result, [action], action=True)
        else:
            raise ServiceValidationError("This appliance command is unsupported")

    async def _async_update_data(self):
        try:
            if not self.discovery_complete or monotonic() - self.last_inventory >= 600:
                await self._discover()
            for state in self.devices.values():
                if (state.present and state.online is not False
                        and monotonic() >= state.command_backoff_until):
                    # A poll started before a write must not supply its readback.
                    async with self._command_locks.setdefault(state.device.did, asyncio.Lock()):
                        if (not self.stopped and state.present and state.online is not False
                                and monotonic() >= state.command_backoff_until):
                            await self._read(state)
            if self.subscriptions_enabled:
                await self.async_start_subscriptions()
        except AuthenticationError:
            raise ConfigEntryAuthFailed("Dreame session requires reauthentication") from None
        except RateLimitError as error:
            try:
                retry = max(60, min(3600, float(error.retry_after or 60)))
            except (TypeError, ValueError):
                retry = 60
            raise UpdateFailed("Dreame cloud rate limit", retry_after=retry) from None
        except DreameError:
            raise UpdateFailed("Dreame cloud discovery failed") from None
        return self.devices

    async def _discover(self):
        listing = await self.api.list_devices()
        seen = set()
        for device in listing:
            seen.add(device.did)
            state = self.devices.get(device.did)
            if state is None or state.device.model != device.model:
                if state and state.subscription:
                    await state.subscription.stop()
                state = DeviceState(device, ObservationStore(device.model))
                self.devices[device.did] = state
            state.present = True
            old_routing = state.device.owner_uid, state.device.bind_domain
            state.device = Device.from_record({**state.device.raw, **device.raw})
            state.online = cloud_online(state.device.raw)
            state.store.merge_cached(device.raw.get("property", {}), source="listing")
            try:
                info = await self.api.get_device_info(device.did)
                state.device = Device.from_record({**state.device.raw, **info})
                state.online = cloud_online(state.device.raw)
                state.store.merge_cached(info.get("property", {}), source="metadata")
                state.metadata_error = None
            except (AuthenticationError, RateLimitError):
                raise
            except DreameError as error:
                state.metadata_error = type(error).__name__
            await self._cloud_data(state)
            schema = laundry_schema(state.device.model)
            if schema:
                state.schema_coverage = schema.coverage(state.store.properties)
            if state.subscription and old_routing != (state.device.owner_uid, state.device.bind_domain):
                await state.subscription.stop()
                state.subscription = None
                state.mqtt_attempt = 0
        for did, state in self.devices.items():
            if did not in seen:
                state.present, state.online = False, False
                if state.subscription:
                    await state.subscription.stop()
                    state.subscription = None
        self.discovery_complete = True
        self.last_inventory = monotonic()

    async def _cloud_data(self, state):
        keys = laundry_cloud_read_keys(state.device.model)
        if not keys:
            return
        state.cloud_data_keys = set(keys)
        try:
            payload = await self.api.get_device_data(state.device.did, keys)
            values = laundry_cloud_values(state.device.model, state.device.did, payload)
            for key in keys:
                if key in values:
                    state.store.cached[key] = values[key]
                else:
                    state.store.cached.pop(key, None)
                    state.cached_rows.pop(key, None)
            state.cloud_data_error = None
        except (AuthenticationError, RateLimitError):
            raise
        except (DreameError, KeyError, TypeError, ValueError) as error:
            # A cloud setting failure cannot make appliance telemetry unavailable.
            state.cloud_data_error = type(error).__name__

    def _freshness(self, state, touched):
        now = monotonic()
        for key in touched:
            row = state.store.properties.get(key, {})
            if (row.get("last_code") in (None, 0, "0")
                    and row.get("last_source") in ("rpc", "mqtt")
                    and not row.get("last_reply_null", False)
                    and row.get("last_item", {}).get("value") is not None):
                state.timestamps[key] = now

    async def _read(self, state):
        # Exact model candidates remain retryable after null/empty/error replies.
        # A completed first request is not proof that every address was usable.
        initial = (list(VACUUM_INITIAL_READ_PAIRS)
                   if state.device.model == "dreame.vacuum.r5023a"
                   else laundry_read_pairs(state.device.model))
        pairs = {(row["siid"], row["piid"]) for row in state.store.properties.values()
                 if row.get("value") is not None
                 and (initial or row.get("last_code") in (None, 0, "0"))}
        if not pairs and not initial:
            return
        try:
            # Reserve exact candidates every refresh, then rotate valued addresses.
            # Unknown models receive only their successful observed coordinates.
            ordered = sorted(pairs - set(initial))
            capacity = 240 - len(initial)
            offset = int(monotonic() // 60) * capacity % len(ordered) if ordered else 0
            selected = initial + (ordered + ordered)[offset:offset + min(capacity, len(ordered))]
            rows = await self.api.read_properties(state.device, selected)
            # An unexpected coordinate is not evidence for a requested property.
            requested = set(selected)
            rows = [row for row in rows if isinstance(row, dict)
                    and property_coordinate(row) in requested]
            touched = state.store.merge_properties(rows)
            self._freshness(state, touched)
            state.read_error, state.initial_read_done = None, True
            schema = laundry_schema(state.device.model)
            if schema:
                state.schema_coverage = schema.coverage(state.store.properties)
            if initial:
                received = {property_coordinate(row) for row in rows}
                successful = {property_coordinate(row) for row in rows
                              if row.get("value") is not None and row.get("code") in (None, 0, "0")}
                state.initial_read_status = (
                    "complete" if set(initial).issubset(successful)
                    else "partial" if set(initial) & received else "empty")
        except (AuthenticationError, RateLimitError):
            raise
        except DreameError as error:
            state.read_error = type(error).__name__
            if initial:
                state.initial_read_status = "request_failed"

    async def async_start_subscriptions(self):
        self.subscriptions_enabled = True
        if self.stopped or not self.entry.data.get(CONF_MQTT, True):
            return
        for state in self.devices.values():
            if self.stopped:
                break
            if not state.present or state.subscription or (state.mqtt_attempt and monotonic() - state.mqtt_attempt < 300):
                continue
            state.mqtt_attempt = monotonic()
            subscription = DeviceSubscription(self.api, state.device,
                                              lambda payload, item=state: self._push(item, payload))
            # Own the client before startup can suspend or be cancelled.
            state.subscription = subscription
            try:
                await subscription.start()
                if self.stopped:
                    await subscription.stop()
                    state.subscription = None
                    break
                state.mqtt_error = None
            except AuthenticationError:
                await subscription.stop()
                state.subscription = None
                raise ConfigEntryAuthFailed("Dreame session requires reauthentication") from None
            except (DreameError, OSError, ValueError):
                await subscription.stop()
                state.subscription = None
                state.mqtt_error = "Verified MQTT connection failed"
            except BaseException:
                await subscription.stop()
                state.subscription = None
                raise
        self.async_update_listeners()

    @callback
    def _push(self, state, payload):
        if self.stopped:
            return
        touched = state.store.merge_push(payload)
        self._freshness(state, touched)
        schema = laundry_schema(state.device.model)
        if schema:
            state.schema_coverage = schema.coverage(state.store.properties)
        if not touched:
            # Unknown events remain in the store; the bus payload is redacted.
            self.hass.bus.async_fire(f"{DOMAIN}_message", {
                "config_entry_id": self.entry.entry_id,
                "device_key": self.device_key(state), "model": state.device.model,
                "message": redactor()(diagnostic_value(payload)),
            })
        # Notify without resetting the account's independent polling timer.
        self.async_update_listeners()

    def device_key(self, state):
        return f"dreame:{self.api.region}:{state.device.did}"

    async def async_stop(self):
        async with self._stop_lock:
            self.stopped = True
            current = asyncio.current_task()
            commands = [task for task in self._command_tasks if task is not current]
            for task in commands:
                task.cancel()
            if commands:
                await asyncio.gather(*commands, return_exceptions=True)
            await self.async_shutdown()
            subscriptions = [state.subscription for state in self.devices.values() if state.subscription]
            results = await asyncio.gather(*(sub.stop() for sub in subscriptions), return_exceptions=True)
            if any(isinstance(result, BaseException) for result in results):
                _LOGGER.warning("A Dreame MQTT client did not shut down cleanly")
            for state in self.devices.values():
                state.subscription = None
