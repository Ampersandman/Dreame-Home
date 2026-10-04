"""Normalize downloaded MIoT candidates. These are NOT verified L9 identities."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dreamehome.miot import flatten_schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = ROOT / "references/miot"
    provenance = json.loads((source / "provenance.json").read_text(encoding="utf-8"))
    candidates = []
    for instance in provenance["instances"]:
        path = source / f"{instance['model']}.json"
        if hashlib.sha256(path.read_bytes()).hexdigest() != instance["sha256"]:
            raise SystemExit(f"Source hash differs: {path}")
        schema = json.loads(path.read_bytes())
        candidates.append({
            "model": instance["model"], "status": instance["status"],
            "marketing_name": None, "live_verified": False,
            "source_url": instance["url"], "source_sha256": instance["sha256"],
            **flatten_schema(schema),
        })
    output = ROOT / "src/dreamehome/data/washer_candidates.json"
    encoded = json.dumps(candidates, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if output.read_text(encoding="utf-8") != encoded:
            raise SystemExit("MIoT extraction differs")
    else:
        output.write_text(encoded, encoding="utf-8", newline="\n")
    print({c["model"]: {key: len(c[key]) for key in ("properties", "actions", "events")} for c in candidates})


if __name__ == "__main__":
    main()
