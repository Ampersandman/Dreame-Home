"""Extract factual L9 dryer protocol constants from an official RN plugin ZIP.

Pure static extraction: no JavaScript, plugin functions, or source lambdas run.
Only derived protocol facts are emitted, not the complete proprietary bundle.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = "dreame.dryer.l9nacn"
DEFAULT_ZIP = ROOT / "private/plugins/dreame.dryer.l9nacn-rn-0-0dad597f4474.zip"
SOURCE_URL = "https://oss.iot.dreame.tech/pd/pg/extensions/2186/ali_dreame/ios/f61ecebafd0dbf15219f10e2f30f1e6edreame.dryer.l9nacn_130.zip"


def literal_segment(source, name):
    match = re.search(r"\bvar " + re.escape(name) + r"\s*=\s*(?:exports\." + re.escape(name) + r"\s*=\s*)?([\[{])", source)
    if match is None:
        raise ValueError(f"Missing literal declaration: {name}")
    start = match.start(1)
    stack, quote, escaped = [], None, False
    for position in range(start, len(source)):
        character = source[position]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in ("'", '"'):
            quote = character
        elif character in "[{":
            stack.append(character)
        elif character in "]}":
            if not stack or (stack.pop(), character) not in (("[", "]"), ("{", "}")):
                raise ValueError("Unbalanced literal")
            if not stack:
                return source[start:position + 1], start
    raise ValueError("Unterminated literal")


def parse_literal(text, translations):
    # Replace explicit translation references with factual keys/labels only.
    text = re.sub(r"_string\.default\.([A-Za-z_$][\w$]*)", lambda match: repr({
        "translation_key": match[1], "label": translations.get(match[1], match[1]),
    }), text)
    # Transform identifier tokens outside strings, then use Python's literal
    # parser. Remaining calls, arithmetic or attribute references are rejected.
    token = re.compile(r"(?:'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")|\b[A-Za-z_$][\w$]*\b", re.S)
    def replace(match):
        value = match[0]
        if value.startswith(("'", '"')):
            return value
        if value in {"true", "false", "null"}:
            return {"true": "True", "false": "False", "null": "None"}[value]
        if re.match(r"\s*:", text[match.end():]):
            return repr(value)
        return value
    return ast.literal_eval(token.sub(replace, text))


def extract(archive_path):
    archive_bytes = archive_path.read_bytes()
    bundle = f"{MODEL}/index.ios.bundle"
    with zipfile.ZipFile(archive_path) as archive:
        project = json.loads(archive.read(f"{MODEL}/project.json"))
        if project["projectName"] != MODEL:
            raise ValueError("Plugin project model does not match L9 dryer")
        source_bytes = archive.read(bundle)
        source = source_bytes.decode("utf-8")
        translations = json.loads(archive.read(f"{MODEL}/assets/projects/{MODEL}/assets/string/en.json"))
    def provenance(offset):
        suffix = re.search(r'\},"(projects_[^"]+)"', source[offset:])
        return {"module": suffix[1] if suffix else None, "line": source[:offset].count("\n") + 1}
    mappings_text, mappings_offset = literal_segment(source, "FunctionsToParam")
    mappings = parse_literal(mappings_text, translations)
    enum_tables = {}
    for name in ("RunStatus", "WashStatus", "Fault"):
        block, offset = literal_segment(source, name)
        enum_tables[name] = {"values": parse_literal(block, translations), "provenance": provenance(offset)}
    properties = []
    for name, coordinate in mappings.items():
        if not isinstance(coordinate, str) or not (match := re.fullmatch(r"prop\.(\d+)\.(\d+)", coordinate)):
            continue
        pair = int(match[1]), int(match[2])
        table = {"isOnline": "RunStatus", "washStatus": "WashStatus", "faultInfo": "Fault"}.get(name)
        values = []
        if table:
            values = [{"value": row["key"], "label": row["value"]["label"],
                       "translation_key": row["value"]["translation_key"],
                       **({"code": row["code"]} if "code" in row else {})}
                      for row in enum_tables[table]["values"]]
        line_offset = source.index(coordinate, mappings_offset)
        properties.append({
            "key": coordinate, "name": name, "siid": pair[0], "piid": pair[1],
            "access": ["notify"] + (["read"] if pair == (3, 14) else []),
            "read_candidate": True, "live_verified": False,
            "wire_format": "scalar; type not declared by plugin subscription table",
            "unit": None, "value_list": values, "provenance": provenance(line_offset),
            "notes": "isOnline is operating status, not boolean cloud connectivity" if name == "isOnline" else None,
        })
    programs = {}
    for name in ("ProgramMode", "ProgramMode_W"):
        block, offset = literal_segment(source, name)
        programs[name] = {"provenance": provenance(offset), "values": [
            {"value": int(match[1]), "translation_key": match[2],
             "label": translations.get(match[2], match[2]), "default_minutes": int(match[3])}
            for match in re.finditer(r"\bkey:\s*(\d+),\s*value:\s*_string\.default\.(\w+),\s*min:\s*\"(\d+)\"", block)
        ]}
    export_flag = re.search(r"var isExportSales = exports\.isExportSales = (\d+);", source)
    selector = re.search(r"function getProgramMode\(\).*?return isExportSales \? copyArr : ProgramMode;", source, re.S)
    if export_flag is None or selector is None or "var copyArr = ProgramMode_W;" not in selector[0]:
        raise ValueError("Unknown program-table selection logic")
    if len(re.findall(r"(?<![.\w])isExportSales\s*=", source)) != 1:
        raise ValueError("Export program flag is dynamically assigned")
    selected_program_table = "ProgramMode_W" if int(export_flag[1]) else "ProgramMode"
    program_selection = {
        "selected_table": selected_program_table, "is_export_sales_literal": int(export_flag[1]),
        "flag_provenance": provenance(export_flag.start()), "selector_provenance": provenance(selector.start()),
        "selection_condition": "Literal isExportSales; no account/country/model condition in this plugin.",
        "duration_adjustment": {"table": "ProgramMode_W", "program_index": 3,
                                "firmware_prefix_number_lte": 16, "minutes_if_lte": 120, "minutes_otherwise": 110},
    }
    configs = {}
    for name in ("defaultConfig", "defaultConfig_W"):
        block, offset = literal_segment(source, name)
        configs[name] = {"provenance": provenance(offset), "values": parse_literal(block, translations)}
    # storageToProgram supplies literal coordinates for the bulk property
    # setter. It includes controls absent from FunctionsToParam notifications.
    control_matches = list(re.finditer(
        r"\[(\d+),\s*(\d+),\s*matchValue\(backupStorageData\.([A-Za-z_$][\w$]*)\)\]", source))
    if len(control_matches) != 10:
        raise ValueError("Unexpected dryer bulk-setting coordinate table")
    control_labels = {}
    for match in re.finditer(r"title:\s*_string\.default\.(\w+),\s*siid:\s*(\d+),\s*piid:\s*(\d+)", source):
        control_labels[(int(match[2]), int(match[3]))] = (match[1], provenance(match.start()))
    parameter_labels = {(2, 6): "DrynessLevel", (2, 10): "ExtraTime", (2, 5): "AirFlow", (2, 13): "steam"}
    for pair, translation in parameter_labels.items():
        match = re.search(r"title:\s*_string\.default\." + translation + r",\s*piid:\s*" + str(pair[1]), source)
        if match is None:
            raise ValueError(f"Missing literal UI parameter binding for {pair}")
        control_labels[pair] = (translation, provenance(match.start()))
    setting_enums = {}
    for table in ("intensity", "addTime", "airflow", "steam"):
        block, offset = literal_segment(source, table)
        setting_enums[table] = {
            "values": [{"value": item["value"],
                        "label": item["label"]["label"] if isinstance(item["label"], dict) else item["label"],
                        **({"translation_key": item["label"]["translation_key"]}
                           if isinstance(item["label"], dict) else {})}
                       for item in parse_literal(block, translations)],
            "provenance": provenance(offset),
        }
    by_pair = {(item["siid"], item["piid"]): item for item in properties}
    writes = []
    def writable(pair, name, evidence, label=None, translation_key=None):
        row = by_pair.get(pair)
        if row is None:
            row = {"key": f"prop.{pair[0]}.{pair[1]}", "name": name, "siid": pair[0], "piid": pair[1],
                   "access": [], "read_candidate": False, "live_verified": False,
                   "wire_format": "numeric setter input; formal property type unspecified",
                   "unit": None, "value_list": [], "provenance": evidence}
            by_pair[pair] = row
            properties.append(row)
        if "write" not in row["access"]:
            row["access"].append("write")
        row.setdefault("control_sources", []).append(evidence)
        row["control_field"] = name
        if label is not None:
            row["label"] = label
            row["translation_key"] = translation_key
        writes.append({"siid": pair[0], "piid": pair[1], "field": name,
                       "provenance": evidence})
        return row
    for match in control_matches:
        pair = int(match[1]), int(match[2])
        name = match[3]
        label_key, ui_evidence = control_labels.get(pair, (None, None))
        row = writable(pair, name, provenance(match.start()),
                       translations.get(label_key, label_key) if label_key else None, label_key)
        if ui_evidence:
            row["control_sources"].append(ui_evidence)
        row["notes"] = "Program-specific defaults may disable this control; see program_default_configs."
        table = {"drynessLevel": "intensity", "addTime": "addTime", "airflow": "airflow", "steam": "steam"}.get(name)
        if table:
            row["value_list"] = setting_enums[table]["values"]
            row["enum_provenance"] = setting_enums[table]["provenance"]
        else:
            row["value_list"] = [{"value": 0, "label": translations.get("Off", "Off")},
                                 {"value": 1, "label": translations.get("On", "On")}]
            row["wire_format"] = "integer flag; UI setters use 0/1"
    # Program selection uses Program(key)->[2,3,key] before setProperties.
    program_match = re.search(r"function Program\(key\)\s*\{\s*return \[2, 3, key\]", source)
    if program_match is None:
        raise ValueError("Missing program property binding")
    row = writable((2, 3), "currentProgram", provenance(program_match.start()),
                   translations.get("Program", "Program"), "Program")
    row["value_list"] = [{"value": item["value"], "label": item["label"],
                          "translation_key": item["translation_key"]}
                         for item in programs[selected_program_table]["values"]]
    row["enum_source"] = program_selection
    # Delay enable is a property setter; the similarly shaped reportAll is
    # exclusively an action, so it never passes through writable().
    reservation_match = re.search(r'"reservation":\s*\[3,\s*5,\s*1\]', source)
    if reservation_match is None:
        raise ValueError("Missing reservation property binding")
    row = writable((3, 5), "reservation", provenance(reservation_match.start()),
                   translations.get("StartDelayTime", "Delay start"), "StartDelayTime")
    row["wire_format"] = "integer flag; reservation/reservationOff setters send 1/0"
    row["value_list"] = [{"value": 0, "label": translations.get("Off", "Off")},
                         {"value": 1, "label": translations.get("On", "On")}]
    row["write_preconditions"] = ["Export plugin checks authorization property3.14 equals1 before enabling delay start."]
    schedule_match = re.search(r"_request\.setProperties\)\(\[2,\s*12,", source)
    if schedule_match is None:
        raise ValueError("Missing delay duration property setter")
    row = writable((2, 12), "yuyueTime", provenance(schedule_match.start()),
                   translations.get("StartDelayTime", "Delay duration"), "StartDelayTime")
    row["write_input_notes"] = "UI computes delayed-start minutes and clamps to a minimum of30; this is an app constraint, not a proven firmware range."
    row["unit"] = "min"
    by_pair[(3, 11)]["notes"] = ("Plugin notification alias night conflicts with explicit NightMode control3.13. "
                                 "A null observation is unknown and must not be interpreted as a disabled night mode. "
                                 "Separate live verification is documented in docs/l9-investigation.md.")
    actions = []
    for name, parameters in mappings.items():
        if not isinstance(parameters, list):
            continue
        methods = sorted(set(re.findall(r"_request\.(action|setProperties)\)\(_request\.FunctionsToParam\['" + re.escape(name) + r"'\]\)", source)))
        actions.append({"name": name, "literal_parameters": parameters, "observed_helpers": methods,
                        "provenance": provenance(source.index('"' + name + '"', mappings_offset)),
                        **({"siid": parameters[0], "aiid": parameters[1],
                            "inputs": [{"piid": parameters[1], "value": parameters[2]}]}
                           if "action" in methods else {})})
    constants, offset = literal_segment(source, "Constant")
    cloud_read = re.search(r"batchGetDeviceDatas\(\[\{\s*'did': _miot\.Device\.deviceID,\s*'props': \[\"prop\.s_auto_upgrade\"\]", source)
    cloud_write = re.search(r'"prop\.s_auto_upgrade": Number\(val\)\.toString\(\)', source)
    if cloud_read is None or cloud_write is None:
        raise ValueError("Missing exact firmware auto-update cloud binding")
    return {
        "model": MODEL, "format_version": 1,
        "source": {"zip_sha256": hashlib.sha256(archive_bytes).hexdigest(), "bundle": bundle,
                   "bundle_sha256": hashlib.sha256(source_bytes).hexdigest(), "plugin_version": project["versionCode"],
                   "source_url": SOURCE_URL, "extraction": "static literals only; no plugin code execution"},
        "properties": properties,
        "read_candidates": [[row["siid"], row["piid"]] for row in properties if row["read_candidate"]],
        "direct_read_pairs": [[3, 14]],
        "read_item_did": "actual device id (Device.deviceID)",
        "action_definitions": actions,
        "action_wire_format": {"did": "actual device id", "siid": "parameters[0]", "aiid": "parameters[1]",
                               "in": [{"piid": "parameters[1]", "value": "parameters[2]"}]},
        "property_write_definitions": writes,
        "property_write_wire_format": {"did": "actual device id", "siid": "parameters[0]", "piid": "parameters[1]",
                                       "value": "parameters[2]"},
        "property_bulk_write_wire_format": "Array of property-write objects; omit undefined entries from stored program configs.",
        "control_enum_tables": setting_enums,
        "programs": programs, "program_default_configs": configs,
        "program_table_selection": program_selection,
        "program_selection_property": {"siid": 2, "piid": 3},
        "program_constants": {"raw_static_expressions": constants, "provenance": provenance(offset),
                              "storage": "device-id-suffixed local AsyncStorage keys; not cloud property ids"},
        "cloud_property_keys": [{
            "key": "prop.s_auto_upgrade", "name": translations.get("AutoUpdate", "Automatic firmware updates"),
            "access": ["read", "write"], "live_verified": False,
            "wire_format": "string flag; app writes Number(val).toString() and reads Boolean(parseInt(value))",
            "value_list": [{"value": "0", "label": "Off"}, {"value": "1", "label": "On"}],
            "read_helper": "Service.smarthome.batchGetDeviceDatas",
            "write_helper": "Service.smarthome.batchSetDeviceDatas",
            "read_helper_input": [{"did": "actual device id", "props": ["prop.s_auto_upgrade"]}],
            "read_helper_result": "Native plugin response is grouped by actual device id, then cloud property key; this does not specify the HTTP response envelope.",
            "provenance": [provenance(cloud_read.start()), provenance(cloud_write.start())],
            "notes": "The app initializes an absent value to string1; read-only consumers must preserve absence without writing.",
        }],
        "enum_tables": enum_tables,
        "cautions": [
            "Subscriptions confirm coordinate use, not formal property access flags or current firmware support.",
            "reportAll literal [2,4,1] is an action that requests device reports; it is excluded from read-only discovery.",
            "Night mode uses prop.3.11 in FunctionsToParam but siid3/piid13 in the ModeCard2 control UI; preserve this unresolved conflict.",
            "getProgramMode selects ProgramMode_W; firmware version<=0.1.6 changes program index3 default minutes to120, later versions use110.",
            "No units or writable ranges are inferred from unrelated vacuum or washer schemas.",
            "Control-only coordinates have read_candidate false; unknown MQTT coordinates remain observable without guessed labels.",
            "The hidden NightMode entry in ModeSwitch leaves its setter piid at0; this malformed UI path is not a valid property definition or read candidate.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--output", type=Path, default=ROOT / "src/dreamehome/data/l9_dryer.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = extract(args.archive)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if args.output.read_text(encoding="utf-8") != text:
            raise SystemExit("Dryer catalog differs from static extraction")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({"model": MODEL, "properties": len(result["properties"]),
                      "programs": {key: len(value["values"]) for key, value in result["programs"].items()},
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
