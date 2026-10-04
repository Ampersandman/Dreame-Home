"""Reproducible, static extraction of Tasshack/dreame-vacuum (no imports/eval)."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
PIN = "9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb"
REPO = "https://github.com/Tasshack/dreame-vacuum"
COMPONENT = "custom_components/dreame_vacuum"


def assignments(tree):
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            yield node.target.id, node.value, node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.value, node


def expression(node):
    return {"expression": ast.unparse(node)}


def plain(node, symbols):
    """Only evaluate literals, containers and already extracted constants."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in symbols:
        return symbols[node.id]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [plain(n, symbols) for n in node.elts]
    if isinstance(node, ast.Dict):
        result = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                return expression(node)
            k = plain(key, symbols)
            if not isinstance(k, (str, int, float, bool)):
                k = ast.unparse(key)
            result[str(k)] = plain(value, symbols)
        return result
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = plain(node.operand, symbols)
        if isinstance(value, (int, float)):
            return -value
    return expression(node)


def extract(upstream: Path):
    commit = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != PIN:
        raise SystemExit(f"Expected pinned revision {PIN}; found {commit}")
    base = upstream / COMPONENT
    sources = {}
    trees = {}
    for file in sorted(base.rglob("*.py")):
        name = file.relative_to(base).as_posix()
        sources[name] = file.read_text(encoding="utf-8")
        trees[name] = ast.parse(sources[name])

    def location(name, node):
        return {
            "file": f"{COMPONENT}/{name}",
            "line": node.lineno,
            "end_line": node.end_lineno,
            "url": f"{REPO}/blob/{commit}/{COMPONENT}/{name}#L{node.lineno}",
        }

    # Resolve just literal constants, never calls or lambdas in upstream code.
    symbols = {}
    constants = {}
    for name in ("dreame/const.py", "const.py", "dreame/types.py"):
        constants[name] = {}
        for key, value, node in assignments(trees[name]):
            resolved = plain(value, symbols)
            symbols[key] = resolved
            if key != "DEVICE_INFO":
                constants[name][key] = {"value": resolved, "source": location(name, node)}

    enums = {}
    for node in trees["dreame/types.py"].body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(ast.unparse(b) in ("Enum", "IntEnum") for b in node.bases):
            continue
        members = {key: plain(value, symbols) for key, value, _ in assignments(node)}
        enums[node.name] = {"members": members, "source": location("dreame/types.py", node)}

    type_assignments = {key: (value, node) for key, value, node in assignments(trees["dreame/types.py"])}
    groups = {}
    for name in ("READ_ONLY_PROPERTIES", "READ_WRITE_PROPERTIES", "DISCARDED_PROPERTIES", "CONSUMABLE_PROPERTIES"):
        value, _ = type_assignments[name]
        groups[name] = [n.attr for n in value.elts]

    def availability(name):
        value, _ = type_assignments[name]
        return {ast.unparse(k): ast.unparse(v) for k, v in zip(value.keys, value.values)}

    rules = {name: availability(name) for name in ("PROPERTY_AVAILABILITY", "ACTION_AVAILABILITY")}

    def mappings(enum_name, mapping_name):
        value, _ = type_assignments[mapping_name]
        mapped = {}
        for key, val in zip(value.keys, value.values):
            mapped[key.attr] = (plain(val, symbols), key)
        rows = []
        for name, numeric in enums[enum_name]["members"].items():
            mapping, key = mapped.get(name, (None, None))
            rows.append({
                "name": name,
                "enum_id": numeric,
                "mapping": mapping,
                "poll_groups": [group for group, members in groups.items() if name in members],
                "source": location("dreame/types.py", key) if key else enums[enum_name]["source"],
            })
        return rows

    properties = mappings("DreameVacuumProperty", "DreameVacuumPropertyMapping")
    actions = mappings("DreameVacuumAction", "DreameVacuumActionMapping")
    protocol_assignments = {key: value for key, value, _ in assignments(trees["dreame/protocol.py"])}
    strings = json.loads(zlib.decompress(base64.b64decode(ast.literal_eval(protocol_assignments["DREAME_STRINGS"])), 31))
    const_assignments = {key: value for key, value, _ in assignments(trees["dreame/const.py"])}
    device_info = json.loads(zlib.decompress(base64.b64decode(ast.literal_eval(const_assignments["DEVICE_INFO"])), 31))
    models = []
    brands = {0: "dreame", 1: "xiaomi", 2: "mova", 3: "trouver"}
    for suffix, index in sorted(device_info[3].items()):
        row = device_info[0][index]
        if row:
            models.append({
                "model": f"{brands[row[0]]}.vacuum.{suffix}",
                "device_info_index": index,
                "device_info_row": row,
                "upstream_model_type": row[1],
                "capability_index": row[2],
                "capability_data": device_info[1][row[2]],
                "map_key_index": row[3] if len(row) > 3 else None,
            })

    entities = []
    platforms = ("sensor", "binary_sensor", "switch", "select", "number", "button", "time", "camera", "vacuum")
    for platform in platforms:
        name = f"{platform}.py"
        for node in ast.walk(trees[name]):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if not node.func.id.endswith("EntityDescription") or not node.keywords:
                continue
            fields = {kw.arg or "**": plain(kw.value, symbols) for kw in node.keywords}
            prop = next((kw.value for kw in node.keywords if kw.arg == "property_key"), None)
            action = next((kw.value for kw in node.keywords if kw.arg == "action_key"), None)
            key = fields.get("key")
            if key is None:
                key = prop.attr.lower() if isinstance(prop, ast.Attribute) else action.attr.lower() if isinstance(action, ast.Attribute) else None
            if key is None and isinstance(fields.get("name"), str):
                key = fields["name"].lower().replace(" ", "_").replace("-", "_")
            entities.append({
                "platform": platform,
                "key": key,
                "property": ast.unparse(prop) if prop is not None else None,
                "action": ast.unparse(action) if action is not None else None,
                "fields": fields,
                "source": location(name, node),
            })

    defaults = {}
    for node in trees["entity.py"].body:
        if isinstance(node, ast.ClassDef) and node.name.endswith("EntityDescription"):
            defaults[node.name] = {k: plain(v, symbols) for k, v, _ in assignments(node)}

    # Preserve encoders, computed state, model remapping and map decoder logic.
    # Source strings are reference material; the client does not execute them.
    implementations = {}
    for file, classes in {
        "dreame/protocol.py": ("DreameVacuumDreameHomeCloudProtocol", "DreameVacuumProtocol"),
        "dreame/device.py": ("DreameVacuumDevice", "DreameVacuumDeviceStatus", "DreameVacuumDeviceInfo"),
        "dreame/types.py": ("DreameVacuumDeviceCapability",),
        "dreame/map.py": ("DreameVacuumMapDecoder",),
    }.items():
        for cls in trees[file].body:
            if not isinstance(cls, ast.ClassDef) or cls.name not in classes:
                continue
            implementations[cls.name] = [{
                "name": node.name,
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "source": location(file, node),
                "implementation": ast.get_source_segment(sources[file], node),
                "property_references": sorted({n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "DreameVacuumProperty"}),
            } for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]

    endpoints = {
        "login": strings[12],
        "list_devices": "/" + "/".join(strings[i] for i in (18, 19, 22, 23)),
        "device_info": "/" + "/".join(strings[i] for i in (18, 19, 22, 24)),
        "otc_info": "/" + "/".join(strings[i] for i in (18, 20, 25)),
        "send_command": "/" + strings[32] + "{broker_suffix}/" + strings[22] + "/" + strings[33],
        "cloud_properties": "/" + "/".join(strings[i] for i in (18, 20, 36)),
        "history": "/" + "/".join(strings[i] for i in (18, 20, 38)),
        "get_device_data": "/" + "/".join(strings[i] for i in (18, 21, 39)),
        "set_device_data": "/" + "/".join(strings[i] for i in (18, 21, 40)),
        "download_url": "/" + "/".join(strings[i] for i in (18, 34, 48)),
        "oss_download_url": "/" + "/".join(strings[i] for i in (18, 34, 49)),
        "device_file": strings[54],
    }
    profiles = {}
    for brand, domain, secret, version, basic, ua, meta in (
        ("dreame", 0, 55, 65, 4, 79, True),
        ("mova", 50, 56, 66, 70, 69, True),
        ("trouver", 52, 57, 67, 78, 80, False),
    ):
        profiles[brand] = {
            "domain_suffix": strings[domain], "port": int(strings[1]),
            "signing_key": strings[secret], "app_version": strings[version],
            "basic_authorization": strings[basic] if brand == "dreame" else "Basic " + strings[basic],
            "user_agent": strings[ua], "browser_metadata": meta,
            "tenant_id": "000000" if brand == "dreame" else "000002" if brand == "mova" else "000005",
            "regions": ["eu", "cn", "us", "ru", "sg", "kr", "by"] if brand == "dreame" else ["eu", "cn", "us", "sg", "kr"] if brand == "mova" else ["eu", "us", "ru", "sg"],
        }

    counts = {
        "properties": len(properties), "mapped_properties": sum(p["mapping"] is not None for p in properties),
        "actions": len(actions), "models": len(models), "enums": len(enums),
        "entity_descriptions": len(entities), "endpoints": len(endpoints),
        "entities_by_platform": {p: sum(e["platform"] == p for e in entities) for p in platforms},
        "reference_implementations": {k: len(v) for k, v in implementations.items()},
    }
    provenance = {
        "repository": REPO, "commit": commit, "license": "MIT", "counts": counts,
        "scope": "Source-derived vacuum catalog; not a universal Dreame device schema.",
        "sources_sha256": {name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in sources},
    }
    return {
        "provenance": provenance, "api": {"endpoints": endpoints, "profiles": profiles, "password_salt": strings[2]},
        "protocol_strings": strings, "properties": properties, "actions": actions,
        "property_groups": groups, "availability": rules, "enums": enums,
        "models": models, "device_info": device_info, "entities": entities,
        "entity_defaults": defaults, "constants": constants, "implementations": implementations,
        "translations_en": json.loads((base / "translations/en.json").read_text(encoding="utf-8")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / "upstream")
    parser.add_argument("--output", type=Path, default=ROOT / "src/dreamehome/data")
    parser.add_argument("--check", action="store_true", help="Verify generated files without writing")
    args = parser.parse_args()
    data = extract(args.upstream)
    for name, value in data.items():
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        path = args.output / f"{name}.json"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != encoded:
                raise SystemExit(f"Extraction differs: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded, encoding="utf-8", newline="\n")
    print(json.dumps(data["provenance"]["counts"], indent=2))


if __name__ == "__main__":
    main()
