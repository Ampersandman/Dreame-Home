"""Exact L9 cycle-time derivation without clocks, defaults, or network I/O.

Callers supply fresh successful observation rows. This helper additionally
checks reply codes, null flags, exact integer wire values and source enums.
Durations are raw minutes: dividing by 60 in the plugins formats hours, not
seconds. Ratio progress is (total-remaining)/total*100. The one-decimal rounding
below is integration presentation; the vendor formula is unrounded/unclamped.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
from typing import Any

from .catalog import load_catalog

WASHER = "dreame.washer.l9nacn"
DRYER = "dreame.dryer.l9nacn"
_MODELS = {
    WASHER: {"catalog": "l9_washer", "total": "2.12", "remaining": "2.13",
             "active_phases": frozenset((1, 2, 3, 4, 7))},
    DRYER: {"catalog": "l9_dryer", "total": "2.9", "remaining": "2.11",
            "active_phases": frozenset((1, 3))},
}


@lru_cache(maxsize=2)
def _catalog(model: str) -> dict[str, Any]:
    data = load_catalog(_MODELS[model]["catalog"])
    if data.get("model") != model:
        raise ValueError("Progress catalogue does not match its exact model")
    return data


def _provenance(model: str) -> dict[str, Any]:
    if model == WASHER:
        evidence = [{
            "module": "projects_dreame.washer.l9nacn_views_components_Timeline_index",
            "binding_lines": [20042, 20043, 20044, 20047, 20048],
            "minute_format_lines": [20065, 20069, 20073, 20077, 20081, 20085],
            "progress_lines": [20092, 20101],
        }]
    else:
        evidence = [{"module": "projects_dreame.dryer.l9nacn_request_index",
                     "binding_lines": [7920, 7926]},
                    {"module": "projects_dreame.dryer.l9nacn_views_Run_index",
                     "binding_lines": [16455, 16470, 17068, 17072]},
                    {"module": "projects_dreame.dryer.l9nacn_views_components_Timeline_index",
                     "minute_format_lines": [17413, 17421],
                     "progress_lines": [17428, 17449]}]
    return {"source": deepcopy(_catalog(model)["source"]), "evidence": evidence,
            "progress_formula": "(total_minutes - remaining_minutes) / total_minutes * 100",
            "elapsed_formula": "total_minutes - remaining_minutes",
            "rounding": "Progress rounded to 1 decimal as integration presentation; not vendor rounding.",
            "validation": "Invalid ratios stay unknown; no clamping, defaults or wall-clock ETA."}


def progress_definitions(model: str) -> list[dict[str, Any]]:
    """Independent descriptors, with the washer terminal-duration exception.

    Washer progress always requires status/program/phase, but may reach 100 in
    fresh powered phase 5/6 without duration rows. ``duration_coordinates`` lists
    the additional requirements for its ordinary ratio. Elapsed and dryer
    progress always require both durations. Freshness is enforced by the caller.
    """
    if model not in _MODELS:
        return []
    context = ["2.1", "2.3", "2.4"]
    durations = [_MODELS[model]["total"], _MODELS[model]["remaining"]]
    provenance = _provenance(model)
    return [{"key": "progress", "name": "Cycle progress", "unit": "%",
             "required_coordinates": context if model == WASHER else context + durations,
             "duration_coordinates": deepcopy(durations), "derived": True,
             "provenance": deepcopy(provenance)},
            {"key": "elapsed_time", "name": "Elapsed cycle time", "unit": "min",
             "required_coordinates": context + durations,
             "duration_coordinates": deepcopy(durations), "derived": True,
             "provenance": deepcopy(provenance)},
            {"key": "finish_time", "name": "Program finish time", "unit": None,
             "required_coordinates": context + durations,
             "duration_coordinates": deepcopy(durations),
             "remaining_coordinate": _MODELS[model]["remaining"],
             "derived": True, "estimated": True}]


def _integer(observations: Mapping[str, Any], coordinate: str) -> int | None:
    row = observations.get(coordinate)
    if not isinstance(row, Mapping) or row.get("last_reply_null", False):
        return None
    code = row.get("last_code")
    if not (code is None or type(code) is int and code == 0 or type(code) is str and code == "0"):
        return None
    value = row.get("value")
    return value if type(value) is int else None


def _enum_codes(model: str, coordinate: str) -> frozenset[int]:
    definition = next(row for row in _catalog(model)["properties"]
                      if f"{row['siid']}.{row['piid']}" == coordinate)
    return frozenset(row["value"] for row in definition.get("value_list") or ()
                     if type(row.get("value")) is int)


def laundry_cycle_metrics(model: str, observations: Mapping[str, Any]) -> dict[str, float | int | None]:
    """Derive only cycle context proved by successful, fresh source observations.

    The washer treats phase 5 Air Refresh Cruise and phase 6 Completed as washing
    completion: 100%, not appliance shutdown. The terminal exception accepts any
    known powered status 1/2/3 and needs no durations. Nonterminal ratio derivation
    requires active/pause status 2/3 and excludes Scheduled and unknown phases.
    Dryer phase 2 Completed has no proven source override and remains unknown.
    """
    result = {"progress": None, "elapsed_time": None}
    if model not in _MODELS or not isinstance(observations, Mapping):
        return result
    status = _integer(observations, "2.1")
    program = _integer(observations, "2.3")
    phase = _integer(observations, "2.4")
    if (status not in (1, 2, 3) or program not in _enum_codes(model, "2.3")
            or phase not in _enum_codes(model, "2.4")):
        return result
    terminal = model == WASHER and phase in (5, 6)
    if not terminal and (status not in (2, 3) or phase not in _MODELS[model]["active_phases"]):
        return result
    if terminal:
        result["progress"] = 100
    total = _integer(observations, _MODELS[model]["total"])
    remaining = _integer(observations, _MODELS[model]["remaining"])
    if (total is None or remaining is None or total <= 0
            or remaining < 0 or remaining > total):
        return result
    # Source displays --min for AI Wash program 0/R0. Its visual 0 is not measured 0%.
    if model == WASHER and program == 0 and remaining == 0 and not terminal:
        return result
    elapsed = total - remaining
    result["elapsed_time"] = elapsed
    if not terminal:
        result["progress"] = round(elapsed / total * 100, 1)
    return result


def laundry_finish_remaining(model: str, observations: Mapping[str, Any]) -> int | None:
    """Minutes for an integration finish estimate during ordinary running only.

    A pause, schedule, add-clothes interruption or aftercare has no defensible
    advancing wall-clock end. The caller anchors this estimate to receipt of
    the remaining-time observation, never to a program's default duration.
    """
    phases = {WASHER: (1, 2, 3, 4), DRYER: (3,)}
    if (model not in _MODELS or not isinstance(observations, Mapping)
            or _integer(observations, "2.1") != 3
            or _integer(observations, "2.4") not in phases[model]
            or laundry_cycle_metrics(model, observations)["elapsed_time"] is None):
        return None
    remaining = _integer(observations, _MODELS[model]["remaining"])
    return remaining if remaining is not None and remaining > 0 else None
