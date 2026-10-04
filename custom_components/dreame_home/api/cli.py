"""Inventory and evidence capture. This CLI never writes device properties."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path

from .catalog import load_catalog
from .client import DreameHomeClient
from .discovery import capture_inventory
from .exceptions import DreameError
from .laundry import LAUNDRY_CATALOGS
from .miot import schema_for_model
from .mqtt import DeviceSubscription
from .privacy import redactor


def pair(value):
    try:
        siid, piid = (int(n) for n in value.split("."))
        if siid < 1 or piid < 1:
            raise ValueError
        return siid, piid
    except ValueError:
        raise argparse.ArgumentTypeError("Use a positive SIID.PIID pair, such as 2.1") from None


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="Print extracted counts; no network or credentials")
    schema = commands.add_parser("schema", help="Show exact-model plugin definitions or a MIoT candidate; no network")
    schema.add_argument("--model", required=True)
    schema.add_argument("--allow-debug-schema", action="store_true")
    for name in ("inventory", "capture", "watch"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--region", default="eu", help="App server: eu/cn/us/ru/sg/kr/by; varies by account type")
        cmd.add_argument("--account-type", choices=("dreame", "mova", "trouver"), default="dreame")
        cmd.add_argument("--username", default=os.environ.get("DREAME_USERNAME"))
        cmd.add_argument("--model", help="Exact model from inventory; do not use the L9 marketing name")
        cmd.add_argument("--private", action="store_true", help="Preserve identifiers in local output; review before sharing")
        if name != "inventory":
            cmd.add_argument("--output", type=Path, required=True)
            cmd.add_argument("--label", default="snapshot")
        if name == "capture":
            cmd.add_argument("--property", action="append", type=pair, default=[], help="Read a known model-specific SIID.PIID; may be repeated")
            cmd.add_argument("--read-schema", action="store_true", help="Read properties in the exact matching schema")
            cmd.add_argument("--allow-debug-schema", action="store_true")
        if name == "watch":
            cmd.add_argument("--seconds", type=int, default=300)
    return root


def create_client(args):
    refresh = os.environ.get("DREAME_REFRESH_TOKEN")
    username = args.username or (input("Dreame account email/ID: ").strip() if not refresh else "")
    password = os.environ.get("DREAME_PASSWORD") or (getpass.getpass("Dreame password (hidden): ") if not refresh else "")
    return DreameHomeClient(username, password, region=args.region, account_type=args.account_type, refresh_token=refresh)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


async def run(args):
    if args.command == "catalog":
        print(json.dumps(load_catalog("provenance")["counts"], indent=2))
        return 0
    if args.command == "schema":
        catalog_name = LAUNDRY_CATALOGS.get(args.model)
        definitions = load_catalog(catalog_name) if catalog_name else schema_for_model(args.model, allow_debug=args.allow_debug_schema)
        print(json.dumps(definitions, ensure_ascii=False, indent=2))
        return 0
    if args.command == "capture" and args.read_schema:
        if not args.model:
            raise ValueError("--read-schema requires --model to match a device exactly")
        schema_for_model(args.model, allow_debug=args.allow_debug_schema)
    if args.command == "watch" and args.seconds < 1:
        raise ValueError("--seconds must be positive")
    if args.command != "inventory" and args.output.exists():
        raise FileExistsError("Choose a new output path; captures are not overwritten")
    api = create_client(args)
    await api.login()
    redact = (lambda value: value) if args.private else redactor()
    if args.command == "inventory":
        devices = await api.list_devices()
        selected = [d for d in devices if not args.model or d.model == args.model]
        print(json.dumps(redact([d.raw for d in selected]), ensure_ascii=False, indent=2))
        return 0
    if args.command == "capture":
        report = await capture_inventory(api, model=args.model, property_pairs=args.property, read_schema=args.read_schema, allow_debug=args.allow_debug_schema, label=args.label)
        write_json(args.output, redact(report))
        errors = len(report["errors"]) + sum(len(d["errors"]) for d in report["devices"])
        print(f"Saved {len(report['devices'])} device records to {args.output}; discovery_complete={report['discovery_complete']}; errors={errors}")
        return 1 if errors else 0
    devices = [d for d in await api.list_devices() if not args.model or d.model == args.model]
    if not devices:
        raise ValueError("No devices matched the requested model")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subscriptions = []
    messages = 0
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        def receive(device, payload):
            nonlocal messages
            record = {"captured_at": datetime.now(timezone.utc).isoformat(), "label": args.label, "model": device.model, "did": device.did, "data": payload}
            output.write(json.dumps(redact(record), ensure_ascii=False) + "\n")
            output.flush()
            messages += 1

        try:
            for device in devices:
                subscription = DeviceSubscription(api, device, lambda payload, d=device: receive(d, payload))
                subscriptions.append(subscription)
                await subscription.start()
            print(f"Listening to {len(subscriptions)} devices for {args.seconds} seconds")
            await asyncio.sleep(args.seconds)
        finally:
            states = [{"model": sub.device.model, "connected": sub.connected, "error": sub.last_error} for sub in subscriptions]
            for subscription in subscriptions:
                await subscription.stop()
    print(f"Saved {messages} MQTT messages to {args.output}")
    print(json.dumps(states, ensure_ascii=False))
    return 1 if messages == 0 or any(state["error"] for state in states) else 0


def main():
    args = parser().parse_args()
    try:
        return_code = asyncio.run(run(args))
    except (DreameError, ValueError, OSError, ImportError) as error:
        if isinstance(error, ImportError):
            print("MQTT capture needs the optional dependency: pip install -e '.[mqtt]'")
        elif isinstance(error, OSError):
            print(f"{type(error).__name__}: local file or network operation failed")
        else:
            print(f"{type(error).__name__}: {error}")
        return_code = 1
    except KeyboardInterrupt:
        return_code = 130
    raise SystemExit(return_code)
