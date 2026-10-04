"""MIoT candidate normalization; schemas must match the actual cloud model."""

from typing import Any

from .catalog import load_catalog
from .exceptions import SchemaRequiredError


def flatten_schema(schema: dict[str, Any]) -> dict[str, Any]:
    properties, actions, events = [], [], []
    for service in schema.get("services", []):
        siid = service["iid"]
        common = {"siid": siid, "service": service.get("description"), "service_type": service.get("type")}
        for prop in service.get("properties", []):
            access = prop.get("access", [])
            platform = "binary_sensor" if prop.get("format") == "bool" else "sensor"
            control = None
            if "write" in access:
                control = "switch" if prop.get("format") == "bool" else "select" if prop.get("value-list") else "number" if prop.get("value-range") else "text" if prop.get("format") == "string" else None
            properties.append({
                **common, "piid": prop["iid"], "name": prop.get("description"), "type": prop.get("type"),
                "format": prop.get("format"), "access": access, "unit": prop.get("unit"),
                "value_range": prop.get("value-range"), "value_list": prop.get("value-list"),
                "suggested_state_platform": platform if "read" in access or "notify" in access else None,
                "suggested_control_platform": control,
            })
        for action in service.get("actions", []):
            actions.append({**common, "aiid": action["iid"], "name": action.get("description"), "type": action.get("type"), "in": action.get("in", []), "out": action.get("out", [])})
        for event in service.get("events", []):
            events.append({**common, "eiid": event["iid"], "name": event.get("description"), "type": event.get("type"), "arguments": event.get("arguments", [])})
    return {"schema_type": schema.get("type"), "description": schema.get("description"), "properties": properties, "actions": actions, "events": events}


def schema_for_model(model: str, *, allow_debug: bool = False) -> dict[str, Any]:
    for candidate in load_catalog("washer_candidates"):
        if candidate["model"] == model:
            if candidate["status"] != "released" and not allow_debug:
                raise SchemaRequiredError("Exact model has only a debug MIoT candidate; enable it explicitly after checking device identity")
            return candidate
    raise SchemaRequiredError(f"No matching MIoT schema for {model}; obtain its plugin or observe its own property messages")
