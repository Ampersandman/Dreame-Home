"""Common boundaries for exact-model laundry controls."""

from collections import Counter
from urllib.parse import quote

from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import EntityCategory

from .api.laundry_controls import (
    control_available,
    control_definitions,
    control_options,
    prepare_control_write,
)
from .api.laundry_programs import program_catalog, program_option_pairs
from .api.presentation import control_presentation
from .entity import DreameEntity, presentation_language


def option_pairs(options):
    """Build a bijective display label/code table without coercing wire values."""
    if not isinstance(options, (list, tuple)) or not 0 < len(options) <= 256:
        return ()
    pairs = []
    for option in options:
        if (not isinstance(option, dict) or type(option.get("value")) is not int
                or not isinstance(option.get("label"), str) or not option["label"].strip()):
            return ()
        pairs.append((option["label"], option["value"]))
    if len({code for _, code in pairs}) != len(pairs):
        return ()
    counts = Counter(label for label, _ in pairs)
    pairs = tuple((f"{label} ({code})" if counts[label] > 1 else label, code)
                  for label, code in pairs)
    return pairs if len({label for label, _ in pairs}) == len(pairs) else ()


def add_control_entities(coordinator, entry, async_add_entities, factory, *, kind):
    """Register source-defined controls once, including later device discovery."""
    known = set()

    @callback
    def discover():
        if coordinator.stopped or coordinator.entity_discovery_suspended:
            return
        entities = []
        for did, state in coordinator.devices.items():
            for definition in control_definitions(state.device.model):
                identity = did, definition["key"]
                if definition["kind"] != kind or identity in known:
                    continue
                entity = factory(coordinator, did, definition)
                if entity is not None:
                    known.add(identity)
                    entities.append(entity)
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DreameControlEntity(DreameEntity):
    """A control whose displayed state changes only after an observation."""

    _attr_entity_category = None

    def __init__(self, coordinator, did, definition):
        self.definition = definition
        self.key = definition["key"]
        self.model = coordinator.devices[did].device.model
        suffix = f"control:{definition['kind']}:{quote(self.key, safe='')}"
        presentation = control_presentation(self.model, self.key, presentation_language(coordinator))
        category = presentation.get("entity_category", definition.get("entity_category"))
        self._attr_entity_category = EntityCategory.CONFIG if category == "config" else None
        super().__init__(coordinator, did, suffix, presentation.get("label", definition["label"]))
        if presentation.get("icon"):
            self._attr_icon = presentation["icon"]
        self._attr_entity_registry_enabled_default = presentation.get("enabled_default", True)

    @property
    def observation(self):
        coordinate = self.definition.get("coordinate")
        return self.device_state.store.properties.get(coordinate, {})

    @property
    def observed_value(self):
        row = self.observation
        code = row.get("last_code")
        if not (code is None or type(code) is int and code == 0
                or type(code) is str and code == "0"):
            return None
        return row.get("value")

    @property
    def control_observations(self):
        return self.coordinator.control_observations(self.did)

    @property
    def available(self):
        return (self.device_state.device.model == self.model
                and self.coordinator.control_ready(self.did)
                and control_available(self.model, self.key, self.control_observations))

    async def async_submit(self, value=None):
        """Validate user input locally, then submit to the serialized gateway."""
        if not self.available:
            raise ServiceValidationError("This control requires fresh available device state")
        try:
            prepare_control_write(self.model, self.key, value, self.control_observations)
        except (ValueError, TypeError) as error:
            raise ServiceValidationError("This choice is unavailable for the current device state") from error
        await self.coordinator.async_execute_control(self.did, self.key, value)

    def selectable_pairs(self):
        """Keep duplicate-label suffixes stable when program filters narrow choices."""
        pairs = self.display_option_pairs()
        if not pairs:
            return ()
        allowed = control_options(self.model, self.key, self.control_observations)
        if not isinstance(allowed, (list, tuple)):
            return ()
        codes = set()
        source = {option["value"]: option["label"] for option in self.definition["options"]}
        for option in allowed:
            if (not isinstance(option, dict) or type(option.get("value")) is not int
                    or option["value"] in codes or option.get("label") != source.get(option["value"])):
                return ()
            codes.add(option["value"])
        return tuple((label, code) for label, code in pairs if code in codes)

    def display_option_pairs(self):
        """Use English app names after verifying their exact source identity."""
        pairs = option_pairs(self.definition.get("options"))
        if self.key != "program" or not pairs:
            return pairs
        source = {row["value"]: row["source_label"] for row in program_catalog(self.model, include_additional=True)}
        options = self.definition["options"]
        if not source or any(source.get(row["value"]) != row["label"] for row in options):
            return pairs
        return program_option_pairs(self.model)

    @property
    def extra_state_attributes(self):
        value = self.observed_value
        attributes = {"control_key": self.key, "raw_code": value if type(value) is int else None}
        if self.definition.get("coordinate"):
            attributes["coordinate"] = self.definition["coordinate"]
        if self.key == "program":
            options = dict((code, label) for label, code in self.display_option_pairs())
            allowed = {code for _, code in self.selectable_pairs()}
            fields = ("value", "label", "labels", "group", "group_labels", "reference_duration_minutes", "reference_duration_kind")
            attributes["program_catalog"] = [{**{key: row[key] for key in fields},
                                               "option": options.get(row["value"]),
                                               "selectable": row["value"] in allowed}
                                              for row in program_catalog(self.model)]
        return attributes
