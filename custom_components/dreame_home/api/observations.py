"""Normalize read-only observations without assuming an appliance schema.

Snapshots retain cloud values and unknown payloads. They are private data and
must pass through ``dreamehome.privacy`` before being shared as diagnostics.
Only verified catalog vacuum models receive upstream vacuum property names.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from copy import deepcopy
import json
import math
import re
from typing import Any

from .catalog import known_vacuum_model, load_catalog


_COORDINATE = re.compile(r"(?:prop\.)?([1-9][0-9]*)\.([1-9][0-9]*)\Z")

# This is a bounded starting read plan from the upstream vacuum property map.
# Support remains conditional on the actual per-property response code.
VACUUM_INITIAL_READ_PAIRS = (
    (2, 1), (2, 2), (3, 1), (3, 2), (4, 1), (4, 2), (4, 3),
    (4, 7), (4, 20), (4, 25), (4, 35), (4, 52), (4, 53),
    (15, 3), (15, 5),
    # Control context for the confirmed r5023a: suction, task/washing state,
    # packed suction-max flag and cruise state. Successful values remain required.
    (4, 4), (4, 26), (4, 47), (4, 50), (4, 60),
)


def property_coordinate(value: Any) -> tuple[int, int] | None:
    """Accept explicit siid/piid or a cloud ``prop.2.1`` / ``2.1`` key.

    A numeric ``did`` is a device or correlation ID, never a property coordinate.
    Malformed or non-positive service/property IDs are retained as unknown data.
    """
    if isinstance(value, Mapping):
        siid, piid = value.get("siid"), value.get("piid")
        if isinstance(siid, bool) or isinstance(piid, bool):
            return None
        if all(isinstance(part, int) or (isinstance(part, str) and part.isdecimal())
               for part in (siid, piid)):
            pair = int(siid), int(piid)
            if min(pair) > 0:
                return pair
        return property_coordinate(value.get("key")) or property_coordinate(value.get("did"))
    if isinstance(value, str) and (match := _COORDINATE.fullmatch(value)):
        return int(match[1]), int(match[2])
    return None


def _json_container(value: Any, max_chars: int) -> tuple[Any, str | None]:
    if isinstance(value, (dict, list)):
        return value, None
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        if len(value) > max_chars:
            return None, "json_too_large"
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed, None
        except (ValueError, RecursionError):
            return None, "invalid_json"
    return None, None


def compound_fields(value: Any, *, max_fields: int = 256, max_depth: int = 16) -> tuple[dict[str, Any], bool]:
    """Bounded scalar projection using unambiguous JSON Pointer paths.

    Original compound data stays on the observation. Projection limits affect
    entity expansion only; they do not silently remove fields from raw values.
    """
    if max_fields < 1 or max_depth < 1:
        raise ValueError("Compound limits must be positive")
    fields: dict[str, Any] = {}
    pending = [("", value, 0)]
    truncated = False
    while pending:
        path, item, depth = pending.pop()
        if isinstance(item, (dict, list)):
            if depth >= max_depth:
                truncated = True
                continue
            children = list(item.items()) if isinstance(item, dict) else list(enumerate(item))
            # Bound pending traversal as well as the resulting leaf dictionary.
            room = max_fields - len(fields) - len(pending)
            if len(children) > room:
                children = children[:max(0, room)]
                truncated = True
            for key, child in reversed(children):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                pending.append((f"{path}/{escaped}", child, depth + 1))
        else:
            if len(fields) >= max_fields:
                truncated = True
                break
            fields[path] = deepcopy(item)
    return fields, truncated


def entity_fields(value: Any, *, max_fields: int = 256, max_depth: int = 16) -> tuple[dict[str, Any], bool]:
    """Project dictionary leaves and uniquely keyed setting lists for entities.

    List members require unique, nonempty scalar ``k`` identifiers. Their stable
    paths use ``/@setting-key/v`` instead of positions that change on reordering.
    Other arrays remain available on the complete compound root. These semantic
    paths use JSON Pointer escaping but are not pointers into the original array.
    """
    if max_fields < 1 or max_depth < 1:
        raise ValueError("Entity projection limits must be positive")
    fields: dict[str, Any] = {}
    pending = [("", value, 0)]
    truncated = False

    def setting_key(key):
        if (not isinstance(key, (str, bool, int, float)) or key == ""
                or isinstance(key, float) and not math.isfinite(key)):
            return None
        return str(key)

    while pending:
        path, item, depth = pending.pop()
        if isinstance(item, (dict, list)):
            if depth >= max_depth:
                truncated = True
                continue
            if isinstance(item, dict):
                if "k" in item and "v" in item:
                    key = setting_key(item["k"])
                    if key is None:
                        continue
                    children = [(f"@{key}", {k: v for k, v in item.items() if k != "k"})]
                else:
                    children = list(item.items())
            else:
                keys = []
                for member in item:
                    key = member.get("k") if isinstance(member, dict) else None
                    normalized = setting_key(key)
                    if normalized is None:
                        break
                    keys.append(normalized)
                if len(keys) != len(item) or len(set(keys)) != len(keys):
                    continue
                # Omit the repeated identifier itself; its stable path supplies it.
                children = [(f"@{key}", {k: v for k, v in member.items() if k != "k"})
                            for key, member in zip(keys, item)]
            room = max_fields - len(fields) - len(pending)
            if len(children) > room:
                children = children[:max(0, room)]
                truncated = True
            for key, child in reversed(children):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                pending.append((f"{path}/{escaped}", child, depth + 1))
        else:
            if len(fields) >= max_fields:
                truncated = True
                break
            fields[path] = deepcopy(item)
    return fields, truncated


class ObservationStore:
    """Merge RPC, cached metadata and MQTT without writes or guessed schemas.

    ``properties`` maps ``siid.piid`` to observations. Failed or null reads preserve
    the last non-null value/source and retain the latest reply evidence separately.
    Unknown cached keys and events stay available in bounded collections.
    Merge methods return the set of property keys touched by the input.
    """

    def __init__(self, model: str, *, max_events: int = 100,
                 max_properties: int = 4096, max_cached_keys: int = 1024,
                 max_json_chars: int = 262_144, max_compound_fields: int = 256):
        if min(max_events, max_properties, max_cached_keys, max_json_chars, max_compound_fields) < 1:
            raise ValueError("Observation limits must be positive")
        self.model = model
        self.properties: dict[str, dict[str, Any]] = {}
        self.cached: dict[str, Any] = {}
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self.max_properties = max_properties
        self.max_cached_keys = max_cached_keys
        self.max_json_chars = max_json_chars
        self.max_compound_fields = max_compound_fields
        self.dropped_events = 0
        self.dropped_properties = 0
        self.dropped_cached_keys = 0
        self._names = {}
        if known_vacuum_model(model):
            self._names = {
                (p["mapping"]["siid"], p["mapping"]["piid"]): p["name"]
                for p in load_catalog("properties")
                if p.get("mapping") and "piid" in p["mapping"]
            }

    def _event(self, payload: Any, source: str) -> None:
        if len(self.events) == self.events.maxlen:
            self.dropped_events += 1
        self.events.append({"source": source, "payload": deepcopy(payload)})

    def merge_properties(self, rows: Iterable[Any], *, source: str = "rpc") -> set[str]:
        touched: set[str] = set()
        for row in rows:
            pair = property_coordinate(row)
            if not isinstance(row, Mapping) or pair is None:
                self._event(row, source)
                continue
            key = f"{pair[0]}.{pair[1]}"
            if key not in self.properties:
                if len(self.properties) >= self.max_properties:
                    self.dropped_properties += 1
                    continue
                self.properties[key] = {"siid": pair[0], "piid": pair[1], "observed_count": 0}
                if pair in self._names:
                    self.properties[key]["name"] = self._names[pair]
            observation = self.properties[key]
            code = row.get("code", 0)
            observation.update(last_code=deepcopy(code), last_source=source,
                               last_item=deepcopy(dict(row)),
                               last_reply_null="value" in row and row["value"] is None,
                               observed_count=observation["observed_count"] + 1)
            if code in (0, "0", None) and row.get("value") is not None:
                value = deepcopy(row["value"])
                observation.update(value=value, source=source, code=code)
                for field in ("compound", "compound_fields", "compound_truncated", "entity_fields",
                              "entity_fields_truncated", "decode_error"):
                    observation.pop(field, None)
                compound, error = _json_container(value, self.max_json_chars)
                if compound is not None:
                    fields, truncated = compound_fields(compound, max_fields=self.max_compound_fields)
                    stable_fields, stable_truncated = entity_fields(compound, max_fields=self.max_compound_fields)
                    observation.update(compound=compound, compound_fields=fields,
                                       compound_truncated=truncated, entity_fields=stable_fields,
                                       entity_fields_truncated=stable_truncated)
                if error is not None:
                    observation["decode_error"] = error
            touched.add(key)
        return touched

    def merge_cached(self, payload: Any, *, source: str = "cached") -> set[str]:
        """Accept a metadata ``property`` blob, cached props response or rows."""
        if isinstance(payload, str):
            decoded, error = _json_container(payload, self.max_json_chars)
            if decoded is None:
                self._event({"cached_payload": payload, "decode_error": error}, source)
                return set()
            payload = decoded
        if isinstance(payload, list):
            return self.merge_properties(payload, source=source)
        if not isinstance(payload, Mapping):
            self._event(payload, source)
            return set()
        # Full device records contain many identity/transport fields. Only the
        # actual cached property blob is merged from that form.
        if "property" in payload and ("did" in payload or "model" in payload):
            return self.merge_cached(payload["property"], source=source)
        if property_coordinate(payload) is not None and "value" in payload:
            return self.merge_properties([payload], source=source)
        touched: set[str] = set()
        for key, value in payload.items():
            if pair := property_coordinate(key):
                row = dict(value) if isinstance(value, Mapping) and "value" in value else {"value": value}
                row.update(siid=pair[0], piid=pair[1])
                touched |= self.merge_properties([row], source=source)
            elif key in ("props", "properties", "data") and isinstance(value, (Mapping, list)):
                touched |= self.merge_cached(value, source=source)
            elif key not in self.cached and len(self.cached) >= self.max_cached_keys:
                self.dropped_cached_keys += 1
            else:
                self.cached[str(key)] = deepcopy(value)
        return touched

    def merge_push(self, message: bytes | str | Mapping[str, Any], *, source: str = "mqtt") -> set[str]:
        """Accept wrapped/unwrapped notifications and retain unknown methods."""
        if isinstance(message, (bytes, str)):
            try:
                message = json.loads(message)
            except (ValueError, UnicodeDecodeError, RecursionError):
                self._event({"invalid_payload": repr(message)}, source)
                return set()
        if not isinstance(message, Mapping):
            self._event(message, source)
            return set()
        original = message
        for _ in range(4):
            if "method" in message or not isinstance(message.get("data"), Mapping):
                break
            message = message["data"]
        if message.get("method") == "properties_changed":
            params = message.get("params")
            if isinstance(params, list):
                return self.merge_properties(params, source=source)
            if isinstance(params, Mapping):
                if property_coordinate(params) is not None:
                    return self.merge_properties([params], source=source)
                return self.merge_cached(params, source=source)
        # Events, device info (_otc.info), custom methods and malformed known
        # notifications remain observable, including the original envelope.
        self._event(original, source)
        return set()

    def snapshot(self) -> dict[str, Any]:
        """Return an independent JSON-compatible private snapshot."""
        return deepcopy({
            "model": self.model, "properties": self.properties, "cached": self.cached,
            "events": list(self.events), "dropped_events": self.dropped_events,
            "dropped_properties": self.dropped_properties,
            "dropped_cached_keys": self.dropped_cached_keys,
        })
