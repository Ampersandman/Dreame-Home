"""Pure, bounded control encoders for the two exact official L9 plugins.

This module performs no I/O. It never guesses a writable property from telemetry,
exposes raw writes, powers on before a command, or starts after changing settings.
The gateway must bind the actual DID and enforce online/freshness requirements.

Source restrictions are complemented by an intentionally narrower policy: program
parameters may change only in standby. The app's editing flow otherwise pauses a
cycle before a bulk write; a single HA setting must not silently pause/resume it.
Defaults with null entries hide settings; ``filter`` entries exclude raw codes.
Delay durations lack a complete source range and are omitted. Stain selection
also changes temperature to sentinel999 and local remembered state, so is omitted.
Dryer night3.11/3.13 is ambiguous,4.7 is unknown, and export UI hides sanitize3.3.
Cloud automatic updates lack a verified HTTP write contract here. Add-clothes and
report-all actions are intentionally absent. Source catalogues remain unchanged.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any, Mapping

from .catalog import load_catalog
from .laundry_programs import program_catalog
from .presentation import control_presentation

WASHER = "dreame.washer.l9nacn"
DRYER = "dreame.dryer.l9nacn"
_CATALOGS = {WASHER: "l9_washer", DRYER: "l9_dryer"}


class ControlValidationError(ValueError):
    """A named source control cannot safely encode this request/current state."""


# Stable entity keys, exact coordinates, and source configuration field names.
# Washer storageToProgram: official iOS plugin83, utils/index lines837-852.
# Dryer storageToProgram: official iOS plugin130, utils/index lines826-841.
# These are encoder bindings, not inferred Boolean meanings of observed values.
_PROPERTY_CONTROLS = {
    WASHER: (
        ("program", "select", 2, 3, None),
        ("temperature", "select", 2, 8, "temperature"),
        ("extra_time", "select", 2, 14, "addTime"),
        ("water_level", "select", 2, 15, "waterLevel"),
        ("rinse_cycles", "select", 2, 16, "numberOfRinses"),
        ("spin_speed", "select", 2, 18, "rotateSpeed"),
        ("detergent_dosing", "select", 2, 24, "intelligent"),
        ("softener_dosing", "select", 2, 25, "compliant"),
        ("child_lock", "switch", 3, 4, None),
        ("fresh_air_circulation", "switch", 3, 6, "newWind"),
        ("dynamic_rinse", "switch", 3, 7, "runningWaterMode"),
        ("speed_mode", "switch", 3, 8, "accelerate"),
        ("night_mode", "switch", 3, 9, "night"),
    ),
    DRYER: (
        ("program", "select", 2, 3, None),
        ("dryness_level", "select", 2, 6, "drynessLevel"),
        ("airflow", "select", 2, 5, "airflow"),
        ("extra_time", "select", 2, 10, "addTime"),
        ("steam_level", "select", 2, 13, "steam"),
        ("child_lock", "switch", 3, 4, "ChildColck"),
        ("wrinkle_care", "switch", 3, 8, "anticrease"),
        ("low_temperature", "switch", 3, 12, "lowtempdry"),
        ("speed_mode", "switch", 3, 10, "Accelerate"),
    ),
}

_OMITTED = {
    WASHER: {
        "stain_type": "Changes temperature to sentinel999 and remembered local configuration.",
        "delay_time": "No complete source bounds; scheduling includes multiple ordered commands.",
        "delay_enabled": "Enabling requires the scheduling flow and duration, not an isolated flag.",
        "automatic_firmware_updates": "Native cloud helper is known; HTTP write DTO is unverified.",
        "add_clothes": "Separate physical-operation constraints have not been extracted completely.",
        "report_all": "An action rather than a user setting; discovery never invokes it.",
    },
    DRYER: {
        "night_mode": "Subscription3.11 conflicts with explicit UI3.13; do not write either.",
        "4.7": "Reported coordinate has no source-defined meaning or write encoder.",
        "sanitize": "The exact export plugin hides this3.3 control.",
        "delay_time": "Minimum30 is known; complete bounds and ordered scheduling flow are not.",
        "delay_enabled": "Enabling requires the scheduling flow and duration, not an isolated flag.",
        "automatic_firmware_updates": "Native cloud helper is known; HTTP write DTO is unverified.",
        "report_all": "An action rather than a user setting; discovery never invokes it.",
    },
}


def omitted_controls(model: str) -> dict[str, str]:
    """Explain deliberate gaps without presenting unsupported writable entities."""
    return deepcopy(_OMITTED.get(model, {}))


@lru_cache(maxsize=2)
def _catalog(model: str) -> dict[str, Any]:
    name = _CATALOGS.get(model)
    if name is None:
        raise ControlValidationError("Controls require an exact supported L9 model")
    data = load_catalog(name)
    if data.get("model") != model:
        raise ControlValidationError("Control catalogue does not match its exact model")
    return data


def _source_properties(model: str) -> dict[str, dict[str, Any]]:
    return {f"{p['siid']}.{p['piid']}": p for p in _catalog(model)["properties"]}


def _options(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = deepcopy(row.get("value_list") or [])
    if not result or any(type(r.get("value")) is not int or not isinstance(r.get("label"), str)
                         for r in result):
        raise ControlValidationError("Source control lacks an exact integer option table")
    if len({r["value"] for r in result}) != len(result):
        raise ControlValidationError("Source control has duplicate raw option codes")
    return [{"value": r["value"], "label": r["label"]} for r in result]


def _required_coordinates(model: str, key: str, coordinate: str | None,
                          program_field: str | None) -> list[str]:
    required = {"2.1", "3.4"}
    if coordinate:
        required.add(coordinate)
    if program_field or key in ("program", "start"):
        required.add("2.3")
    if key == "start":
        required.update(("2.2", "3.14"))
    if model == WASHER:
        required.update({
            "temperature": ("2.5", "3.8"), "extra_time": ("3.8",),
            "rinse_cycles": ("3.7",), "spin_speed": ("3.9",),
            "dynamic_rinse": ("2.16",), "speed_mode": ("2.8", "2.14"),
            "night_mode": ("2.4",), "fresh_air_circulation": ("2.4",),
        }.get(key, ()))
    else:
        required.update({"wrinkle_care": ("2.4",), "low_temperature": ("3.10",),
                         "speed_mode": ("3.12",)}.get(key, ()))
    return sorted(required)


@lru_cache(maxsize=2)
def _definitions(model: str) -> tuple[dict[str, Any], ...]:
    properties = _source_properties(model)
    definitions = []
    for key, kind, siid, piid, field in _PROPERTY_CONTROLS[model]:
        coordinate = f"{siid}.{piid}"
        row = properties[coordinate]
        if "write" not in row.get("access", ()):
            raise ControlValidationError("Control binding is absent from source writes")
        options = _options(row)
        if kind == "switch" and {r["value"] for r in options} != {0, 1}:
            raise ControlValidationError("Switch lacks a verified0/1 encoder")
        definitions.append({
            "key": key, "kind": kind, "platform": kind,
            "label": row.get("label") or row["name"], "coordinate": coordinate,
            "siid": siid, "piid": piid, "options": options,
            "value_type": "boolean" if kind == "switch" else "integer",
            "constraints": {"program_field": field,
                            "required_observations": _required_coordinates(model, key, coordinate, field),
                            "parameter_write_policy": "standby-only; no implicit pause/resume"},
            "provenance": {"source": deepcopy(_catalog(model)["source"]),
                           "property": deepcopy(row.get("control_sources") or row["provenance"])},
            "live_write_verified": False,
            **control_presentation(model, key),
        })
    # Literal native action inputs are identical on both exact plugins. Stop is
    # explicitly power-off, never an invented stop action or a pause alias.
    for key, label, aiid, raw in (("start", "Start or resume", 2, 1),
                                  ("pause", "Pause", 2, 0),
                                  ("stop", "Stop and power off", 1, 0)):
        if model == WASHER:
            evidence = next(r for r in _catalog(model)["actions"] if r["aiid"] == aiid)
            if raw not in evidence["observed_input_values"] or evidence["input_piid"] != aiid:
                raise ControlValidationError("Action input differs from official source")
        else:
            evidence = next(r for r in _catalog(model)["action_definitions"]
                            if r.get("siid") == 2 and r.get("aiid") == aiid
                            and r.get("inputs") == [{"piid": aiid, "value": raw}])
            if "action" not in evidence["observed_helpers"]:
                raise ControlValidationError("Source binding is not a native action")
        definitions.append({
            "key": key, "kind": "button", "platform": "button", "label": label,
            "siid": 2, "aiid": aiid, "inputs": [{"piid": aiid, "value": raw}],
            "options": [], "value_type": "none",
            "constraints": {"required_observations": _required_coordinates(model, key, None, None)},
            "provenance": {"source": deepcopy(_catalog(model)["source"]),
                           "action": deepcopy(evidence["provenance"])},
            "live_write_verified": False,
            **control_presentation(model, key),
        })
    return tuple(definitions)


def control_definitions(model: str) -> list[dict[str, Any]]:
    """Descriptors only for the exact known models, isolated from caller edits."""
    return deepcopy(list(_definitions(model))) if model in _CATALOGS else []


def _definition(model: str, key: str) -> dict[str, Any]:
    if not isinstance(key, str):
        raise ControlValidationError("Control key must name a source-defined control")
    for definition in _definitions(model):
        if definition["key"] == key:
            return definition
    raise ControlValidationError("Unknown or omitted control for this exact model")


def _state(observations: Mapping[str, Any], coordinate: str) -> int:
    """Require successful, non-null typed observation rows; no retained nulls."""
    if not isinstance(observations, Mapping):
        raise ControlValidationError("Current observations must be a mapping")
    row = observations.get(coordinate)
    if not isinstance(row, Mapping) or row.get("last_reply_null") is True:
        raise ControlValidationError(f"Current {coordinate} observation is missing or null")
    code = row.get("last_code")
    if code is not None and not (type(code) is int and code == 0 or type(code) is str and code == "0"):
        raise ControlValidationError(f"Current {coordinate} observation failed")
    value = row.get("value")
    if type(value) is not int:
        raise ControlValidationError(f"Current {coordinate} must be an integer source value")
    return value


def _enum_state(model: str, observations: Mapping[str, Any], coordinate: str) -> int:
    raw = _state(observations, coordinate)
    # Dryer SubscribePage lines525-529 explicitly treats faultInfo2.2 ==0
    # as no fault; its positive Fault table deliberately has no zero entry.
    if coordinate == "2.2" and raw == 0:
        return raw
    options = _source_properties(model).get(coordinate, {}).get("value_list")
    if options and raw not in {r["value"] for r in options if type(r.get("value")) is int}:
        raise ControlValidationError(f"Current {coordinate} has an unknown source code")
    return raw


def _flag(observations: Mapping[str, Any], coordinate: str) -> int:
    raw = _state(observations, coordinate)
    if raw not in (0, 1):
        raise ControlValidationError(f"Current {coordinate} is not a source0/1 flag")
    return raw


def _program_config(model: str, observations: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    program = _enum_state(model, observations, "2.3")
    catalog = _catalog(model)
    if model == WASHER:
        return program, next(row["default_configuration"] for row in catalog["programs"]
                             if row["value"] == program)
    selection = catalog["program_table_selection"]
    if selection["selected_table"] != "ProgramMode_W" or selection["is_export_sales_literal"] != 1:
        raise ControlValidationError("Unexpected dryer source program selection")
    # Every source ProgramMode_W[key] explicitly binds defaultConfig_W[key],
    # including the reordered18,19,16,17 entries. This is not array-list order.
    return program, catalog["program_default_configs"]["defaultConfig_W"]["values"][program]


def _validate_state(model: str, definition: Mapping[str, Any], observations: Mapping[str, Any]) -> None:
    key = definition["key"]
    for coordinate in definition["constraints"]["required_observations"]:
        _enum_state(model, observations, coordinate)
    status = _enum_state(model, observations, "2.1")
    if status not in (1, 2, 3):
        raise ControlValidationError("Device must have a known powered-on source status")
    lock = _flag(observations, "3.4")
    if key != "child_lock" and lock != 0:
        raise ControlValidationError("Child lock must be off")
    if key == "start":
        if status not in (1, 2) or _state(observations, "3.14") != 1 or _state(observations, "2.2") != 0:
            raise ControlValidationError("Start requires standby/pause, authorization1 and no fault")
    elif key == "pause":
        if status != 3:
            raise ControlValidationError("Pause requires running status")
    elif key == "stop" or key == "child_lock":
        pass
    elif key == "fresh_air_circulation":
        phase = _enum_state(model, observations, "2.4")
        program, _ = _program_config(model, observations)
        if program == 14 or phase != 0 and (status != 2 or phase not in (1, 2, 3)):
            raise ControlValidationError("Fresh air is restricted by program and paused wash phase")
    elif key == "wrinkle_care":
        phase = _enum_state(model, observations, "2.4")
        if status != 2 or phase not in (1, 2, 3):
            raise ControlValidationError("Wrinkle care requires pause in source phase1/2/3")
    elif status != 1:
        raise ControlValidationError("Parameter changes require standby; pause/resume is never implicit")
    if definition["kind"] != "button":
        current = _state(observations, definition["coordinate"])
        if current not in {r["value"] for r in definition["options"]}:
            raise ControlValidationError("Current setting has an unknown source code")
    field = definition["constraints"].get("program_field")
    if field:
        program, config = _program_config(model, observations)
        if config.get(field) is None:
            raise ControlValidationError("Current program disables this setting in the source UI")
        if model == DRYER and key == "extra_time" and program == 3:
            # Parameters/filterDefaultData explicitly hides addTime for key3,
            # even though the static configuration contains the integer0.
            raise ControlValidationError("Dryer Wool program explicitly disables extra time")
    if model == WASHER:
        if key == "temperature" and _state(observations, "2.5") != 0:
            raise ControlValidationError("Stain mode fixes temperature through a separate encoder")
        if key == "extra_time" and _flag(observations, "3.8") != 0:
            raise ControlValidationError("Speed mode disables extra-time changes")
        if key == "spin_speed" and _flag(observations, "3.9") != 0:
            raise ControlValidationError("Night mode fixes the existing spin speed")
        if key == "night_mode":
            program, _ = _program_config(model, observations)
            if _enum_state(model, observations, "2.4") != 0 or program in (6, 7, 20):
                raise ControlValidationError("Night-mode UI excludes this phase or program")


def _allowed_options(model: str, definition: Mapping[str, Any], observations: Mapping[str, Any]) -> list[dict[str, Any]]:
    _validate_state(model, definition, observations)
    options = deepcopy(definition["options"])
    if definition["key"] == "program":
        standard_codes = {row["value"] for row in program_catalog(model)}
        options = [row for row in options if row["value"] in standard_codes]
    field = definition["constraints"].get("program_field")
    program = None
    if field:
        program, config = _program_config(model, observations)
        setting = config[field]
        if isinstance(setting, Mapping):
            filtered = setting.get("filter")
            if not isinstance(filtered, list) or any(type(raw) is not int for raw in filtered):
                raise ControlValidationError("Program option filter is not a source integer list")
            options = [row for row in options if row["value"] not in filtered]
    if model == WASHER:
        if definition["key"] == "temperature" and program in (2, 4) and _flag(observations, "3.8") == 1:
            options = [row for row in options if row["value"] != 2]
        if definition["key"] == "rinse_cycles" and _flag(observations, "3.7") == 1:
            options = [row for row in options if row["value"] != 0]
        if definition["key"] == "dynamic_rinse" and _state(observations, "2.16") == 0:
            # App also changes rinse count; one switch never invents that value.
            options = [row for row in options if row["value"] != 1]
        if definition["key"] == "speed_mode":
            temperature = _enum_state(model, observations, "2.8")
            extra = _enum_state(model, observations, "2.14")
            if extra != 0 or program in (2, 4) and temperature == 2:
                options = [row for row in options if row["value"] != 1]
    else:
        # App turns off the other mode before writing its bulk config. This
        # interface preserves single-setting writes and requires it already off.
        companion = {"low_temperature": "3.10", "speed_mode": "3.12"}.get(definition["key"])
        if companion and _flag(observations, companion) != 0:
            options = [row for row in options if row["value"] != 1]
    return options


def control_options(model: str, key: str, current_observations: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return only currently valid exact raw options; unavailable controls yield[]."""
    try:
        return _allowed_options(model, _definition(model, key), current_observations)
    except ControlValidationError:
        return []


def control_available(model: str, key: str, current_observations: Mapping[str, Any]) -> bool:
    """Use the same required-state checks as the command encoder."""
    try:
        definition = _definition(model, key)
        if definition["kind"] == "button":
            _validate_state(model, definition, current_observations)
            return True
        return bool(_allowed_options(model, definition, current_observations))
    except ControlValidationError:
        return False


def prepare_control_write(model: str, key: str, value: Any,
                          current_observations: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a named control and return one DID-free RPC specification.

    Switch requests accept only actual bools. Select requests accept only actual
    integers from their raw options. Numeric strings, floats and bool-as-int are
    never coerced. Buttons accept only None. A gateway must attach its target DID;
    the caller cannot inject coordinates, an action id, or arbitrary input data.
    """
    definition = _definition(model, key)
    if definition["kind"] == "button":
        if value is not None:
            raise ControlValidationError("Buttons accept no caller-supplied action inputs")
        _validate_state(model, definition, current_observations)
        return {"method": "action", "action": {
            "siid": definition["siid"], "aiid": definition["aiid"],
            "in": deepcopy(definition["inputs"]),
        }}
    if definition["kind"] == "switch":
        if type(value) is not bool:
            raise ControlValidationError("Switch value must be a Boolean")
        raw = 1 if value else 0
    else:
        if type(value) is not int:
            raise ControlValidationError("Select value must be an exact integer source code")
        raw = value
    if raw not in {row["value"] for row in _allowed_options(model, definition, current_observations)}:
        raise ControlValidationError("Requested source code is not allowed by current program/settings")
    return {"method": "set_properties", "properties": [{
        "siid": definition["siid"], "piid": definition["piid"], "value": raw,
    }]}
