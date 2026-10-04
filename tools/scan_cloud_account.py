"""Interactive, read-only account identification; never persist credentials."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dreamehome import Device, DreameHomeClient
from dreamehome.catalog import known_vacuum_model
from dreamehome.exceptions import ApiError, AuthenticationError, DreameError, IncompleteDiscoveryError, RateLimitError, TransportError
from dreamehome.miot import schema_for_model


def public_device_record(device: Device, info: dict | None = None) -> dict:
    """Allowlisted identification fields, including the exact requested DID."""
    raw = {**device.raw, **(info or {})}
    product = raw.get("deviceInfo")
    if not isinstance(product, dict):
        product = {}
    model = str(raw.get("model") or device.model)
    result = {
        "did": str(raw.get("did") or device.did),
        "model": model,
        "product_name": product.get("displayName") or product.get("name"),
        "assigned_name": raw.get("customName") or None,
        "firmware": raw.get("ver") or raw.get("fwVersion") or raw.get("firmwareVersion"),
        "product_id": raw.get("productId") or product.get("productId"),
        "shared": (not raw["master"]) if isinstance(raw.get("master"), bool) else None,
        "known_vacuum_model": known_vacuum_model(model),
    }
    # Keep schema identifiers, but never plugin download URLs or signed URLs.
    for key in ("spec_type", "specType", "schemaVersion", "extensionId", "pluginId"):
        value = raw.get(key, product.get(key))
        if isinstance(value, (str, int, float, bool)) and not (isinstance(value, str) and "://" in value):
            result[key] = value
    try:
        candidate = schema_for_model(model, allow_debug=True)
    except DreameError:
        candidate = None
    if candidate:
        result["schema_candidate"] = {
            "type": candidate["schema_type"], "registry_status": candidate["status"],
            "live_verified": False,
            "properties": len(candidate["properties"]), "actions": len(candidate["actions"]),
            "events": len(candidate["events"]),
        }
    return result


def bodyless_records(response: dict) -> tuple[list[Device], bool]:
    """Use upstream's original listing without claiming partial pages are complete."""
    try:
        page = response["data"]["page"]
        records = page["records"]
        if not isinstance(records, list):
            raise TypeError
        devices = {str(record["did"]): Device.from_record(record) for record in records}
        total = int(page["total"]) if page.get("total") is not None else None
        pages = int(page["pages"]) if page.get("pages") is not None else None
        current = int(page.get("current", 1))
        complete = total is not None and total <= len(devices) and (pages is None or pages <= 1) and current == 1
    except (KeyError, TypeError, ValueError):
        raise TransportError("Unexpected bodyless device list shape") from None
    return list(devices.values()), complete


async def scan(api: DreameHomeClient) -> dict:
    warnings_list = []
    try:
        devices = await api.list_devices()
        complete = True
    except (AuthenticationError, RateLimitError):
        raise
    except (ApiError, IncompleteDiscoveryError):
        # This known read-only request is present in the original source.
        devices, complete = bodyless_records(await api.list_devices_response())
        warnings_list.append("Used upstream bodyless device listing after paginated listing was rejected or incomplete")
    projected = []
    for device in devices:
        info = None
        try:
            info = await api.get_device_info(device.did)
            if not isinstance(info, dict):
                info = None
                warnings_list.append(f"Device metadata unavailable for model {device.model}")
        except (AuthenticationError, RateLimitError):
            raise
        except (DreameError, KeyError, TypeError):
            warnings_list.append(f"Device metadata unavailable for model {device.model}")
        projected.append(public_device_record(device, info))
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "region": api.region, "account_type": api.account_type,
        "discovery_complete": complete, "device_count": len(projected),
        "devices": projected, "warnings": warnings_list,
    }


def verified_tls_probe(api: DreameHomeClient):
    """Handshake only, before credentials are entered; no login request."""
    host = api.region + api.profile["domain_suffix"]
    context = ssl.create_default_context()
    with socket.create_connection((host, api.profile["port"]), timeout=10) as tcp:
        with context.wrap_socket(tcp, server_hostname=host):
            pass


def write_status(path: Path | None, state: str, **fields):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"state": state, **fields}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def hidden_input(prompt: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="eu")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--no-pause", action="store_true")
    args = parser.parse_args()
    state = "starting"
    exit_code = 1
    try:
        if args.output.exists():
            raise FileExistsError("Output already exists")
        print("Dreame cloud: read-only identification of connected devices.")
        print("Credentials stay in process memory and are never saved to the results.")
        if not os.environ.get("DREAME_REFRESH_TOKEN"):
            write_status(args.status, "waiting_for_region")
            chosen = input(f"App server region [{args.region}]: ").strip().lower()
            if chosen:
                args.region = chosen
        api = DreameHomeClient(region=args.region)
        state = "tls_preflight"
        write_status(args.status, state, region=args.region)
        print("Checking the cloud connection with verified TLS...")
        verified_tls_probe(api)
        print("Verified TLS connection succeeded.")
        refresh = os.environ.get("DREAME_REFRESH_TOKEN")
        state = "waiting_for_login"
        write_status(args.status, state, region=args.region)
        username = os.environ.get("DREAME_USERNAME") or (hidden_input("Dreame email/ID (hidden): ").strip() if not refresh else "")
        password = os.environ.get("DREAME_PASSWORD") or (hidden_input("Dreame password (hidden): ") if not refresh else "")
        api = DreameHomeClient(username, password, region=args.region, refresh_token=refresh)
        state = "scanning"
        write_status(args.status, state, region=args.region)
        print("Identifying registered devices...")
        result = asyncio.run(scan(api))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
        print(f"Saved {result['device_count']} device identifications to {args.output}")
        for device in result["devices"]:
            print(f"{device['product_name'] or device['assigned_name'] or 'Device'}: {device['model']} / DID {device['did']}")
        if not result["discovery_complete"]:
            print("The returned list may be incomplete; pagination still needs confirmation.")
        exit_code = 0
        write_status(args.status, "complete", output=str(args.output), device_count=result["device_count"], discovery_complete=result["discovery_complete"])
    except AuthenticationError:
        print("Cloud login/access was rejected. Check account region and credentials; server fingerprint filtering can also reject valid credentials.")
        write_status(args.status, "failed", stage=state, error="AuthenticationError")
    except (DreameError, OSError, ValueError, getpass.GetPassWarning, EOFError) as error:
        # No repr of the exception, server body, credentials, headers or URLs.
        print(f"The scan could not finish ({type(error).__name__}, stage: {state}).")
        fields = {"stage": state, "error": type(error).__name__}
        if isinstance(error, ApiError):
            fields["http_status"] = error.status
        write_status(args.status, "failed", **fields)
    except KeyboardInterrupt:
        exit_code = 130
        write_status(args.status, "cancelled", stage=state)
    finally:
        if not args.no_pause and sys.stdin.isatty():
            try:
                input("Press Enter to close this window...")
            except (EOFError, KeyboardInterrupt):
                pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
