"""Read-only inventory capture for unknown Dreame device categories."""

from __future__ import annotations

from datetime import datetime, timezone

from .catalog import load_catalog
from .client import DreameHomeClient
from .exceptions import DreameError, SchemaRequiredError
from .miot import schema_for_model
from .models import Device


async def capture_inventory(api: DreameHomeClient, *, model: str | None = None, property_pairs=None, read_schema=False, allow_debug=False, label="snapshot"):
    report = {
        "format_version": 1, "label": label,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "region": api.region, "account_type": api.account_type,
        "upstream_commit": load_catalog("provenance")["commit"],
        "discovery_complete": False, "pages": [], "devices": [], "errors": [],
    }
    records = {}
    try:
        async for response in api.device_pages():
            report["pages"].append(response)
            for record in response["data"]["page"]["records"]:
                records[str(record["did"])] = record
        report["discovery_complete"] = True
    except DreameError as error:
        report["errors"].append({"stage": "discovery", "error": type(error).__name__})
    for record in records.values():
        device = Device.from_record(record)
        if model and device.model != model:
            continue
        row = {"record": record, "errors": []}
        for name, function in (("device_info", api.get_device_info), ("otc_info", api.get_otc_info)):
            try:
                row[name] = await function(device.did)
                if name == "device_info" and isinstance(row[name], dict):
                    device = Device.from_record({**device.raw, **row[name]})
            except DreameError as error:
                row["errors"].append({"stage": name, "error": type(error).__name__})
        pairs = list(property_pairs or [])
        try:
            candidate = schema_for_model(device.model, allow_debug=True)
        except SchemaRequiredError:
            candidate = None
        if candidate:
            row["schema_candidate"] = {
                "model": candidate["model"], "status": candidate["status"],
                "live_verified": False, "source_url": candidate["source_url"],
            }
        if read_schema:
            try:
                schema = schema_for_model(device.model, allow_debug=allow_debug)
                pairs += [(p["siid"], p["piid"]) for p in schema["properties"] if "read" in p["access"]]
            except SchemaRequiredError as error:
                row["errors"].append({"stage": "schema", "error": type(error).__name__})
        if pairs:
            try:
                row["properties"] = await api.read_properties(device, sorted(set(pairs)))
            except DreameError as error:
                row["errors"].append({"stage": "property_reads", "error": type(error).__name__})
        report["devices"].append(row)
    if model and not report["devices"]:
        report["errors"].append({"stage": "selection", "error": "ModelNotInDeviceList"})
    return report
