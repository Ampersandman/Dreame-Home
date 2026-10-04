"""Source-defined laundry flags with observed readback."""

from homeassistant.components.switch import SwitchEntity

from .control import DreameControlEntity, add_control_entities


async def async_setup_entry(hass, entry, async_add_entities):
    add_control_entities(entry.runtime_data, entry, async_add_entities,
                         DreameLaundrySwitch, kind="switch")


class DreameLaundrySwitch(DreameControlEntity, SwitchEntity):
    @property
    def is_on(self):
        value = self.observed_value
        return bool(value) if type(value) is int and value in (0, 1) else None

    @property
    def available(self):
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs):
        await self.async_submit(True)

    async def async_turn_off(self, **kwargs):
        await self.async_submit(False)
