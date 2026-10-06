"""Context availability for source-proven r5023a cleaning telemetry.

Pinned Tasshack/dreame-vacuum revision
9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb: types.py:2068-2095 defines
availability; device.py:8981-9007,9048-9061,9123-9125,9180-9200,9481-9485
defines the underlying status getters. All enum constants are from types.py.

The caller supplies successful, fresh observation rows and validates the
telemetry value separately. This helper never reads catalogs or contacts a
device, and does not invent progress from elapsed time or cleaned area.
"""

from collections.abc import Mapping

VACUUM_MODEL = "dreame.vacuum.r5023a"
SOURCE_REVISION = "9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb"
_COORDINATES = frozenset(("4.2", "4.3", "4.63", "4.64"))

# The raw state getter also recognizes zero as charging completed.
_STATE_CODES = (frozenset(range(39)) | frozenset(range(95, 100))
                | frozenset(range(101, 110)) | frozenset(range(113, 119))
                | {120, 121, 122} | frozenset(range(140, 148)))
_STATUS_CODES = frozenset(range(31)) | {1501}
_TASK_CODES = frozenset(range(19)) | frozenset(range(20, 28)) | frozenset(range(30, 45))
_SELF_WASH_CODES = frozenset(range(8))
_STARTED_STATUSES = frozenset((2, 4, 18, 19, 20, 21, 22, 23, 25))
_CRUISING_TASKS = frozenset((20, 21, 22, 23))
_CRUISING_STATUSES = frozenset((22, 23))


def _integer(observations, coordinate):
    if not isinstance(observations, Mapping):
        return None
    rows = observations.get("properties", observations)
    if not isinstance(rows, Mapping):
        return None
    row = rows.get(coordinate)
    if (not isinstance(row, Mapping) or row.get("has_value") is False
            or isinstance(row.get("last_code"), bool)
            or row.get("last_code") not in (None, 0, "0")
            or row.get("last_reply_null", False)):
        return None
    value = row.get("value")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def vacuum_telemetry_available(model: str, coordinate: str, observations) -> bool:
    """Whether fresh typed context permits the requested telemetry sensor.

    Unknown model, coordinate, status enums, null replies and failed context
    observations fail closed. Historical time/area remain valid while idle.
    Paused cleaning counts as started, including the source's separate
    low-battery cleaning-paused flag when it is positively observed.
    """
    if model != VACUUM_MODEL or coordinate not in _COORDINATES:
        return False
    if coordinate == "4.64":
        self_wash = _integer(observations, "4.25")
        return self_wash in _SELF_WASH_CODES and self_wash == 2

    state = _integer(observations, "2.1")
    status = _integer(observations, "4.1")
    task = _integer(observations, "4.7")
    if state not in _STATE_CODES or status not in _STATUS_CODES or task not in _TASK_CODES:
        return False

    fast_mapping = (task == 5 or status == 21
                    or task in (5, 10) and state in (2, 3, 4))
    # This integration has no local go_to_zone command state. Explicit vendor
    # cruise codes are conservatively excluded even though r5023a has no
    # CAMERA_STREAMING capability, which upstream normally needs for cruising.
    cruising = task in _CRUISING_TASKS or status in _CRUISING_STATUSES
    if fast_mapping or cruising:
        return False
    if coordinate in ("4.2", "4.3"):
        return True

    if task not in (0, 11) or status in _STARTED_STATUSES:
        return True
    cleaning_paused = _integer(observations, "4.17")
    # The source getter applies bool() to this property, rather than using an
    # enum. Require a nonnegative integer before applying its truthiness.
    return cleaning_paused is not None and cleaning_paused > 0
