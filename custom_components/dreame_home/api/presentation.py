"""Bounded entity presentation, independent of raw control encoders."""

from .laundry_programs import DRYER, WASHER

_MODELS = (WASHER, DRYER)
_CONFIGURATION = frozenset(("child_lock", "night_mode"))
_CONTROL_NAMES = {
    "program": "Program", "temperature": "Temperature", "extra_time": "Extra time",
    "water_level": "Water level", "rinse_cycles": "Rinse cycles", "spin_speed": "Spin speed",
    "detergent_dosing": "Detergent dosing", "softener_dosing": "Softener dosing",
    "child_lock": "Child lock", "night_mode": "Night mode",
    "fresh_air_circulation": "Fresh air circulation", "dynamic_rinse": "Dynamic rinse",
    "speed_mode": "Speed mode", "dryness_level": "Dryness level", "airflow": "Airflow",
    "steam_level": "Steam level", "wrinkle_care": "Wrinkle care",
    "low_temperature": "Low temperature", "start": "Start or resume", "pause": "Pause",
    "stop": "Stop and power off",
}
_STATUS_NAMES = {
    "2.1": "Run status", "2.2": "Fault code", "2.3": "Program",
    "progress": "Cycle progress", "elapsed_time": "Elapsed cycle time",
}
_MAIN_PROPERTIES = {
    WASHER: frozenset(("2.1", "2.2", "2.4", "2.11", "2.12", "2.13", "3.13", "4.6", "4.7")),
    DRYER: frozenset(("2.1", "2.2", "2.4", "2.9", "2.11", "2.12")),
    "dreame.vacuum.r5023a": frozenset(("2.1", "2.2", "2.3", "3.1", "4.1", "4.2", "4.3", "4.63", "4.64")),
}


def control_presentation(model, key, language=None):
    if model not in _MODELS or key not in _CONTROL_NAMES:
        return {}
    return {"label": _CONTROL_NAMES[key],
            "entity_category": "config" if key in _CONFIGURATION else None,
            "enabled_default": True}


def property_presentation(model, coordinate, pointer=None, language=None):
    """Unknown roots/leaves and duplicate setting readbacks stay diagnostics."""
    primary = pointer is None and coordinate in _MAIN_PROPERTIES.get(model, ())
    result = {"entity_category": None if primary else "diagnostic",
              "enabled_default": primary, "hide_legacy": not primary}
    if pointer is None and model in _MODELS:
        label = _STATUS_NAMES.get(coordinate)
        if label:
            result["label"] = label
        if coordinate == "2.4":
            result["label"] = "Wash phase" if model == WASHER else "Dry phase"
        if coordinate in (("2.12",) if model == WASHER else ("2.9",)):
            result["label"] = "Program duration"
        if coordinate in (("2.13",) if model == WASHER else ("2.11",)):
            result["label"] = "Remaining time"
    return result


def cycle_presentation(key, language=None):
    label = _STATUS_NAMES.get(key)
    return {"label": label} if label else {}
