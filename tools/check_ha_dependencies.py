"""Check the component's pinned/minimum releases against public PyPI metadata."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "custom_components/dreame_home/manifest.json").read_text())
    packages = []
    for requirement in manifest["requirements"]:
        parsed = re.fullmatch(r"([a-z0-9-]+)(==|>=)([0-9.]+)(?:,<([0-9]+))?", requirement)
        if parsed is None:
            raise ValueError("Review a changed dependency format before checking it")
        name, operator, version, upper = parsed.groups()
        if name not in {"pycryptodome", "paho-mqtt"}:
            raise ValueError("Review any new dependency before extending this verifier")
        url = f"https://pypi.org/pypi/{name}/json"
        with urllib.request.urlopen(url, timeout=30) as response:
            metadata = json.load(response)
        files = metadata["releases"].get(version, [])
        packages.append({
            "package": name, "requirement": requirement, "requested_version": version,
            "metadata_url": url, "latest_version": metadata["info"]["version"],
            "requested_release_exists": bool(files),
            "release_files": [{"filename": item["filename"],
                               "sha256": item["digests"]["sha256"],
                               "yanked": item["yanked"]} for item in files],
        })
    record = {"checked_at": datetime.now(timezone.utc).isoformat(), "packages": packages}
    output = ROOT / "references/ha-os-package-check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    for package in packages:
        print(json.dumps({key: package[key] for key in (
            "package", "requested_version", "latest_version", "requested_release_exists")}))
    return 0 if all(package["requested_release_exists"] for package in packages) else 1


if __name__ == "__main__":
    raise SystemExit(main())
