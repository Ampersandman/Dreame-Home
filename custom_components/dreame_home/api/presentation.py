"""Bounded entity presentation, independent of raw control encoders."""

from .laundry_programs import DRYER, WASHER

_MODELS = (WASHER, DRYER)
_CONTROL_NAMES = {
    "program": "Selected program", "temperature": "Temperature", "extra_time": "Extra time",
    "water_level": "Water level", "rinse_cycles": "Rinse cycles", "spin_speed": "Spin speed",
    "detergent_dosing": "Detergent dosing", "softener_dosing": "Softener dosing",
    "child_lock": "Child lock", "night_mode": "Night mode",
    "fresh_air_circulation": "Fresh air circulation", "dynamic_rinse": "Dynamic rinse",
    "speed_mode": "Speed mode", "dryness_level": "Dryness level", "airflow": "Airflow",
    "steam_level": "Steam level", "wrinkle_care": "Wrinkle care",
    "low_temperature": "Low temperature", "start": "Start or resume", "pause": "Pause",
    "stop": "Stop and power off",
}
_CONTROL_ICONS = {
    "program": "mdi:format-list-bulleted", "temperature": "mdi:thermometer",
    "extra_time": "mdi:timer-plus", "water_level": "mdi:water",
    "rinse_cycles": "mdi:waves", "spin_speed": "mdi:rotate-right",
    "detergent_dosing": "mdi:bottle-tonic", "softener_dosing": "mdi:bottle-tonic-outline",
    "child_lock": "mdi:lock", "night_mode": "mdi:weather-night",
    "fresh_air_circulation": "mdi:fan", "dynamic_rinse": "mdi:water-sync",
    "speed_mode": "mdi:fast-forward", "dryness_level": "mdi:tshirt-crew",
    "airflow": "mdi:fan", "steam_level": "mdi:weather-fog",
    "wrinkle_care": "mdi:hanger", "low_temperature": "mdi:thermometer-low",
    "start": "mdi:play-circle-outline", "pause": "mdi:pause-circle-outline",
    "stop": "mdi:stop-circle-outline",
}
_STATUS_NAMES = {
    "2.1": "Operation state", "2.2": "Fault code", "2.3": "Active program",
    "3.14": "Remote start", "progress": "Program progress",
    "elapsed_time": "Elapsed cycle time", "finish_time": "Program finish time",
}
_CYCLE_ICONS = {
    "progress": "mdi:progress-check", "elapsed_time": "mdi:timer-outline",
    "finish_time": "mdi:clock-end",
}
_MAIN_PROPERTIES = {
    WASHER: frozenset(("2.1", "2.3", "2.4", "2.12", "2.13", "3.13", "3.14", "4.6", "4.7")),
    DRYER: frozenset(("2.1", "2.3", "2.4", "2.9", "2.11", "3.14")),
    "dreame.vacuum.r5023a": frozenset(("2.1", "2.2", "2.3", "3.1", "4.1", "4.2", "4.3", "4.63", "4.64")),
}


def control_presentation(model, key, language=None):
    if model not in _MODELS or key not in _CONTROL_NAMES:
        return {}
    return {"label": _CONTROL_NAMES[key],
            "entity_category": None, "icon": _CONTROL_ICONS[key],
            "enabled_default": True}


def property_presentation(model, coordinate, pointer=None, language=None):
    """Unknown roots/leaves and duplicate setting readbacks stay diagnostics."""
    primary = pointer is None and coordinate in _MAIN_PROPERTIES.get(model, ())
    result = {"entity_category": None if primary else "diagnostic",
              "enabled_default": primary, "hide_legacy": not primary}
    if not primary:
        result["icon"] = "mdi:code-braces"
    if pointer is None and model in _MODELS:
        label = _STATUS_NAMES.get(coordinate)
        if label:
            result["label"] = label
        icons = {"2.1": "mdi:washing-machine" if model == WASHER else "mdi:tumble-dryer",
                 "2.2": "mdi:alert-circle-outline", "2.3": "mdi:format-list-bulleted",
                 "2.4": "mdi:progress-clock", "3.14": "mdi:remote"}
        if coordinate in icons:
            result["icon"] = icons[coordinate]
        if coordinate == "2.4":
            result["label"] = "Wash phase" if model == WASHER else "Dry phase"
        if coordinate in (("2.12",) if model == WASHER else ("2.9",)):
            result["label"] = "Program duration"
            result["icon"] = "mdi:timer-outline"
        if coordinate in (("2.13",) if model == WASHER else ("2.11",)):
            result["label"] = "Remaining time"
            result["icon"] = "mdi:timer-sand"
        if model == WASHER and coordinate in ("3.13", "4.6", "4.7"):
            result.update({
                "3.13": {"label": "Drum cleaning recommended", "icon": "mdi:spray-bottle"},
                "4.6": {"label": "Low detergent", "icon": "mdi:bottle-tonic"},
                "4.7": {"label": "Low softener", "icon": "mdi:bottle-tonic-outline"},
            }[coordinate])
        # These two readbacks were previously disabled as duplicate diagnostics.
        result["promote_default"] = coordinate in ("2.3", "3.14")
    return result


def cycle_presentation(key, language=None):
    label = _STATUS_NAMES.get(key)
    return {"label": label, "icon": _CYCLE_ICONS[key]} if key in _CYCLE_ICONS else {}
