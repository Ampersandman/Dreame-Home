"""Stable entities for observed property coordinates and JSON Pointer leaves."""

import math
import json
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any
from urllib.parse import quote, unquote

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from .api.observations import compound_fields, entity_fields
from .api.laundry import enum_label, laundry_definition
from .api.privacy import SENSITIVE, redactor
from .api.telemetry import telemetry_metadata
from .api.presentation import control_presentation, property_presentation
from .const import DOMAIN


def presentation_language(coordinator):
    """Keep integration-owned labels English without changing the HA locale."""
    return "en"


@callback
def async_migrate_entity_presentation(hass, entry):
    """Update categories and defaults without replacing user customizations.

    Legacy uncustomized duplicate/raw rows are integration-hidden. User-hidden,
    user-disabled and customized rows remain untouched. New diagnostic defaults
    are handled on entity creation; existing automations keep their entities.
    Newly promoted program/remote-start readbacks override only their former
    integration-disabled default, never a user's disabled setting.
    """
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    prefixes = {coordinator.device_key(state) + ":": state.device.model
                for state in coordinator.devices.values()}
    for row in er.async_entries_for_config_entry(registry, entry.entry_id):
        if row.platform != DOMAIN:
            continue
        prefix = next((key for key in prefixes if row.unique_id.startswith(key)), None)
        if prefix is None:
            continue
        suffix, model = row.unique_id[len(prefix):], prefixes[prefix]
        presentation = None
        if suffix.startswith("control:"):
            parts = suffix.split(":", 2)
            if len(parts) == 3:
                presentation = control_presentation(model, unquote(parts[2]))
        elif suffix.startswith("prop:") and ":state" in suffix:
            coordinate, _, tail = suffix[5:].partition(":state")
            presentation = property_presentation(model, unquote(coordinate), tail or None)
        elif suffix.startswith("cycle:"):
            presentation = {"entity_category": None}
        if not presentation:
            continue
        category = presentation.get("entity_category")
        category = EntityCategory.CONFIG if category == "config" else EntityCategory.DIAGNOSTIC if category == "diagnostic" else None
        changes = {}
        if row.entity_category != category:
            changes["entity_category"] = category
        customized = bool(row.name or row.icon or row.options
                          or getattr(row, "labels", ()) or getattr(row, "aliases", ())
                          or getattr(row, "area_id", None) or getattr(row, "categories", {})
                          or row.disabled_by == er.RegistryEntryDisabler.USER)
        if presentation.get("hide_legacy") and row.hidden_by is None and not customized:
            changes["hidden_by"] = er.RegistryEntryHider.INTEGRATION
        elif not presentation.get("hide_legacy") and row.hidden_by == er.RegistryEntryHider.INTEGRATION:
            changes["hidden_by"] = None
        if (presentation.get("promote_default")
                and row.disabled_by == er.RegistryEntryDisabler.INTEGRATION):
            changes["disabled_by"] = None
        if changes:
            registry.async_update_entity(row.entity_id, **changes)


def property_definition(model, key, pointer=None):
    definition = laundry_definition(model, key, pointer)
    metadata = telemetry_metadata(model, key, pointer)
    return {**(definition or {}), **metadata} if metadata else definition


def fresh_observations(state, *, max_age=180):
    """Select current RPC/MQTT replies for derived read-only telemetry."""
    now = monotonic()
    timestamps = getattr(state, "timestamps", {})
    return {key: row for key, row in state.store.properties.items()
            if row.get("value") is not None and not row.get("last_reply_null", False)
            and row.get("last_source") in ("rpc", "mqtt")
            and row.get("last_item", {}).get("value") is not None
            and (row.get("last_code") is None
                 or type(row.get("last_code")) is int and row["last_code"] == 0
                 or type(row.get("last_code")) is str and row["last_code"] == "0")
            and key in timestamps and 0 <= now - timestamps[key] <= max_age}


def sensitive_path(key, pointer=None):
    parts = [key[7:] if key.startswith("cached:") else key]
    if pointer:
        parts.extend(part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/"))
    return any(part.lstrip("@").lower().replace("_", "").replace("-", "") in SENSITIVE for part in parts)


def cached_observation(value):
    row = {"value": value, "last_code": 0, "source": "cached"}
    compound = value
    if isinstance(value, str) and len(value) <= 262144 and value.lstrip().startswith(("{", "[")):
        try:
            compound = json.loads(value)
        except (ValueError, RecursionError):
            pass
    if isinstance(compound, (dict, list)):
        fields, truncated = compound_fields(compound)
        stable_fields, stable_truncated = entity_fields(compound)
        row.update(compound=compound, compound_fields=fields, compound_truncated=truncated,
                   entity_fields=stable_fields, entity_fields_truncated=stable_truncated)
    return row


def cached_row(state, key):
    value = state.store.cached.get(key)
    existing = state.cached_rows.get(key)
    if existing is None or existing[0] is not value:
        existing = value, cached_observation(redactor()(value))
        state.cached_rows[key] = existing
    row = existing[1]
    if key in getattr(state, "cloud_data_keys", ()):
        row["source"] = "cloud_userdata"
        row["last_code"] = None
    return row


def readings(state):
    """Yield only successful observations; never manufacture missing values."""
    for key, row in state.store.properties.items():
        if "value" not in row:
            continue
        yield key, None, row["value"]
        for pointer, value in row.get("entity_fields", {}).items():
            if not sensitive_path(key, pointer):
                yield key, pointer, value
    for key in state.store.cached:
        if sensitive_path(f"cached:{key}"):
            continue
        row = cached_row(state, key)
        yield f"cached:{key}", None, row["value"]
        for pointer, leaf in row.get("entity_fields", {}).items():
            if not sensitive_path(f"cached:{key}", pointer):
                yield f"cached:{key}", pointer, leaf


def add_observed_entities(coordinator, entry, async_add_entities, factory, *, boolean):
    known = set()

    @callback
    def discover():
        if (getattr(coordinator, "stopped", False)
                or getattr(coordinator, "entity_discovery_suspended", False)):
            return
        entities = []
        for did, state in coordinator.devices.items():
            for key, pointer, value in readings(state):
                identity = did, key, pointer
                if value is None:
                    continue
                platform = coordinator.entity_platforms.setdefault(identity, isinstance(value, bool))
                if identity in known or platform != boolean:
                    continue
                known.add(identity)
                entities.append(factory(coordinator, did, key, pointer))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DreameEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, did, suffix, label):
        super().__init__(coordinator)
        self.did = did
        state = coordinator.devices[did]
        self._attr_unique_id = f"{coordinator.device_key(state)}:{suffix}"
        self._attr_name = label

    @property
    def device_state(self):
        return self.coordinator.devices[self.did]

    @property
    def device_info(self):
        state = self.device_state
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_key(state))},
            name=state.device.name, manufacturer="Dreame", model=state.device.model,
            sw_version=state.device.raw.get("ver") or state.device.raw.get("fwVersion"),
        )

    @property
    def available(self):
        state = self.device_state
        return state.present and (self.coordinator.last_update_success or
                                 bool(state.subscription and state.subscription.connected))


class DreamePropertyEntity(DreameEntity):
    _expected_boolean = False

    def __init__(self, coordinator, did, key, pointer=None):
        self.key, self.pointer = key, pointer
        self._sanitize = redactor()
        label = (f"Cloud key {key[7:]}" if key.startswith("cached:") else f"Property {key}")
        label += f" {pointer}" if pointer is not None else ""
        definition = property_definition(coordinator.devices[did].device.model, key, pointer)
        if definition:
            label = definition.get("label") or definition.get("name") or label
        presentation = property_presentation(coordinator.devices[did].device.model, key, pointer,
                                             presentation_language(coordinator))
        label = presentation.get("label", label)
        suffix = f"prop:{quote(key, safe='.')}:state"
        suffix += f":json:{quote(pointer, safe='')}" if pointer is not None else ""
        super().__init__(coordinator, did, suffix, label)
        if presentation.get("icon"):
            self._attr_icon = presentation["icon"]
        self._attr_entity_category = None if presentation["entity_category"] is None else EntityCategory.DIAGNOSTIC
        # The root preserves complete structured data in attributes. Leaf entities
        # are enabled; disable the large duplicate root by default in the registry.
        self._attr_entity_registry_enabled_default = (presentation["enabled_default"]
            and not (pointer is None and "compound" in self.observation))

    @property
    def observation(self):
        if self.key.startswith("cached:"):
            return cached_row(self.device_state, self.key[7:])
        return self.device_state.store.properties.get(self.key, {})

    @property
    def definition(self):
        return property_definition(self.device_state.device.model, self.key, self.pointer)

    @property
    def cloud_setting(self):
        return (self.key.startswith("cached:")
                and self.key[7:] in getattr(self.device_state, "cloud_data_keys", ()))

    @property
    def value(self) -> Any:
        if self.pointer is not None:
            return self.observation.get("entity_fields", {}).get(self.pointer)
        return self.observation.get("value")

    @property
    def available(self):
        row = self.observation
        return (super().available and (self.device_state.online is not False or self.cloud_setting)
                and not (self.cloud_setting and getattr(self.device_state, "cloud_data_error", None))
                and (self.key.startswith("cached:") or self.device_state.read_error is None
                     or row.get("last_source") == "mqtt") and "value" in row
                and row.get("last_code") in (None, 0, "0")
                and (self.pointer is None or self.pointer in row.get("entity_fields", {}))
                and (self.value is None or isinstance(self.value, bool) == self._expected_boolean))

    @property
    def extra_state_attributes(self):
        row = self.observation
        attributes = {"siid": row.get("siid"), "piid": row.get("piid"),
                      "source": row.get("source"), "last_code": row.get("last_code")}
        if self.key.startswith("cached:"):
            attributes["cloud_key"] = self.key[7:]
            if self.key[7:] in getattr(self.device_state, "cloud_data_keys", ()):
                attributes["cloud_data_error"] = getattr(self.device_state, "cloud_data_error", None)
        if row.get("last_reply_null"):
            attributes["last_reply_null"] = True
        if self.pointer is not None:
            attributes["field_path"] = self.pointer
        elif "compound" in row or isinstance(self.value, str) and len(self.value) > 255:
            attributes["raw_value"] = self._sanitize(self.value)
            attributes["projection_truncated"] = (row.get("compound_truncated", False)
                                                   or row.get("entity_fields_truncated", False))
        definition = self.definition
        if definition:
            attributes["schema_name"] = definition.get("name")
            attributes["schema_live_verified"] = definition.get("live_verified") is True
            if enum_label(definition, self.value) is not None:
                attributes["raw_code"] = self.value
        if self.key == "2.1" and self.pointer is None:
            attributes["raw_code"] = self.value if type(self.value) is int else None
            fresh = self.key in fresh_observations(self.device_state)
            attributes["observation_fresh"] = fresh
            received = getattr(self.device_state, "timestamps", {}).get(self.key)
            age = monotonic() - received if received is not None else None
            attributes["observed_at"] = ((datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
                                         if age is not None and age >= 0 else None)
        return attributes


def scalar_state(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return "structured"
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str) and len(value) > 255:
        return "long_text"
    return value
