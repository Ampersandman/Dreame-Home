"""Read-only scalar telemetry, with exact-plugin labels where available."""

import math

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE

from .api.laundry import enum_label
from .entity import DreamePropertyEntity, add_observed_entities, scalar_state


async def async_setup_entry(hass, entry, async_add_entities):
    add_observed_entities(entry.runtime_data, entry, async_add_entities,
                          DreamePropertySensor, boolean=False)


class DreamePropertySensor(DreamePropertyEntity, SensorEntity):
    _expected_boolean = False

    def __init__(self, coordinator, did, key, pointer=None):
        super().__init__(coordinator, did, key, pointer)
        definition = self.definition
        if definition and isinstance(definition.get("unit"), str) and not definition.get("value_list"):
            self._attr_native_unit_of_measurement = definition["unit"]
        if self.device_state.device.model == "dreame.vacuum.r5023a" and key == "3.1" and pointer is None:
            self._attr_name = "Battery"
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_entity_category = None

    @property
    def numeric(self):
        return (self.device_class == SensorDeviceClass.BATTERY
                or getattr(self, "_attr_native_unit_of_measurement", None) is not None)

    def _numeric_value(self):
        value = self.value
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or isinstance(value, float) and not math.isfinite(value)):
            return None
        if self.device_class == SensorDeviceClass.BATTERY and not 0 <= value <= 100:
            return None
        return value

    @property
    def available(self):
        return super().available and (not self.numeric or self._numeric_value() is not None)

    @property
    def native_value(self):
        # HA requires numeric native values whenever a unit or numeric device
        # class is present. Keep structured observations on attributes/leaves.
        if self.numeric:
            return self._numeric_value()
        if "compound" in self.observation and self.pointer is None:
            return "structured"
        label = enum_label(self.definition, self.value)
        return label if label is not None else scalar_state(self.value)
