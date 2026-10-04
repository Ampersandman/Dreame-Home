"""Capture metadata, referenced definitions and passive updates without controls."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dreamehome import Device, DreameHomeClient
from dreamehome.exceptions import AuthenticationError, DreameError, RateLimitError
from dreamehome.mqtt import DeviceSubscription
from dreamehome.observations import ObservationStore
from dreamehome.privacy import redactor
from scan_cloud_account import hidden_input, public_device_record, verified_tls_probe, write_status

VACUUM_INITIAL = [(2, 1), (2, 2), (3, 1), (3, 2), (4, 1), (4, 2), (4, 3),
                  (4, 7), (4, 20), (4, 25), (4, 35), (4, 52), (4, 53), (15, 3), (15, 5)]
COORDINATE = re.compile(r"^(?:prop\.)?(\d+)\.(\d+)$")


def referenced_definitions(record):
    """Only explicit definition references, not images or arbitrary metadata URLs."""
    found = []
    for container in (record, record.get("deviceInfo", {})):
        if not isinstance(container, dict):
            continue
        for field in ("keyDefine", "liveKeyDefine", "qaKeyDefine"):
            reference = container.get(field)
            if isinstance(reference, dict) and isinstance(reference.get("url"), str):
                parsed = urlsplit(reference["url"])
                if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
                    found.append({"field": field, "version": reference.get("ver"), "url": reference["url"]})
    return list({item["url"]: item for item in found}.values())


def observed_pairs(snapshot):
    properties = snapshot.get("properties", {})
    pairs = set()
    for key in properties:
        match = COORDINATE.fullmatch(key)
        if match:
            pairs.add((int(match[1]), int(match[2])))
    return pairs


def safe_error(stage, error):
    result = {"stage": stage, "error": type(error).__name__}
    status = getattr(error, "status", None)
    if isinstance(status, int):
        result["http_status"] = status
    code = getattr(error, "code", None)
    if isinstance(code, (int, str)):
        result["api_code"] = code
    return result


async def capture(api, *, seconds, output, status=None, subscription_factory=DeviceSubscription, read_plan=None):
    if output.exists():
        raise FileExistsError("Capture output exists; choose a fresh file")
    sanitize = redactor()
    report = {
        "format_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
        "region": api.region, "read_only": True, "discovery_complete": False,
        "devices": [], "errors": [], "observation_seconds": seconds,
    }
    stores, subscriptions, attempted = {}, {}, {}

    def save(state, **extra):
        # Credentials and account/network identifiers never enter this file. The
        # allowlisted identity block keeps requested DIDs for local comparison.
        for row in report["devices"]:
            did = row["identity"]["did"]
            row["observations"] = sanitize(stores[did].snapshot())
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output)
        write_status(status, state, output=str(output),
                     devices=[{"model": row["identity"]["model"],
                               "property_count": len(stores[row["identity"]["did"]].snapshot().get("properties", {})),
                               "mqtt_connected": bool(subscriptions.get(row["identity"]["did"]) and subscriptions[row["identity"]["did"]].connected),
                               "message_count": row.get("message_count", 0),
                               "definition_count": len(row["definitions"]),
                               "errors": row["errors"]} for row in report["devices"]], **extra)

    async def read_pairs(device, row, pairs):
        fresh = sorted(set(pairs) - attempted[device.did])
        # Only observed coordinates or the bounded, exact-model vacuum plan.
        for start in range(0, min(len(fresh), 300), 15):
            batch = fresh[start:start + 15]
            attempted[device.did].update(batch)
            try:
                results = await api.read_properties(device, batch)
                stores[device.did].merge_properties(results, source="rpc")
                row.setdefault("rpc_results", []).extend(sanitize(results))
            except (AuthenticationError, RateLimitError):
                raise
            except (DreameError, OSError, ValueError) as error:
                row["errors"].append(safe_error("read_properties", error))
                break

    try:
        devices = await api.list_devices()
        report["discovery_complete"] = True
        for original in devices:
            row = {"identity": public_device_record(original), "errors": [], "definitions": [], "message_count": 0, "messages": []}
            stores[original.did] = ObservationStore(original.model)
            attempted[original.did] = set()
            report["devices"].append(row)
            device = original
            info = {}
            try:
                info = await api.get_device_info(device.did)
                if isinstance(info, dict):
                    device = Device.from_record({**device.raw, **info})
                    row["identity"] = public_device_record(device)
            except (AuthenticationError, RateLimitError):
                raise
            except (DreameError, OSError, ValueError) as error:
                row["errors"].append(safe_error("device_info", error))
            row["metadata"] = sanitize(device.raw)
            stores[device.did].merge_cached(device.raw.get("property", {}))
            try:
                row["otc_info"] = sanitize(await api.get_otc_info(device.did))
            except (AuthenticationError, RateLimitError):
                raise
            except (DreameError, OSError, ValueError) as error:
                row["errors"].append(safe_error("otc_info", error))
            for reference in referenced_definitions({**original.raw, **device.raw}):
                entry = {"field": reference["field"], "version": reference["version"]}
                try:
                    blob = await api.download(reference["url"])
                    document = json.loads(blob)
                    # These are documents fetched without account headers. Keep
                    # property names intact; generic metadata redaction removes
                    # 'name', which is useful schema information here.
                    entry.update(document=document, sha256=hashlib.sha256(blob).hexdigest(),
                                 source_url=reference["url"], bytes=len(blob))
                except (DreameError, OSError, ValueError) as error:
                    entry["error"] = type(error).__name__
                row["definitions"].append(entry)
            pairs = observed_pairs(stores[device.did].snapshot())
            if device.model == "dreame.vacuum.r5023a":
                pairs.update(VACUUM_INITIAL)
            if pairs:
                await read_pairs(device, row, pairs)

            def on_message(message, *, target_row=row, target_store=stores[device.did]):
                target_row["message_count"] += 1
                target_store.merge_push(message)
                if len(target_row["messages"]) < 1000:
                    target_row["messages"].append(sanitize(message))

            subscription = subscription_factory(api, device, on_message)
            subscriptions[device.did] = subscription
            try:
                await subscription.start()
            except (AuthenticationError, RateLimitError):
                raise
            except (DreameError, OSError, ValueError, RuntimeError) as error:
                row["errors"].append(safe_error("mqtt_start", error))
            save("collecting")
            print(f"Prepared {device.model}; observing read-only cloud updates.", flush=True)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while loop.time() < deadline:
            await asyncio.sleep(min(5, deadline - loop.time()))
            if read_plan and read_plan.exists():
                plan = json.loads(read_plan.read_text(encoding="utf-8"))
                if plan.get("source") != "verified-model-plugin":
                    raise ValueError("Read plans need verified model-plugin provenance")
                for row in report["devices"]:
                    model = row["identity"]["model"]
                    specification = plan.get("models", {}).get(model)
                    if not specification:
                        continue
                    source = (ROOT / specification["source_file"]).resolve()
                    source.relative_to((ROOT / "private" / "plugins").resolve())
                    if hashlib.sha256(source.read_bytes()).hexdigest() != specification["sha256"]:
                        raise ValueError("Read-plan plugin hash mismatch")
                    pairs = specification["pairs"]
                    if len(pairs) > 300 or any(len(p) != 2 or any(type(i) is not int or i < 1 for i in p) for p in pairs):
                        raise ValueError("Invalid bounded property read plan")
                    did = row["identity"]["did"]
                    await read_pairs(subscriptions[did].device, row, {tuple(pair) for pair in pairs})
            save("observing", seconds_remaining=max(0, round(deadline - loop.time())))
        for row in report["devices"]:
            did = row["identity"]["did"]
            await read_pairs(subscriptions[did].device, row, observed_pairs(stores[did].snapshot()))
            subscription = subscriptions[did]
            if subscription.last_error:
                row["errors"].append({"stage": "mqtt", "error": subscription.last_error})
            row["mqtt_connected_at_end"] = subscription.connected
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        save("complete")
        return report
    finally:
        for subscription in subscriptions.values():
            await subscription.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="eu")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", type=Path)
    args = parser.parse_args()
    state, code = "starting", 1
    try:
        if args.output.exists():
            raise FileExistsError("Output exists; choose a new capture path")
        if not 0 <= args.seconds <= 3600:
            raise ValueError("Observation duration must be between 0 and 3600 seconds")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        print("Read-only Dreame API capture for all registered devices.")
        print("Open each appliance in DreameHome during the observation period to collect its displayed states.")
        print("This tool does not change settings or start appliance actions.")
        api = DreameHomeClient(region=args.region)
        state = "tls_preflight"
        write_status(args.status, state)
        verified_tls_probe(api)
        state = "waiting_for_login"
        write_status(args.status, state)
        refresh = os.environ.get("DREAME_REFRESH_TOKEN")
        username = os.environ.get("DREAME_USERNAME") or (hidden_input("Dreame email/ID (hidden): ").strip() if not refresh else "")
        password = os.environ.get("DREAME_PASSWORD") or (hidden_input("Dreame password (hidden): ") if not refresh else "")
        api = DreameHomeClient(username, password, region=args.region, refresh_token=refresh)
        state = "collecting"
        report = asyncio.run(capture(api, seconds=args.seconds, output=args.output, status=args.status))
        print(f"Saved {len(report['devices'])} devices to {args.output}")
        code = 0
    except KeyboardInterrupt:
        write_status(args.status, "cancelled", stage=state)
        code = 130
    except Exception as error:
        # Never print server response/error repr, headers, credentials or URLs.
        print(f"Capture could not finish ({type(error).__name__}, stage: {state}).")
        write_status(args.status, "failed", **safe_error(state, error))
    finally:
        if sys.stdin.isatty():
            try:
                input("Press Enter to close this window...")
            except (EOFError, KeyboardInterrupt):
                pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
