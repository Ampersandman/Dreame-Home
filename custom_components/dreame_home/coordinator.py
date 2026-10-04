"""Account discovery and bounded, read-only property observation."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from time import monotonic

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.exceptions import AuthenticationError, DreameError, RateLimitError
from .api.laundry import laundry_cloud_read_keys, laundry_cloud_values, laundry_read_pairs, laundry_schema
from .api.models import Device
from .api.mqtt import DeviceSubscription
from .api.observations import ObservationStore, VACUUM_INITIAL_READ_PAIRS, property_coordinate
from .api.privacy import redactor
from .const import CONF_MQTT, DOMAIN
from .diagnostics import diagnostic_value

_LOGGER = logging.getLogger(__name__)


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


class DreameCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        super().__init__(hass, _LOGGER, name="Dreame Home", config_entry=entry,
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

    async def _async_update_data(self):
        try:
            if not self.discovery_complete or monotonic() - self.last_inventory >= 600:
                await self._discover()
            for state in self.devices.values():
                if state.present and state.online is not False:
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
        pairs = {(row["siid"], row["piid"]) for row in state.store.properties.values()
                 if "value" in row and row.get("last_code") in (None, 0, "0")}
        initial = []
        if not state.initial_read_done:
            initial = (list(VACUUM_INITIAL_READ_PAIRS)
                       if state.device.model == "dreame.vacuum.r5023a"
                       else laundry_read_pairs(state.device.model))
        if not pairs and not initial:
            return
        try:
            # Each refresh reads at most 240 observed addresses; rotate if needed.
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
            await self.async_shutdown()
            subscriptions = [state.subscription for state in self.devices.values() if state.subscription]
            results = await asyncio.gather(*(sub.stop() for sub in subscriptions), return_exceptions=True)
            if any(isinstance(result, BaseException) for result in results):
                _LOGGER.warning("A Dreame MQTT client did not shut down cleanly")
            for state in self.devices.values():
                state.subscription = None
