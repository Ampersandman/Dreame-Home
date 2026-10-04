"""Retrieve the app's model-specific plugins through a source-backed GET route."""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dreamehome import DreameHomeClient
from dreamehome.exceptions import AuthenticationError, DreameError, RateLimitError
from dreamehome.privacy import redactor
from scan_cloud_account import hidden_input, public_device_record, verified_tls_probe, write_status
from capture_device_api import capture


def plugin_urls(value):
    urls = set()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            for key, field in item.items():
                if isinstance(field, (dict, list)):
                    pending.append(field)
                elif isinstance(field, str) and key.lower() in {"url", "downloadurl", "pluginurl", "pkgurl", "packageurl", "newurl", "respackageurl", "androidpluginurl", "iospluginurl", "ohospluginurl"}:
                    parsed = urlsplit(field)
                    if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
                        urls.add(field)
    return sorted(urls)


async def fetch(api, output, status):
    sanitize = redactor()
    result = {"captured_at": datetime.now(timezone.utc).isoformat(), "region": api.region,
              "routes": ["GET /dreame-product/upgrades/appplugin", "GET /dreame-product/upgrades/h5plugin"], "devices": []}
    downloaded = {}

    def save():
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for device in await api.list_devices():
        row = {"identity": public_device_record(device), "variants": []}
        result["devices"].append(row)
        for kind, function in (("h5", api.h5_plugin_manifest), ("rn", api.plugin_manifest)):
            for os_code in (0, 1):
                variant = {"kind": kind, "os_code": os_code, "app_version": 102060603, "downloads": []}
                row["variants"].append(variant)
                try:
                    manifest = await function(device, os_code=os_code, app_version=102060603)
                    variant["manifest"] = sanitize(manifest)
                    save()
                    for url in plugin_urls(manifest):
                        download = {"source_url": url}
                        variant["downloads"].append(download)
                        if url in downloaded:
                            download.update(downloaded[url], reused=True)
                            continue
                        try:
                            payload = await api.download(url)
                            extension = Path(urlsplit(url).path).suffix.lower()
                            if extension not in {".zip", ".json", ".gz", ".js", ".bundle"}:
                                extension = ".bin"
                            url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
                            destination = output.parent / "plugins" / f"{device.model}-{kind}-{os_code}-{url_hash}{extension}"
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            with destination.open("xb") as target:
                                target.write(payload)
                            fields = dict(path=str(destination.relative_to(ROOT)), bytes=len(payload),
                                          sha256=hashlib.sha256(payload).hexdigest())
                            downloaded[url] = fields
                            download.update(fields)
                        except (DreameError, OSError, ValueError) as error:
                            download["error"] = type(error).__name__
                except (AuthenticationError, RateLimitError):
                    raise
                except (DreameError, OSError, ValueError) as error:
                    variant["error"] = type(error).__name__
                    if hasattr(error, "code"):
                        variant["api_code"] = error.code
                save()
                write_status(status, "fetching", model=device.model, kind=kind, os_code=os_code)
                print(f"Fetched {kind} plugin metadata for {device.model} (OS {os_code})", flush=True)
    write_status(status, "complete", output=str(output), devices=[{
        "model": row["identity"]["model"],
        "downloads": sum(len([d for d in v["downloads"] if "sha256" in d]) for v in row["variants"]),
    } for row in result["devices"]])


async def research(api, output, status):
    if output.name == "device-api-online-validation.json":
        write_status(status, "using_downloaded_plugins", output=str(output))
    else:
        await fetch(api, output, status)
    capture_path = output.with_name(output.stem + "-observations.json")
    print("Keeping this local session for five minutes of read-only updates and source-backed property reads.", flush=True)
    await capture(api, seconds=300, output=capture_path,
                  status=output.with_name(output.stem + "-observations.status.json"),
                  read_plan=ROOT / "private" / "verified-property-read-plan.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="eu")
    parser.add_argument("--output", type=Path, default=ROOT / "private/plugin-variants.json")
    parser.add_argument("--status", type=Path, default=ROOT / "private/plugin-variants.status.json")
    args = parser.parse_args()
    if args.output == ROOT / "private/plugin-variants.json" and args.output.exists():
        args.output = ROOT / "private/device-api-online-validation.json"
        args.status = ROOT / "private/device-api-online-validation.status.json"
    try:
        if args.output.exists():
            raise FileExistsError("Output exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_status(args.status, "tls_preflight")
        api = DreameHomeClient(region=args.region)
        verified_tls_probe(api)
        write_status(args.status, "waiting_for_login")
        print("Read-only Dreame app-plugin discovery for the connected models.")
        print("Credentials remain in this process only; downloaded app assets stay in private/.")
        refresh = os.environ.get("DREAME_REFRESH_TOKEN")
        username = os.environ.get("DREAME_USERNAME") or (hidden_input("Dreame email/ID (hidden): ").strip() if not refresh else "")
        password = os.environ.get("DREAME_PASSWORD") or (hidden_input("Dreame password (hidden): ") if not refresh else "")
        api = DreameHomeClient(username, password, region=args.region, refresh_token=refresh)
        asyncio.run(research(api, args.output, args.status))
        print(f"Saved plugin results to {args.output}")
        return 0
    except KeyboardInterrupt:
        write_status(args.status, "cancelled")
        return 130
    except Exception as error:
        print(f"Plugin discovery could not finish ({type(error).__name__}).")
        write_status(args.status, "failed", error=type(error).__name__)
        return 1
    finally:
        if sys.stdin.isatty():
            try:
                input("Press Enter to close this window...")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
