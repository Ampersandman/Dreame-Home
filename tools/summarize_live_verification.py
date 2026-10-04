"""Publish allowlisted coverage facts without device IDs or property values."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(source: Path) -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("read_only") is not True or data.get("discovery_complete") is not True:
        raise ValueError("Coverage evidence must be a complete read-only capture")
    devices = []
    for item in data["devices"]:
        results = []
        for row in item.get("rpc_results", []):
            siid, piid = row.get("siid"), row.get("piid")
            if type(siid) is not int or type(piid) is not int or min(siid, piid) < 1:
                raise ValueError("Invalid property coordinate")
            code = row.get("code")
            if type(code) is not int:
                raise ValueError("Unexpected RPC result code")
            results.append({"coordinate": f"{siid}.{piid}", "code": code,
                            "has_value": row.get("value") is not None})
        observations = item.get("observations", {}).get("properties", {})
        successful = sorted(key for key, row in observations.items()
                            if row.get("value") is not None
                            and row.get("last_code") in (None, 0, "0"))
        identity = item["identity"]
        devices.append({
            "model": identity["model"], "firmware": identity.get("firmware"),
            "rpc_results": sorted(results, key=lambda row: row["coordinate"]),
            "rpc_success_count": sum(row["code"] == 0 for row in results),
            "rpc_value_count": sum(row["code"] == 0 and row["has_value"] for row in results),
            "observed_value_coordinates": successful,
            "observed_value_count": len(successful),
            "mqtt_message_count": item.get("message_count", 0),
            "mqtt_connected_at_end": item.get("mqtt_connected_at_end") is True,
            "error_count": len(item.get("errors", [])),
        })
    return {
        "format_version": 1, "captured_at": data["captured_at"],
        "completed_at": data["completed_at"], "region": data["region"],
        "read_only": True, "discovery_complete": True,
        "observation_seconds": data["observation_seconds"],
        "private_capture_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "devices": sorted(devices, key=lambda row: row["model"]),
        "error_count": len(data.get("errors", [])),
        "limits": ["One owned-device EU account, reported firmware only",
                   "No writes, appliance actions, cycles or Home Assistant runtime tested",
                   "Observation counts combine MQTT and successful RPC values; null RPCs do not erase earlier MQTT evidence"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "private/device-api-online-validation-observations.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/live-verification.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(summarize(args.input), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if args.output.read_text(encoding="utf-8") != content:
            raise SystemExit("Live verification summary differs")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print("Verified coverage facts" if args.check else "Saved coverage facts without identifiers or values")


if __name__ == "__main__":
    main()
