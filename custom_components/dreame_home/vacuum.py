"""Native vacuum controls for the confirmed exact r5023a model."""

from homeassistant.components.vacuum import StateVacuumEntity, VacuumActivity, VacuumEntityFeature
from homeassistant.core import callback

from .api.vacuum_controls import vacuum_command_available, vacuum_control_supported, vacuum_state
from .entity import DreameEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    @callback
    def discover():
        if coordinator.stopped or coordinator.entity_discovery_suspended:
            return
        entities = []
        for did, state in coordinator.devices.items():
            if state.present and did not in known and vacuum_control_supported(state.device.model):
                known.add(did)
                entities.append(DreameVacuum(coordinator, did))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DreameVacuum(DreameEntity, StateVacuumEntity):
    """Use HA 2026.9 activity, with state derived only from observations."""

    def __init__(self, coordinator, did):
        super().__init__(coordinator, did, "vacuum", None)

    @property
    def projected(self):
        return vacuum_state(self.device_state.device.model, self.device_state.store.properties)

    @property
    def activity(self):
        value = self.projected["activity"]
        return VacuumActivity(value) if value is not None else None

    @property
    def available(self):
        return (super().available and not self.coordinator.stopped
                and not self.coordinator.entity_discovery_suspended
                and self.device_state.online is not False
                and self.projected["supported"] and self.activity is not None)

    @property
    def supported_features(self):
        features = VacuumEntityFeature.STATE
        if self.coordinator.control_ready(self.did):
            observations = self.coordinator.control_observations(self.did)
            for command, feature in (
                ("start", VacuumEntityFeature.START), ("pause", VacuumEntityFeature.PAUSE),
                ("stop", VacuumEntityFeature.STOP), ("return_to_base", VacuumEntityFeature.RETURN_HOME),
                ("set_fan_speed", VacuumEntityFeature.FAN_SPEED),
            ):
                if vacuum_command_available(self.device_state.device.model, command, observations):
                    features |= feature
        return features

    @property
    def fan_speed(self):
        return self.projected["fan_speed"]

    @property
    def fan_speed_list(self):
        return self.projected["fan_speed_list"] if VacuumEntityFeature.FAN_SPEED in self.supported_features else []

    @property
    def extra_state_attributes(self):
        state = self.projected
        return {key: state[key] for key in ("battery_level", "state_code", "status_code", "task_code", "error_code")
                if state[key] is not None}

    async def async_start(self):
        await self.coordinator.async_execute_vacuum(self.did, "start")

    async def async_pause(self):
        await self.coordinator.async_execute_vacuum(self.did, "pause")

    async def async_stop(self, **kwargs):
        await self.coordinator.async_execute_vacuum(self.did, "stop")

    async def async_return_to_base(self, **kwargs):
        await self.coordinator.async_execute_vacuum(self.did, "return_to_base")

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        await self.coordinator.async_execute_vacuum(self.did, "set_fan_speed", fan_speed)
