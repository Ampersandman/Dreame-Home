"""Read-only scalar telemetry, with exact-plugin labels where available."""

import math

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import callback

from .api.laundry import enum_label
from .api.laundry_progress import laundry_cycle_metrics, progress_definitions
from .api.vacuum_telemetry import vacuum_telemetry_available
from .api.presentation import cycle_presentation
from .entity import DreameEntity, DreamePropertyEntity, add_observed_entities, fresh_observations, presentation_language, scalar_state


async def async_setup_entry(hass, entry, async_add_entities):
    add_observed_entities(entry.runtime_data, entry, async_add_entities,
                          DreamePropertySensor, boolean=False)
    add_progress_entities(entry.runtime_data, entry, async_add_entities)


def add_progress_entities(coordinator, entry, async_add_entities):
    known = set()

    @callback
    def discover():
        if coordinator.stopped or coordinator.entity_discovery_suspended:
            return
        entities = []
        for did, state in coordinator.devices.items():
            for definition in progress_definitions(state.device.model):
                identity = did, definition["key"]
                if identity in known or not state.present:
                    continue
                # The device must have observed cycle context before adding a
                # derived entity, even if the current context has since expired.
                if not any("value" in state.store.properties.get(key, {})
                           for key in definition["required_coordinates"]):
                    continue
                known.add(identity)
                entities.append(DreameCycleSensor(coordinator, did, definition))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DreameCycleSensor(DreameEntity, SensorEntity):
    _attr_entity_category = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, did, definition):
        self.definition = definition
        self.key = definition["key"]
        self.model = coordinator.devices[did].device.model
        label = cycle_presentation(self.key, presentation_language(coordinator)).get("label", definition["name"])
        super().__init__(coordinator, did, f"cycle:{self.key}", label)
        self._attr_native_unit_of_measurement = definition["unit"]
        self._attr_suggested_display_precision = 1 if self.key == "progress" else 0
        if self.key == "elapsed_time":
            self._attr_device_class = SensorDeviceClass.DURATION

    @property
    def native_value(self):
        return laundry_cycle_metrics(self.model, fresh_observations(self.device_state)).get(self.key)

    @property
    def available(self):
        return (super().available and self.device_state.device.model == self.model
                and self.device_state.online is not False and not self.coordinator.stopped
                and not self.coordinator.entity_discovery_suspended and self.native_value is not None)

    @property
    def extra_state_attributes(self):
        return {"derived": True, "cycle_metric": self.key, "required_coordinates": self.definition["required_coordinates"],
                "duration_coordinates": self.definition["duration_coordinates"]}


class DreamePropertySensor(DreamePropertyEntity, SensorEntity):
    _expected_boolean = False

    def __init__(self, coordinator, did, key, pointer=None):
        super().__init__(coordinator, did, key, pointer)
        definition = self.definition
        if definition and isinstance(definition.get("unit"), str) and not definition.get("value_list"):
            self._attr_native_unit_of_measurement = definition["unit"]
        if definition and definition.get("device_class") == "duration":
            self._attr_device_class = SensorDeviceClass.DURATION
        elif definition and definition.get("device_class") == "area":
            self._attr_device_class = SensorDeviceClass.AREA
        if definition and definition.get("operational"):
            self._attr_entity_category = None
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
        definition = self.definition or {}
        if "minimum" in definition and value < definition["minimum"]:
            return None
        if "maximum" in definition and value > definition["maximum"]:
            return None
        if definition.get("ai_zero_is_unknown") and value == 0:
            context = fresh_observations(self.device_state)
            program = context.get("2.3", {}).get("value")
            phase = context.get("2.4", {}).get("value")
            if type(program) is not int or program == 0 and phase not in (5, 6):
                return None
        return value

    @property
    def available(self):
        if not super().available or self.numeric and self._numeric_value() is None:
            return False
        if (self.device_state.device.model == "dreame.vacuum.r5023a" and self.pointer is None
                and self.key in ("4.2", "4.3", "4.63", "4.64")):
            context = fresh_observations(self.device_state)
            return (self.key in context and vacuum_telemetry_available(
                self.device_state.device.model, self.key, context))
        return True

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
