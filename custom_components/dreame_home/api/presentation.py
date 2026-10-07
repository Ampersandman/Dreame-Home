"""Bounded entity presentation, independent of raw control encoders."""

from .laundry_programs import DRYER, WASHER, program_language

_MODELS = (WASHER, DRYER)
_CONFIGURATION = frozenset(("child_lock", "night_mode"))
_CONTROL_NAMES = {
    "program": ("Program", "Programm"), "temperature": ("Temperature", "Temperatur"),
    "extra_time": ("Extra time", "Zusatzzeit"), "water_level": ("Water level", "Wasserstand"),
    "rinse_cycles": ("Rinse cycles", "Spülgänge"), "spin_speed": ("Spin speed", "Schleuderdrehzahl"),
    "detergent_dosing": ("Detergent dosing", "Waschmitteldosierung"),
    "softener_dosing": ("Softener dosing", "Weichspülerdosierung"),
    "child_lock": ("Child lock", "Kindersicherung"), "night_mode": ("Night mode", "Nachtmodus"),
    "fresh_air_circulation": ("Fresh air circulation", "Frischluftzirkulation"),
    "dynamic_rinse": ("Dynamic rinse", "Dynamisches Spülen"), "speed_mode": ("Speed mode", "Schnellmodus"),
    "dryness_level": ("Dryness level", "Trocknungsgrad"), "airflow": ("Airflow", "Luftstrom"),
    "steam_level": ("Steam level", "Dampfstufe"), "wrinkle_care": ("Wrinkle care", "Knitterschutz"),
    "low_temperature": ("Low temperature", "Niedrige Temperatur"),
    "start": ("Start or resume", "Starten oder fortsetzen"), "pause": ("Pause", "Pausieren"),
    "stop": ("Stop and power off", "Stoppen und ausschalten"),
}
_STATUS_NAMES = {
    "2.1": ("Run status", "Betriebsstatus"), "2.2": ("Fault code", "Fehlercode"),
    "2.3": ("Program", "Programm"), "progress": ("Cycle progress", "Programmfortschritt"),
    "elapsed_time": ("Elapsed cycle time", "Vergangene Programmzeit"),
}
_MAIN_PROPERTIES = {
    WASHER: frozenset(("2.1", "2.2", "2.4", "2.11", "2.12", "2.13", "3.13", "4.6", "4.7")),
    DRYER: frozenset(("2.1", "2.2", "2.4", "2.9", "2.11", "2.12")),
    "dreame.vacuum.r5023a": frozenset(("2.1", "2.2", "2.3", "3.1", "4.1", "4.2", "4.3", "4.63", "4.64")),
}


def control_presentation(model, key, language=None):
    if model not in _MODELS or key not in _CONTROL_NAMES:
        return {}
    names = _CONTROL_NAMES[key]
    return {"label": names[program_language(language) == "de"],
            "entity_category": "config" if key in _CONFIGURATION else None,
            "enabled_default": True}


def property_presentation(model, coordinate, pointer=None, language=None):
    """Unknown roots/leaves and duplicate setting readbacks stay diagnostics."""
    primary = pointer is None and coordinate in _MAIN_PROPERTIES.get(model, ())
    result = {"entity_category": None if primary else "diagnostic",
              "enabled_default": primary, "hide_legacy": not primary}
    if pointer is None and model in _MODELS:
        names = _STATUS_NAMES.get(coordinate)
        if names:
            result["label"] = names[program_language(language) == "de"]
        if coordinate == "2.4":
            result["label"] = ("Waschphase" if model == WASHER else "Trocknungsphase") if program_language(language) == "de" else ("Wash phase" if model == WASHER else "Dry phase")
        if coordinate in (("2.12",) if model == WASHER else ("2.9",)):
            result["label"] = "Programmdauer" if program_language(language) == "de" else "Program duration"
        if coordinate in (("2.13",) if model == WASHER else ("2.11",)):
            result["label"] = "Restzeit" if program_language(language) == "de" else "Remaining time"
    return result


def cycle_presentation(key, language=None):
    names = _STATUS_NAMES.get(key)
    return {"label": names[program_language(language) == "de"]} if names else {}
