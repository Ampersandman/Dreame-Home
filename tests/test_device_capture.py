"""Offline collector checks: discover laundry fields without vacuum guesses."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from dreamehome import Device

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("capture_device_api", ROOT / "tools/capture_device_api.py")
capture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture_module)


class FakeApi:
    region = "eu"

    def __init__(self):
        self.reads = []
        self.downloads = []

    async def list_devices(self):
        return [Device.from_record({"did": str(index), "model": model}) for index, model in enumerate(
            ("dreame.washer.l9nacn", "dreame.dryer.l9nacn", "dreame.vacuum.r5023a"), 1)]

    async def get_device_info(self, did):
        if did == "1":
            return {"did": did, "property": '{"prop.2.1":14,"unknown_name":"idle","iotId":"private-secret"}',
                    "keyDefine": {"ver": 2, "url": "https://example.test/washer.json"},
                    "access_token": "never-store-me", "masterUid": "private-account"}
        return {"did": did}

    async def get_otc_info(self, did):
        return {"otcInfo": {"params": {"mac": "private-mac", "token": "private-token"}}}

    async def read_properties(self, device, pairs):
        self.reads.append((device.model, list(pairs)))
        return [{"siid": siid, "piid": piid, "value": 15, "code": 0} for siid, piid in pairs]

    async def download(self, url):
        self.downloads.append(url)
        return b'{"model":"dreame.washer.l9nacn","name":"Washer state","keyDefine":{"2.1":{"en":{"0":"Idle"}}}}'


class FakeSubscription:
    instances = []

    def __init__(self, api, device, callback):
        self.device, self.callback = device, callback
        self.connected = False
        self.last_error = None
        self.stopped = False
        self.instances.append(self)

    async def start(self):
        self.connected = True
        self.callback({"method": "properties_changed", "params": [{"siid": 11, "piid": 9, "value": True}]})

    async def stop(self):
        self.stopped = True
        self.connected = False


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_only_observed_laundry_and_bounded_vacuum_fields(self):
        api = FakeApi()
        FakeSubscription.instances = []
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            await capture_module.capture(api, seconds=0, output=path,
                                         subscription_factory=FakeSubscription)
            report = json.loads(path.read_text(encoding="utf-8"))
        reads = {}
        for model, pairs in api.reads:
            reads.setdefault(model, set()).update(pairs)
        self.assertEqual(reads["dreame.washer.l9nacn"], {(2, 1), (11, 9)})
        self.assertEqual(reads["dreame.dryer.l9nacn"], {(11, 9)})
        self.assertEqual(reads["dreame.vacuum.r5023a"], set(capture_module.VACUUM_INITIAL) | {(11, 9)})
        self.assertEqual(api.downloads, ["https://example.test/washer.json"])
        self.assertTrue(all(subscription.stopped for subscription in FakeSubscription.instances))
        serialized = json.dumps(report)
        for secret in ("never-store-me", "private-secret", "private-account", "private-mac", "private-token"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(report["devices"][0]["identity"]["did"], "1")
        self.assertEqual(report["devices"][0]["definitions"][0]["document"]["name"], "Washer state")
        self.assertTrue(report["discovery_complete"])

    def test_definition_references_are_explicit_and_deduplicated(self):
        refs = capture_module.referenced_definitions({
            "keyDefine": {"url": "https://example.test/spec.json"},
            "deviceInfo": {"liveKeyDefine": {"url": "https://example.test/spec.json"},
                           "qaKeyDefine": {"url": "http://example.test/insecure.json"},
                           "mainImage": {"url": "https://example.test/picture.png"}}})
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["url"], "https://example.test/spec.json")


if __name__ == "__main__":
    unittest.main()
