"""Exact plugin choices, filtered by the current laundry program."""

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import ServiceValidationError

from .control import DreameControlEntity, add_control_entities, option_pairs


async def async_setup_entry(hass, entry, async_add_entities):
    add_control_entities(entry.runtime_data, entry, async_add_entities,
                         DreameLaundrySelect, kind="select")


class DreameLaundrySelect(DreameControlEntity, SelectEntity):
    @property
    def options(self):
        return [label for label, _ in self.selectable_pairs()]

    @property
    def current_option(self):
        value = self.observed_value
        if type(value) is not int:
            return None
        return next((label for label, code in option_pairs(self.definition.get("options"))
                     if code == value), None)

    @property
    def available(self):
        return super().available and self.current_option is not None

    async def async_select_option(self, option):
        if not isinstance(option, str):
            raise ServiceValidationError("Choose one of the available options")
        code = next((code for label, code in self.selectable_pairs() if label == option), None)
        if code is None:
            raise ServiceValidationError("Choose one of the available options")
        await self.async_submit(code)
