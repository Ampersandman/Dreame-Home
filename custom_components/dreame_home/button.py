"""Source-proven laundry actions, submitted only on an explicit press."""

from homeassistant.components.button import ButtonEntity

from .control import DreameControlEntity, add_control_entities


async def async_setup_entry(hass, entry, async_add_entities):
    add_control_entities(entry.runtime_data, entry, async_add_entities,
                         DreameLaundryButton, kind="button")


class DreameLaundryButton(DreameControlEntity, ButtonEntity):
    _attr_entity_category = None

    async def async_press(self):
        await self.async_submit()
