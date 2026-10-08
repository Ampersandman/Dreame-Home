"""Read-only display metadata proved by app timelines and pinned vacuum sensors.

This overlay keeps generated source catalogs unchanged. Labels and units apply
only to the listed exact model/coordinate, never to a compound child or setter.
"""

from copy import deepcopy

_WASHER_TIMELINE = "projects_dreame.washer.l9nacn_views_components_Timeline_index"
_DRYER_TIMELINE = "projects_dreame.dryer.l9nacn_views_components_Timeline_index"


def _duration(label, module, lines):
    return {"label": label, "unit": "min", "device_class": "duration", "minimum": 0,
            "operational": True, "telemetry_provenance": {"module": module, "lines": lines}}


_METADATA = {
    "dreame.washer.l9nacn": {
        "2.12": _duration("Program duration", _WASHER_TIMELINE, [20042, 20073]),
        "2.13": _duration("Remaining time", _WASHER_TIMELINE, [20048, 20085]),
        "3.14": {
            "label": "Remote start", "value_list_inferred": False,
            "value_list": [{"value": 0, "label": "Off"}, {"value": 1, "label": "On"}],
            "telemetry_provenance": {
                "module": "projects_dreame.washer.l9nacn_views_SubscribePage_index",
                "lines": [469, 470, 596, 600],
                "meaning": "Integer 0 opens the not-authorized prompt; integer 1 permits remote start.",
            },
        },
    },
    "dreame.dryer.l9nacn": {
        "2.1": {"label": "Run status"},
        "2.2": {"label": "Fault code"},
        "2.4": {"label": "Dry phase"},
        "2.9": _duration("Program duration", _DRYER_TIMELINE, [17428, 17449]),
        "2.11": _duration("Remaining time", _DRYER_TIMELINE, [17413, 17421]),
        "3.14": {
            "label": "Remote start", "value_list_inferred": False,
            "value_list": [{"value": 0, "label": "Off"}, {"value": 1, "label": "On"}],
            "telemetry_provenance": {
                "module": "projects_dreame.dryer.l9nacn_views_SubscribePage_index",
                "lines": [515, 517, 614, 618],
                "meaning": "Integer 0 opens the not-authorized prompt; integer 1 permits remote start.",
            },
        },
    },
    "dreame.vacuum.r5023a": {
        "4.2": {"label": "Cleaning time", "unit": "min", "device_class": "duration",
                "minimum": 0, "operational": True},
        "4.3": {"label": "Cleaned area", "unit": "m²", "device_class": "area",
                "minimum": 0, "operational": True},
        "4.63": {"label": "Cleaning progress", "unit": "%", "minimum": 0,
                 "maximum": 100, "operational": True},
        "4.64": {"label": "Mop drying progress", "unit": "%", "minimum": 0,
                 "maximum": 100, "operational": True},
    },
}

_METADATA["dreame.washer.l9nacn"]["2.13"]["ai_zero_is_unknown"] = True
for _row in _METADATA["dreame.vacuum.r5023a"].values():
    _row["telemetry_provenance"] = {
        "source_revision": "9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb",
        "file": "custom_components/dreame_vacuum/sensor.py", "lines": [60, 83, 592, 605],
    }


def telemetry_metadata(model: str, coordinate: str, pointer=None) -> dict:
    """Return independent source-backed metadata for scalar roots only."""
    return deepcopy(_METADATA.get(model, {}).get(coordinate, {})) if pointer is None else {}
