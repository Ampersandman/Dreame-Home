"""Exact L9 plugin definitions, without claiming firmware or live coverage.

Subscription coordinates are safe read candidates, not proof that a particular
device implements get_properties. Consumers must require successful returned
values before creating entities. Actions and write-only fields never seed reads.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping

from .catalog import load_catalog

LAUNDRY_CATALOGS = {
    "dreame.washer.l9nacn": "l9_washer",
    "dreame.dryer.l9nacn": "l9_dryer",
}


def enum_label(definition: Mapping[str, Any] | None, value: Any) -> str | None:
    """Translate only exact source mappings; preserve unknown codes and types."""
    if (not definition or definition.get("value_list_inferred") is True
            or isinstance(value, (bool, dict, list))):
        return None
    for item in definition.get("value_list") or ():
        if not isinstance(item, dict):
            continue
        code = item.get("value")
        # Numeric strings are deliberately not coerced into integer enum codes.
        if type(code) is type(value) and code == value:
            label = item.get("label")
            if isinstance(label, str) and label:
                return label
    return None


@dataclass(frozen=True)
class LaundrySchema:
    model: str
    properties: Mapping[str, dict[str, Any]]
    read_pairs: tuple[tuple[int, int], ...]
    direct_read_pairs: tuple[tuple[int, int], ...]
    source: Mapping[str, Any]
    live_verified: bool
    cloud_properties: Mapping[str, dict[str, Any]] = field(default_factory=dict)

    def definition(self, key: str, pointer: str | None = None) -> dict[str, Any] | None:
        root = (self.cloud_properties.get(key[7:]) if key.startswith("cached:")
                else self.properties.get(key))
        if not root:
            return None
        if pointer is None:
            return root
        # Compound leaf enums/units require their own explicit source mapping.
        fields = root.get("fields", {})
        if isinstance(fields, dict) and isinstance(fields.get(pointer), dict):
            return fields[pointer]
        if isinstance(fields, list):
            for item in fields:
                if isinstance(item, dict) and item.get("pointer") == pointer:
                    return item
        return {"name": f"{root.get('label') or root['name']} {pointer}"}

    def coverage(self, observations: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
        """Separate vendor definitions, read candidates, and successful live data."""
        candidates = {f"{siid}.{piid}" for siid, piid in self.read_pairs}
        supported = {key for key, row in observations.items()
                     if key in candidates and row.get("value") is not None
                     and row.get("last_code") in (None, 0, "0")}
        observed = {key for key, row in observations.items()
                    if row.get("value") is not None
                    and row.get("last_code") in (None, 0, "0")}
        failed = {key for key, row in observations.items()
                  if key in candidates and row.get("last_code") not in (None, 0, "0")}
        return {
            "model": self.model, "source_live_verified": self.live_verified,
            "definition_count": len(self.properties),
            "read_candidate_count": len(candidates),
            "direct_read_count": len(self.direct_read_pairs),
            "successful_value_count": len(supported),
            "successful_observed_count": len(observed),
            "failed_coordinates": sorted(failed),
            "unobserved_coordinates": sorted(candidates - set(observations)),
            "all_candidate_values_observed": supported == candidates,
            "controls_enabled": False,
        }


@lru_cache(maxsize=None)
def laundry_schema(model: str) -> LaundrySchema | None:
    """Return definitions only for the exact model that supplied the plugin."""
    catalog_name = LAUNDRY_CATALOGS.get(model)
    if catalog_name is None:
        return None
    data = load_catalog(catalog_name)
    if data.get("model") != model:
        raise ValueError("Laundry catalog does not match its exact model")
    properties = {}
    candidates, direct = [], []
    for original in data.get("properties", ()):
        row = deepcopy(original)
        siid, piid = row.get("siid"), row.get("piid")
        if type(siid) is not int or type(piid) is not int or min(siid, piid) < 1:
            raise ValueError("Invalid laundry property coordinate")
        key = f"{siid}.{piid}"
        if key in properties:
            raise ValueError("Duplicate laundry property coordinate")
        row.setdefault("name", key)
        access = row.get("access", ())
        row["read_candidate"] = ("read" in access or "notify" in access
                                 or row.get("read_observed") is True)
        row.setdefault("read_observed", False)
        row.setdefault("live_verified", False)
        properties[key] = row
        if row["read_candidate"]:
            candidates.append((siid, piid))
        if "read" in access or row.get("read_observed") is True:
            direct.append((siid, piid))
    cloud_properties = {row["key"]: deepcopy(row) for row in data.get("cloud_property_keys", ())
                        if isinstance(row, dict) and isinstance(row.get("key"), str)}
    return LaundrySchema(model, properties, tuple(candidates), tuple(direct),
                         deepcopy(data.get("source", {})), data.get("live_verified") is True,
                         cloud_properties)


def laundry_read_pairs(model: str) -> list[tuple[int, int]]:
    """One bounded initial validation plan; never any action invocation."""
    schema = laundry_schema(model)
    return list(schema.read_pairs) if schema else []


def laundry_definition(model: str, key: str, pointer: str | None = None):
    schema = laundry_schema(model)
    return schema.definition(key, pointer) if schema else None


def laundry_cloud_read_keys(model: str) -> list[str]:
    """Only explicitly extracted readable cloud userdata keys."""
    schema = laundry_schema(model)
    if not schema:
        return []
    return [key for key, row in schema.cloud_properties.items() if "read" in row.get("access", ())]


def laundry_cloud_values(model: str, did: str, payload: Any) -> dict[str, Any]:
    """Select known values from direct HTTP or source SDK DID-grouped mappings.

    Missing/empty settings stay absent. Never reproduce the app's default write.
    Unknown envelope fields and other devices cannot become entities.
    """
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get(did), dict):
        payload = payload[did]
    return {key: payload[key] for key in laundry_cloud_read_keys(model)
            if key in payload and isinstance(payload[key], (str, int, float, bool))}
