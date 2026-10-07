"""Observed JSON booleans and independently reported connectivity."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .entity import DreameEntity, DreamePropertyEntity, add_observed_entities


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    add_observed_entities(coordinator, entry, async_add_entities,
                          DreamePropertyBinarySensor, boolean=True)
    known = set()

    @callback
    def discover():
        entities = []
        for did in coordinator.devices.keys() - known:
            known.add(did)
            entities.extend((DreameOnline(coordinator, did), DreameMqttConnected(coordinator, did)))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DreamePropertyBinarySensor(DreamePropertyEntity, BinarySensorEntity):
    _expected_boolean = True

    @property
    def is_on(self):
        return self.value if isinstance(self.value, bool) else None


class DreameOnline(DreameEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, did):
        super().__init__(coordinator, did, "cloud_online", "Cloud reported online")

    @property
    def is_on(self):
        return self.device_state.online


class DreameMqttConnected(DreameEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, did):
        super().__init__(coordinator, did, "mqtt_connected", "MQTT connected")

    @property
    def is_on(self):
        subscription = self.device_state.subscription
        return bool(subscription and subscription.connected)

    @property
    def extra_state_attributes(self):
        state = self.device_state
        return {"error": state.mqtt_error or (state.subscription.last_error if state.subscription else None)}
