"""Extract factual L9 washer metadata from its exact official model plugin.

Offline only: the downloaded JavaScript is parsed as text, never evaluated.
The input is pinned to the authenticated model-specific plugin collected on
2026-10-04. Notify evidence is kept separate from successful live RPC reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


MODEL = "dreame.washer.l9nacn"
ZIP_SHA256 = "33ea438c47b2c33572b08017c88fb7450bcd8157ba752673fac9f2ebae6fc9f8"
SOURCE_URL = "https://oss.iot.dreame.tech/pd/pg/extensions/2175/ali_dreame/ios/9d22fee332abcb1d0ae80463c1c799b7dreame.washer.l9nacn_83.zip"
DEFAULT_ZIP = Path("private/plugins/dreame.washer.l9nacn-rn-0-7b398d1b21dc.zip")
BUNDLE = f"{MODEL}/index.ios.bundle"

# Names are semantic annotations of the corresponding UI/store code. Values,
# coordinates, English labels and enum tables are read from the pinned bundle.
NAMES = {
    (2, 1): ("run_status", "Run status", "RunStatus", False, None),
    (2, 2): ("fault_code", "Fault code", "Fault", False, None),
    (2, 3): ("program", "Program", "ProgramMode", False, None),
    (2, 4): ("wash_phase", "Wash phase", "WashStatus", False, None),
    (2, 8): ("temperature", "Temperature", "temperature", False, None),
    (2, 11): ("delay_remaining_time", "Delay remaining time", None, False, "min"),
    (2, 12): ("program_time", "Program duration", None, False, "min"),
    (2, 13): ("remaining_time", "Remaining time", None, False, "min"),
    (2, 14): ("extra_time", "Extra time", "addTime", False, None),
    (2, 15): ("water_level", "Water level", "waterLevel", False, None),
    (2, 16): ("rinse_cycles", "Rinse cycles", "times", False, None),
    (2, 18): ("spin_speed", "Spin speed", "rotate", False, None),
    (2, 24): ("detergent_dosing", "Detergent dosing", "gearArr", False, None),
    (2, 25): ("softener_dosing", "Softener dosing", "gearArr", False, None),
    (3, 4): ("child_lock", "Child lock", None, True, None),
    (3, 6): ("fresh_air_circulation", "Fresh air circulation", None, True, None),
    (3, 7): ("dynamic_rinse", "Dynamic rinse", None, True, None),
    (3, 8): ("speed_mode", "Speed mode", None, True, None),
    (3, 9): ("night_mode", "Night mode", None, True, None),
    (3, 13): ("drum_clean_recommended", "Drum clean recommended", None, True, None),
    (3, 14): ("network_authorized", "Network authorized", None, True, None),
    (4, 6): ("low_detergent", "Low detergent", None, True, None),
    (4, 7): ("low_softener", "Low softener", None, True, None),
    (5, 1): ("ota_status", "Firmware update status", None, False, None),
}
WRITE_ONLY = {
    (2, 5): ("stain_type", "Stain type", "StainTypeData", False, None),
    (2, 19): ("delay_time", "Delay time", None, False, "min"),
    (3, 5): ("delay_enabled", "Delay enabled", None, True, None),
}


def literal_at(text: str, start: int) -> str:
    """Get a balanced array/object literal, ignoring delimiters inside strings."""
    pairs = {"[": "]", "{": "}"}
    stack: list[str] = []
    quote = None
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in pairs:
            stack.append(pairs[char])
        elif char in "]}":
            if not stack or char != stack.pop():
                raise ValueError("Mismatched JS literal")
            if not stack:
                return text[start : i + 1]
    raise ValueError("Unterminated JS literal")


def array_var(text: str, name: str) -> tuple[str, int]:
    match = re.search(rf"\bvar {re.escape(name)}\s*=\s*(?:exports\.{name}\s*=\s*)?\[", text)
    if not match:
        raise ValueError(f"Missing expected array {name}")
    start = match.end() - 1
    return literal_at(text, start), start


def parse_simple(text: str):
    """Parse only literal JS syntax after replacing explicitly known tokens."""
    text = re.sub(r"\b([A-Za-z_$][\w$]*)\s*:", r'"\1":', text)
    text = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", lambda m: json.dumps(m[1]), text)
    return json.loads(text)


def modules(text: str) -> list[tuple[int, int, str]]:
    result = []
    for start in (m.start() for m in re.finditer(r"^__d\(function", text, re.M)):
        tail = re.search(r'^},"([^\"]+)",\[', text[start:], re.M)
        if tail:
            result.append((start, start + tail.end(), tail[1]))
    return result


def provenance(text: str, spans, offset: int) -> dict:
    module = next((name for begin, end, name in spans if begin <= offset <= end), None)
    return {"module": module, "line": text.count("\n", 0, offset) + 1}


def translation_literals(raw: str, labels: dict) -> str:
    raw = re.sub(
        r"_string\.default(?:\.([\w-]+)|\[\"([^\"]+)\"\])",
        lambda m: json.dumps(labels[m[1] or m[2]], ensure_ascii=False),
        raw,
    )
    # Times labels are literal count + localized suffix in the app.
    raw = re.sub(r"'([0-9]+)'\s*\+\s*(\"(?:[^\"\\]|\\.)*\")", lambda m: json.dumps(m[1] + json.loads(m[2])), raw)
    # Icons are irrelevant to the device's enum values.
    raw = re.sub(r",\s*icon:\s*[_\w.]+", "", raw)
    return raw


def extract(path: Path) -> dict:
    raw = path.read_bytes()
    zip_hash = hashlib.sha256(raw).hexdigest()
    if zip_hash != ZIP_SHA256:
        raise ValueError("Input ZIP does not match the exact verified washer plugin")
    with zipfile.ZipFile(path) as archive:
        bundle_bytes = archive.read(BUNDLE)
        labels = json.loads(archive.read(f"{MODEL}/assets/projects/{MODEL}/assets/string/en.json"))
        project = json.loads(archive.read(f"{MODEL}/project.json"))
    text = bundle_bytes.decode("utf-8")
    if project != {"versionCode": 83, "projectName": MODEL, "plat": "ios"}:
        raise ValueError("Unexpected model/plugin version/platform in project.json")
    spans = modules(text)
    observed = {tuple(map(int, values)) for values in re.findall(r"prop\.([0-9]+)\.([0-9]+)", text)}
    if observed != set(NAMES):
        raise ValueError(f"Unexpected notify coordinates: {observed.symmetric_difference(NAMES)}")

    tables = {}
    table_provenance = {}
    for name in {row[2] for row in NAMES.values()} | {"StainTypeData"}:
        if name is None:
            continue
        literal, offset = array_var(text, name)
        literal = translation_literals(literal, labels)
        literal = re.sub(r"JSON\.stringify\(_ProgramDefaultConfig\.defaultConfig\[(\d+)\]\)", r"\1", literal)
        tables[name] = parse_simple(literal)
        table_provenance[name] = provenance(text, spans, offset)

    default_config, config_offset = array_var(text, "defaultConfig")
    configurations = parse_simple(default_config)
    storage_line = text.index("var arr = [[3, 8, matchValue(")
    write_pairs = {tuple(map(int, row)) for row in re.findall(r"\[(\d+), (\d+), matchValue", text)}
    write_pairs |= {(2, 3), (2, 19), (3, 5), (3, 4)}
    properties = []
    for pair, annotation in sorted({**NAMES, **WRITE_ONLY}.items()):
        key, name, enum, boolean, unit = annotation
        if pair in observed:
            token = f"'prop.{pair[0]}.{pair[1]}'"
            offset = text.index(token)
            access = ["notify"]
            if pair == (3, 14):
                access.insert(0, "read")
        else:
            offset = storage_line if pair == (2, 5) else text.index(f"_request.setProperties)({pair[0]}, {pair[1]},")
            access = []
        if pair in write_pairs:
            access.append("write")
        values = None
        if enum:
            values = []
            for row in tables[enum]:
                code = row.get("key", row.get("value"))
                label = row.get("value") if "key" in row else row.get("label", row.get("title"))
                item = {"value": code, "label": label}
                if row.get("code") is not None:
                    item["fault_code"] = row["code"]
                values.append(item)
            if enum == "gearArr":
                values.insert(0, {"value": 0, "label": labels["Off"]})
        if boolean:
            values = [{"value": 0, "label": "Off"}, {"value": 1, "label": "On"}]
        if enum == "Fault":
            # SubscribePage handles the literal zero as no fault, separately
            # from the Fault dictionary (whose first entry is code one).
            values.insert(0, {"value": 0, "label": "No fault"})
        unit_provenance = None
        if unit:
            expression = "Math.floor(programTime / 60)" if pair == (2, 12) else "Math.floor(remainingTime / 60)" if pair == (2, 13) else "futureTimestamp = now.getTime() + Number(n) * 60 * 1000"
            unit_provenance = provenance(text, spans, text.index(expression))
        properties.append({
            "key": key, "name": name, "siid": pair[0], "piid": pair[1],
            "access": access, "wire_format": "integer", "wire_format_inferred": True,
            "semantic_type": "boolean" if boolean else "enum" if enum else "integer",
            "unit": unit, "value_list": values,
            "value_list_inferred": boolean,
            "value_range": None, "live_verified": False,
            "provenance": provenance(text, spans, offset),
            "enum_provenance": table_provenance.get(enum),
            "unit_provenance": unit_provenance,
        })
    action_names = {1: "Power", 2: "Start/pause", 3: "Add clothes", 4: "Request current status report"}
    actions = []
    calls = list(re.finditer(r"_request\.action\)\((\d+), (\d+), (\d+)\)", text))
    for aiid in sorted({int(m[2]) for m in calls}):
        action_calls = [m for m in calls if int(m[2]) == aiid]
        actions.append({
            "siid": 2, "aiid": aiid, "name": action_names[aiid],
            "input_piid": aiid, "observed_input_values": sorted({int(m[3]) for m in action_calls}),
            "changes_device_state": aiid != 4,
            "live_executed": False,
            "provenance": [provenance(text, spans, m.start()) for m in action_calls],
        })
    programs = []
    for row in tables["ProgramMode"]:
        programs.append({
            "value": row["key"], "label": row["value"],
            "default_duration_minutes": int(row["min"]),
            "default_configuration": configurations[row["config"]],
        })
    return {
        "model": MODEL, "marketing_name": "L9 Washer", "product_id": "11528", "extension_id": "2175",
        "status": "official-model-plugin", "live_verified": False,
        "source": {"zip_sha256": zip_hash, "bundle": BUNDLE,
                   "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
                   "source_url": SOURCE_URL,
                   "plugin_version": 83, "os_code": 0, "platform": "ios",
                   "lookup_route": "GET /dreame-product/upgrades/appplugin",
                   "app_version": 102060603, "project_model": project["projectName"]},
        "properties": properties, "actions": actions,
        "programs": programs,
        "program_constants": {"stain_types": tables["StainTypeData"],
                              "default_configuration_provenance": provenance(text, spans, config_offset)},
        "rpc_contract": {"property_did": "actual device ID", "read_method": "get_properties",
                         "write_method": "set_properties", "action_method": "action",
                         "action_input_form": [{"piid": "aiid", "value": "input value"}]},
        "cloud_property_keys": [{"key": "prop.s_auto_upgrade", "name": "Automatic firmware updates", "access": ["read", "write"]}],
        "local_app_state": ["favorites", "usage history", "program memory", "notification preferences", "filter cleaning reminder"],
        "limitations": ["Notify coordinates are not formal MIoT access declarations; only 3.14 has a direct app get_properties call.",
                        "Wire integer type is inferred from the app's comparisons, numeric enums and Number conversions.",
                        "Program options and allowed values depend on the selected program and running phase.",
                        "2.8 value 999 appears in app stain-removal UI state; its device meaning is unresolved.",
                        "Action 2.4 is used by the app to request status; no actions were executed during extraction.",
                        "5.1 OTA states 1 through 4 mean update in progress; individual state labels are unresolved."]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, nargs="?", default=DEFAULT_ZIP)
    parser.add_argument("--output", type=Path, default=Path("src/dreamehome/data/l9_washer.json"))
    parser.add_argument("--check", action="store_true", help="Check reproduction without modifying the catalogue")
    args = parser.parse_args()
    data = extract(args.zip)
    encoded = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if args.output.read_text(encoding="utf-8") != encoded:
            raise ValueError("Catalogue differs from the pinned plugin extraction")
        print(f"Catalogue matches the pinned model plugin: {args.output}")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(f"Extracted {len(data['properties'])} properties, {len(data['actions'])} actions, {len(data['programs'])} programs -> {args.output}")


if __name__ == "__main__":
    main()
