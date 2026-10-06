"""Allowlisted diagnostics with raw account envelopes excluded."""

from time import monotonic

from .api.privacy import redactor
from .api.laundry_controls import control_available, control_definitions
from .api.vacuum_controls import vacuum_command_available, vacuum_control_supported


def control_diagnostics(coordinator, state):
    """Report named support and current eligibility without identities or values."""
    model = state.device.model
    observations = coordinator.control_observations(state.device.did)
    ready = coordinator.control_ready(state.device.did)
    definitions = control_definitions(model)
    supported = [definition["key"] for definition in definitions]
    eligible = [key for key in supported if ready and control_available(model, key, observations)]
    if vacuum_control_supported(model):
        supported = ["start", "pause", "stop", "return_to_base", "set_fan_speed"]
        eligible = [key for key in supported if ready and vacuum_command_available(model, key, observations)]
    return {"supported_commands": supported, "available_commands": eligible,
            "gateway_ready": ready, "fresh_coordinate_count": len(observations)}


def diagnostic_value(value):
    # Unknown property text may contain personal data or a credential under an
    # unidentified coordinate. Preserve shape/numbers, omit arbitrary strings.
    if isinstance(value, dict):
        return {key: diagnostic_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [diagnostic_value(item) for item in value]
    if isinstance(value, str):
        return "<text omitted>"
    return value


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    devices = []
    now = monotonic()
    for state in coordinator.devices.values():
        properties = {key: {
            "siid": row["siid"], "piid": row["piid"],
            "value": diagnostic_value(row.get("compound", row.get("value"))),
            "has_value": "value" in row, "last_code": row.get("last_code"),
            "last_reply_null": row.get("last_reply_null", False),
            "last_source": (row.get("last_source") if row.get("last_source")
                            in ("rpc", "mqtt", "listing", "metadata") else None),
            "has_current_reply_value": row.get("last_item", {}).get("value") is not None,
            "last_value_age_seconds": (max(0, round(now - state.timestamps[key]))
                                       if key in state.timestamps else None),
            "source": row.get("source"), "compound_truncated": row.get("compound_truncated", False),
        } for key, row in state.store.properties.items()}
        devices.append({
            "model": state.device.model,
            "firmware": state.device.raw.get("ver") or state.device.raw.get("fwVersion"),
            "present": state.present, "online": state.online,
            "metadata_error": state.metadata_error, "read_error": state.read_error,
            "initial_read_status": state.initial_read_status,
            "schema_coverage": state.schema_coverage,
            "cloud_data_error": state.cloud_data_error,
            "cloud_data_keys": sorted(state.cloud_data_keys),
            "mqtt_connected": bool(state.subscription and state.subscription.connected),
            "command_busy": state.command_busy,
            "last_command_status": state.last_command_status,
            "controls": control_diagnostics(coordinator, state),
            "properties": properties, "event_count": len(state.store.events),
            "cached_key_count": len(state.store.cached),
            "dropped_properties": state.store.dropped_properties,
            "dropped_events": state.store.dropped_events,
        })
    return redactor()({"region": coordinator.api.region, "discovery_complete": coordinator.discovery_complete,
                       "api_update_success": coordinator.last_update_success, "devices": devices})
