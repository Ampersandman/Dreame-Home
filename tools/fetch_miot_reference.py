"""Fetch public MIoT washer candidate schemas, without account credentials."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
INDEX_URL = "https://miot-spec.org/miot-spec-v2/instances?status=all"
CANDIDATES = {"dreame.washer.r1111", "dreame.washer.r1112"}


def main():
    index_path = ROOT / "references/miot-instances.json"
    if not index_path.exists():
        with urlopen(INDEX_URL, timeout=30) as response:
            index_path.write_bytes(response.read())
    index = json.loads(index_path.read_bytes())
    out = ROOT / "references/miot"
    out.mkdir(parents=True, exist_ok=True)
    provenance = {
        "index_url": INDEX_URL,
        "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "scope": "Candidate debug schemas, not verified L9 washer/dryer identities.",
        "instances": [],
    }
    for instance in index["instances"]:
        if instance["model"] not in CANDIDATES:
            continue
        url = "https://miot-spec.org/miot-spec-v2/instance?" + urlencode({"type": instance["type"]})
        with urlopen(url, timeout=30) as response:
            data = response.read()
        schema = json.loads(data)
        (out / f"{instance['model']}.json").write_bytes(data)
        provenance["instances"].append({**instance, "url": url, "sha256": hashlib.sha256(data).hexdigest()})
        count = sum(len(s.get("properties", [])) for s in schema.get("services", []))
        print(f"{instance['model']}: {instance['status']}, {count} properties, {schema.get('description')}")
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
