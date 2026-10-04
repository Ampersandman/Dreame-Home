"""Numeric controls require complete source-defined bounds and step sizes."""

import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import ServiceValidationError

from .control import DreameControlEntity, add_control_entities


def numeric_bounds(definition):
    values = tuple(definition.get(key) for key in ("min", "max", "step"))
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        return None
    minimum, maximum, step = values
    return values if minimum < maximum and step > 0 and step <= maximum - minimum else None


def number_factory(coordinator, did, definition):
    # Current exact L9 schemas intentionally omit unbounded delay controls.
    return DreameLaundryNumber(coordinator, did, definition) if numeric_bounds(definition) else None


async def async_setup_entry(hass, entry, async_add_entities):
    add_control_entities(entry.runtime_data, entry, async_add_entities,
                         number_factory, kind="number")


class DreameLaundryNumber(DreameControlEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, did, definition):
        super().__init__(coordinator, did, definition)
        bounds = numeric_bounds(definition)
        if bounds is None:
            raise ValueError("Numeric control requires complete source bounds")
        self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step = bounds
        self._attr_native_unit_of_measurement = definition.get("unit")

    def valid_value(self, value):
        if type(value) not in (int, float) or not math.isfinite(value):
            return False
        if not self._attr_native_min_value <= value <= self._attr_native_max_value:
            return False
        steps = (value - self._attr_native_min_value) / self._attr_native_step
        return math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-9)

    @property
    def native_value(self):
        value = self.observed_value
        return value if self.valid_value(value) else None

    @property
    def available(self):
        return super().available and self.native_value is not None

    async def async_set_native_value(self, value):
        if not self.valid_value(value):
            raise ServiceValidationError("Choose a value within the supported range and step")
        await self.async_submit(value)
