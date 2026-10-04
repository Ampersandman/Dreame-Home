"""Verify the packaged backend works independently of the source install."""

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import zipfile

from dreamehome.privacy import redactor

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_vendored_resources_resolve_under_another_package_name(self):
        directory = ROOT / "custom_components/dreame_home/api"
        spec = importlib.util.spec_from_file_location("dreamehome_vendor_test", directory / "__init__.py",
                                                   submodule_search_locations=[str(directory)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            client = module.DreameHomeClient(region="eu")
            self.assertEqual(client.base_url, "https://eu.iot.dreame.tech:13267")
            catalog = sys.modules[spec.name + ".catalog"]
            self.assertTrue(catalog.known_vacuum_model("dreame.vacuum.r5023a"))
            self.assertFalse(catalog.known_vacuum_model("dreame.washer.l9nacn"))
            laundry = importlib.import_module(spec.name + ".laundry")
            self.assertEqual(len(laundry.laundry_schema("dreame.washer.l9nacn").properties), 27)
            self.assertEqual(len(laundry.laundry_schema("dreame.dryer.l9nacn").properties), 22)
            self.assertEqual(len(laundry.laundry_read_pairs("dreame.washer.l9nacn")), 24)
            self.assertEqual(len(laundry.laundry_read_pairs("dreame.dryer.l9nacn")), 17)
            controls = importlib.import_module(spec.name + ".laundry_controls")
            self.assertEqual(len(controls.control_definitions("dreame.washer.l9nacn")), 16)
            self.assertEqual(len(controls.control_definitions("dreame.dryer.l9nacn")), 12)
            vacuum = importlib.import_module(spec.name + ".vacuum_controls")
            self.assertTrue(vacuum.vacuum_control_supported("dreame.vacuum.r5023a"))
        finally:
            for name in list(sys.modules):
                if name == spec.name or name.startswith(spec.name + "."):
                    del sys.modules[name]

    def test_release_contains_component_and_excludes_research_assets(self):
        with zipfile.ZipFile(ROOT / "dist/dreame_home.zip") as archive:
            names = archive.namelist()
            self.assertIn("manifest.json", names)
            self.assertIn("api/mqtt_tls.py", names)
            self.assertIn("api/laundry.py", names)
            self.assertIn("api/data/l9_washer.json", names)
            self.assertIn("api/data/l9_dryer.json", names)
            self.assertIn("api/LICENSE", names)
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["domain"], "dreame_home")
            for name in names:
                self.assertFalse(any(part in {"private", "captures", ".venv", "__pycache__"} for part in Path(name).parts), name)
                self.assertFalse(name.lower().endswith((".apk", ".xapk", ".pyc", ".hbc")), name)

    def test_release_bytes_match_current_component_and_vendor_manifest(self):
        with zipfile.ZipFile(ROOT / "dist/dreame_home.zip") as archive:
            vendor = json.loads(archive.read("api/vendor_manifest.json"))
            for name, digest in vendor["files"].items():
                self.assertEqual(hashlib.sha256(archive.read("api/" + name)).hexdigest(), digest, name)
            for name in archive.namelist():
                self.assertEqual(archive.read(name), (ROOT / "custom_components/dreame_home" / name).read_bytes(), name)

    def test_packed_sensitive_settings_are_redacted_contextually(self):
        payload = {"settings": [{"k": "streamKey", "v": "secret-stream"},
                                {"key": "access_token", "value": "secret-access"},
                                {"k": "AutoDry", "v": 1}]}
        output = redactor()(payload)
        serialized = json.dumps(output)
        self.assertNotIn("secret-stream", serialized)
        self.assertNotIn("secret-access", serialized)
        self.assertEqual(output["settings"][2], {"k": "AutoDry", "v": 1})


if __name__ == "__main__":
    unittest.main()
