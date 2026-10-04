"""Load extracted data without importing Home Assistant or upstream code."""

from functools import lru_cache
from importlib.resources import files
import json

from .exceptions import SchemaRequiredError


@lru_cache(maxsize=None)
def load_catalog(name: str):
    if name not in {"api", "provenance", "properties", "actions", "models", "enums", "entities", "property_groups", "availability", "device_info", "protocol_strings", "constants", "entity_defaults", "implementations", "translations_en", "washer_candidates", "l9_washer", "l9_dryer"}:
        raise ValueError("Unknown catalog")
    return json.loads(files(__package__).joinpath("data", f"{name}.json").read_text(encoding="utf-8"))


def known_vacuum_model(model: str) -> bool:
    return any(row["model"] == model for row in load_catalog("models"))


def vacuum_property_pairs(model: str) -> list[tuple[int, int]]:
    """Candidates, not proof of model support. Never apply to a washer/dryer."""
    if not known_vacuum_model(model):
        raise SchemaRequiredError(f"No extracted vacuum schema for {model}")
    return sorted({(p["mapping"]["siid"], p["mapping"]["piid"]) for p in load_catalog("properties") if p["mapping"] and "piid" in p["mapping"]})
