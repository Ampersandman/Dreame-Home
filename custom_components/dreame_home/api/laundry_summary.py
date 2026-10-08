"""Compact read-only L9 appliance state, without I/O or cached payloads.

As with ``laundry_cycle_metrics``, callers must pass their fresh successful
RPC/MQTT observation mapping. Home Assistant supplies ``fresh_observations``
to enforce the observation clock before invoking this pure helper. Replies are
additionally checked here; no defaults, retained nulls, opaque properties or
write commands become reported appliance state.
"""

from collections.abc import Mapping

from .laundry import enum_label, laundry_schema
from .laundry_controls import control_definitions
from .laundry_programs import DRYER, WASHER, program_option_pairs
from .laundry_progress import laundry_cycle_metrics

_MODELS = {WASHER: ("washer", "2.12", "2.13"), DRYER: ("dryer", "2.9", "2.11")}


def _successful(row):
    """Further validate a row already selected by the caller's freshness clock."""
    if (not isinstance(row, Mapping) or row.get("has_value") is False
            or row.get("last_reply_null") or row.get("value") is None):
        return False
    code = row.get("last_code")
    if not (code is None or type(code) is int and code == 0
            or type(code) is str and code == "0"):
        return False
    if "last_source" in row and row["last_source"] not in ("rpc", "mqtt"):
        return False
    if "last_item" in row:
        latest = row["last_item"]
        if (not isinstance(latest, Mapping) or latest.get("value") is None
                or type(latest["value"]) is not type(row["value"])
                or latest["value"] != row["value"]):
            return False
    return True


def _integer(observations, coordinate):
    value = observations.get(coordinate, {}).get("value")
    return value if type(value) is int else None


def _enum(schema, observations, coordinate):
    value = _integer(observations, coordinate)
    definition = schema.definition(coordinate)
    if not definition or definition.get("value_list_inferred") is True:
        return None, None
    known = {row["value"] for row in definition.get("value_list") or ()
             if isinstance(row, Mapping) and type(row.get("value")) is int}
    if value not in known:
        return None, None
    return value, enum_label(definition, value)


def _minutes(observations, coordinate):
    value = _integer(observations, coordinate)
    return value if value is not None and value >= 0 else None


def _settings(model, schema, observations):
    settings = {}
    for definition in control_definitions(model):
        key, kind = definition["key"], definition["kind"]
        if key == "program" or kind not in ("select", "switch"):
            continue
        coordinate = definition.get("coordinate")
        source = schema.definition(coordinate)
        if not source:
            continue
        # A successful fresh reply is itself readable evidence. Some source
        # tables omit notify/read for parameters later reported by MQTT; no
        # such parameter is seeded from a default or its writable definition.
        value = _integer(observations, coordinate)
        options = {row["value"]: row["label"] for row in definition["options"]}
        if value not in options:
            continue
        if kind == "switch":
            # The existing switch encoder proves its exact 0/1 meaning. This
            # does not infer Boolean semantics for any unrelated raw property.
            if value in (0, 1):
                settings[key] = value == 1
        else:
            settings[key] = options[value]
    return settings


def laundry_appliance_summary(model, observations):
    """Return a bounded, JSON-serializable snapshot of an exact L9 appliance.

    ``observations`` is the caller's already-fresh mapping, never an account,
    device object or cached blob. Unknown/missing data stays ``None``; absent
    readable settings are omitted. Program options are the standard English
    profile, not a claim that a setting is currently writable. Durations and
    elapsed time use minutes; progress uses percent and the existing timeline
    helper's context/AI/terminal rules.
    """
    if not isinstance(model, str) or model not in _MODELS:
        return {}
    observations = ({key: row for key, row in observations.items() if _successful(row)}
                    if isinstance(observations, Mapping) else {})
    schema = laundry_schema(model)
    appliance_type, total_coordinate, remaining_coordinate = _MODELS[model]
    status, status_label = _enum(schema, observations, "2.1")
    if status not in (0, 1, 2, 3):
        status, status_label = None, None
    program, program_label = _enum(schema, observations, "2.3")
    # Match the select entity's exact option for a safe service round trip,
    # including the Dry/Care prefixes needed for duplicate garment names.
    if program is not None:
        program_label = dict((code, label) for label, code in program_option_pairs(model)).get(program)
    phase, phase_label = _enum(schema, observations, "2.4")
    fault, fault_label = _enum(schema, observations, "2.2")
    # Both exact plugins explicitly treat 2.2 == 0 as no fault. The dryer's
    # positive Fault enum intentionally omits zero; SubscribePage 525-529
    # supplies this no-fault identity rather than an inferred truthiness rule.
    if _integer(observations, "2.2") == 0:
        fault, fault_label = 0, "No fault"
    remaining = _minutes(observations, remaining_coordinate)
    if model == WASHER and remaining == 0 and (
            program is None or program == 0 and phase not in (5, 6)):
        remaining = None
    metrics = laundry_cycle_metrics(model, observations)
    return {
        "appliance_type": appliance_type,
        "status": status_label, "status_code": status,
        "is_running": status == 3 if status is not None else None,
        "is_paused": status == 2 if status is not None else None,
        "is_powered_on": status != 0 if status is not None else None,
        "program": program_label, "program_code": program,
        "program_options": [label for label, _ in program_option_pairs(model, include_additional=False)],
        "phase": phase_label, "phase_code": phase,
        "error": fault_label, "error_code": fault,
        "has_error": fault != 0 if fault is not None else None,
        "program_duration": _minutes(observations, total_coordinate),
        "remaining_time": remaining,
        "progress": metrics["progress"], "elapsed_time": metrics["elapsed_time"],
        "settings": _settings(model, schema, observations),
    }
