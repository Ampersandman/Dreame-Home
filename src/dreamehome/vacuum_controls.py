"""Source-backed controls for the confirmed L10s Ultra Gen 3 cloud model.

Plans contain no device identifier; the caller binds the actual cloud DID and
checks acknowledgements without replaying commands. No network or vendor code
is executed here. Commands require successful, current observations supplied
by the caller, and never predict the resulting appliance state.

Pinned upstream: Tasshack/dreame-vacuum, revision below. types.py:1586-1597,
1962-1966 defines coordinates; protocol.py:2633-2708 proves actual DID use for
Dreame Home. device.py:4370-4624 defines actions and special resume cases;
2188-2191,5965-5998 define suction and its SuctionMax patch. r5023a capability
row 104 enables NEW_STATE, MAX_SUCTION_POWER and DRAINAGE.
"""

from collections.abc import Mapping
import json
import math

VACUUM_MODEL = "dreame.vacuum.r5023a"
SOURCE_REVISION = "9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb"
SOURCE_URL = f"https://github.com/Tasshack/dreame-vacuum/tree/{SOURCE_REVISION}"
FAN_SPEEDS = {"silent": 0, "standard": 1, "strong": 2, "turbo": 3}
_ACTIONS = {"start": (2, 1), "pause": (2, 2), "stop": (4, 2), "return_to_base": (3, 1)}

# Pinned vacuum.py:76-123 projects the new-state enum onto HA activities.
# UNKNOWN deliberately remains unknown rather than being manufactured as idle.
_ACTIVITY_GROUPS = {
    "idle": (2, 14, 16, 29),
    "cleaning": (1, 7, 9, 12, 15, 20, 23, 25, 26, 27, 97, 30, 32, 33, 98, 37, 38, 96, 101),
    "paused": (3, 21, 99, 36, 95, 102),
    "error": (4,),
    "returning": (5, 10, 17, 18, 28, 31),
    "docked": (6, 8, 11, 13, 19, 22, 24, 34, 35, 103, 104),
}
_ACTIVITIES = {code: activity for activity, codes in _ACTIVITY_GROUPS.items() for code in codes}
# Pinned types.py:2559-2581 distinguishes warnings from blocking errors.
_WARNING_CODES = frozenset((68, 70, 114, 47, 107, 71, 72, 117, 121, 123, 75,
                            9, 10, 51, 85, 129, 56, 20, 82, 213, 214, 122))
_DOCKING_PAUSED = frozenset((11, 16, 17, 18))
_CLEANING_STATUSES = frozenset((2, 4, 5, 18, 19, 20, 21, 22, 23, 24, 25))
_STATUS_CODES = frozenset(range(31)) | {1501}
_TASK_CODES = frozenset(range(19)) | frozenset(range(20, 28)) | frozenset(range(30, 45))


def vacuum_control_supported(model: str) -> bool:
    return model == VACUUM_MODEL


def _properties(observations):
    if not isinstance(observations, Mapping):
        return {}
    rows = observations.get("properties", observations)
    return rows if isinstance(rows, Mapping) else {}


def _value(observations, coordinate):
    row = _properties(observations).get(coordinate)
    if (not isinstance(row, Mapping) or "value" not in row
            or isinstance(row.get("last_code"), bool)
            or row.get("last_code") not in (None, 0, "0")
            or row.get("last_reply_null", False)):
        return None
    return row["value"]


def _integer(observations, coordinate):
    value = _value(observations, coordinate)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _auto_setting(observations, setting):
    value = _value(observations, "4.50")
    if isinstance(value, str):
        if len(value) > 262144:
            return None
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            return None
    if isinstance(value, Mapping) and "k" in value:
        value = [value]
    if not isinstance(value, list) or len(value) > 1024:
        return None
    entries = [entry.get("v") for entry in value
               if isinstance(entry, Mapping) and entry.get("k") == setting]
    if len(entries) != 1 or not isinstance(entries[0], int) or isinstance(entries[0], bool):
        return None
    return entries[0]


def _started(observations):
    task = _integer(observations, "4.7")
    return (task is not None and task not in (0, 11)
            or _integer(observations, "4.1") in _CLEANING_STATUSES)


def vacuum_state(model: str, observations) -> dict:
    """Project successful observation rows into HA-independent state fields."""
    state = _integer(observations, "2.1") if vacuum_control_supported(model) else None
    status = _integer(observations, "4.1") if vacuum_control_supported(model) else None
    task = _integer(observations, "4.7") if vacuum_control_supported(model) else None
    error = _integer(observations, "2.2") if vacuum_control_supported(model) else None
    activity = _ACTIVITIES.get(13 if state == 0 else state)
    if error is not None and error > 0 and error not in _WARNING_CODES:
        activity = "error"
    elif state == 2:
        # device.py:8183-8198: idle during an active task is paused; an
        # otherwise idle robot reporting charging/completed is docked.
        if _started(observations):
            activity = "paused"
        elif _integer(observations, "3.2") in (1, 3) and status != 3:
            activity = "docked"
    battery = _value(observations, "3.1") if vacuum_control_supported(model) else None
    if (not isinstance(battery, (int, float)) or isinstance(battery, bool)
            or not 0 <= battery <= 100
            or isinstance(battery, float) and not math.isfinite(battery)):
        battery = None
    suction = _integer(observations, "4.4") if vacuum_control_supported(model) else None
    fan = next((name for name, code in FAN_SPEEDS.items() if code == suction), None)
    return {"supported": vacuum_control_supported(model), "activity": activity,
            "battery_level": battery, "fan_speed": fan,
            "fan_speed_list": list(FAN_SPEEDS) if vacuum_control_supported(model) else [],
            "state_code": state, "status_code": status, "task_code": task, "error_code": error}


def vacuum_required_coordinates(model: str, command: str, observations=None) -> tuple[str, ...]:
    """Minimal successful/current observations needed for this command.

    The caller may refresh these before validation. Optional dock/drainage
    observations are also checked by the encoder when supplied. Unsupported
    optional properties do not manufacture model capabilities.
    """
    if not vacuum_control_supported(model) or command not in (*_ACTIONS, "set_fan_speed"):
        raise ValueError("Vacuum command is not supported for this exact model")
    required = ["2.1", "4.1", "4.7"]
    if command == "start" and _integer(observations, "2.1") == 3:
        required.append("4.25")
    if command == "set_fan_speed":
        required.extend(("4.4", "4.50"))
        if _started(observations):
            required.extend(("4.26", "4.47"))
    return tuple(required)


def prepare_vacuum_command(model: str, command: str, value=None, observations=None) -> dict:
    """Validate one explicit command and return its source-backed wire plan."""
    required = vacuum_required_coordinates(model, command, observations)
    for coordinate in required:
        if coordinate == "4.50":
            if _auto_setting(observations, "SuctionMax") not in (0, 1):
                raise ValueError("Current maximum-suction setting is unavailable")
        elif _integer(observations, coordinate) is None:
            raise ValueError("Current vacuum command context is unavailable")
    projected = vacuum_state(model, observations)
    state, status, task = (projected[key] for key in ("state_code", "status_code", "task_code"))
    if (state not in _ACTIVITIES and state != 0 or projected["activity"] is None
            or task not in _TASK_CODES or status not in _STATUS_CODES):
        raise ValueError("Vacuum state is unknown")
    if (state in (14, 19, 32, 33) or status in (7, 8, 9, 10, 11, 15, 16, 1501)
            or _integer(observations, "4.60") == 1):
        raise ValueError("Vacuum controls are unavailable during maintenance")
    if command != "set_fan_speed" and value is not None:
        raise ValueError("This vacuum action takes no value")
    if command == "start":
        if task in (5, 10, 20, 21, 22, 23, 27, 31, 32, 33) or state in (9, 21, 30, 98, 99):
            raise ValueError("This task needs a specialized resume command")
        if state == 3 and _integer(observations, "4.25") in (3, 7):
            raise ValueError("Dock-washing resume is not supported")
        if task in _DOCKING_PAUSED and projected["activity"] != "docked":
            command = "return_to_base"  # device.py:4382-4383
    elif command == "pause" and not _started(observations) and state in (9, 21):
        raise ValueError("Dock-washing pause is not supported")
    elif command == "stop":
        if state in (8, 35, 36) and not _started(observations):
            raise ValueError("Dock-drying stop is not supported")
        if task in (5, 10) or state == 11:
            command = "return_to_base"  # device.py:4507-4508
    elif command == "set_fan_speed":
        if not isinstance(value, str) or value not in FAN_SPEEDS:
            raise ValueError("Fan speed must be silent, standard, strong or turbo")
        if (projected["fan_speed"] is None or state in (7, 11, 19, 23, 98, 99)
                or task in (5, 10, 20, 21, 22, 23) or status in (21, 22, 23)):
            raise ValueError("Fan speed is unavailable for this task")
        if _started(observations):
            customized = _integer(observations, "4.26")
            # Source 1/2/4 denotes scheduled tasks; only positively observed
            # ordinary-task 0 permits changing the shared suction preference.
            if customized not in (0, 1) or _integer(observations, "4.47") != 0:
                raise ValueError("Fan speed is managed by this cleaning task")
            if customized and task not in (2, 7, 14, 18, 4, 9) and status != 20:
                raise ValueError("Fan speed is managed by customized cleaning")
            if _auto_setting(observations, "SmartHost") != 0:
                raise ValueError("Current automatic-cleaning setting is unavailable or active")
        properties = []
        if _auto_setting(observations, "SuctionMax") == 1:
            properties.append({"siid": 4, "piid": 50, "value": '{"k":"SuctionMax","v":0}'})
        properties.append({"siid": 4, "piid": 4, "value": FAN_SPEEDS[value]})
        plan = {"method": "set_properties", "properties": properties}
        if len(properties) > 1:
            plan["sequential"] = True
        return plan
    siid, aiid = _ACTIONS[command]
    return {"method": "action", "action": {"siid": siid, "aiid": aiid, "in": []}}


def vacuum_command_available(model: str, command: str, observations) -> bool:
    """Whether memory contains enough supported context to offer a control."""
    try:
        prepare_vacuum_command(model, command, "standard" if command == "set_fan_speed" else None,
                               observations)
    except (TypeError, ValueError):
        return False
    return True
