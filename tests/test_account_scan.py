"""Safe account identification with fabricated records; no credentials/network."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("account_scan", ROOT / "tools/scan_cloud_account.py")
account_scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(account_scan)

from dreamehome import Device
from dreamehome.exceptions import AuthenticationError, IncompleteDiscoveryError


class ProjectionTests(unittest.TestCase):
    def test_preserves_exact_ids_without_cloud_secrets(self):
        raw = {
            "did": "washer-exact-id", "model": "dreame.washer.r1111", "masterUid": "secret-owner",
            "customName": "Washer L9", "ver": "1.2.3", "mac": "secret-mac",
            "property": '{"iotId":"secret-iot-id"}', "access_token": "secret-access",
            "deviceInfo": {"displayName": "Washer L9", "productId": "p123", "imageUrl": "https://private.test/file?key=secret"},
        }
        result = account_scan.public_device_record(Device.from_record(raw))
        self.assertEqual(result["did"], "washer-exact-id")
        self.assertEqual(result["product_id"], "p123")
        self.assertEqual(result["schema_candidate"]["properties"], 92)
        self.assertNotIn("secret-", str(result))
        self.assertNotIn("imageUrl", str(result))

    def test_bodyless_completeness_requires_metadata(self):
        records = [{"did": "x", "model": "unknown.washer"}]
        devices, complete = account_scan.bodyless_records({"data": {"page": {"records": records}}})
        self.assertEqual(devices[0].did, "x")
        self.assertFalse(complete)
        _, complete = account_scan.bodyless_records({"data": {"page": {"records": records, "total": 1, "pages": 1}}})
        self.assertTrue(complete)


class ScanTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_fallback_retains_all_three_device_categories(self):
        class FakeApi:
            region, account_type = "eu", "dreame"
            async def list_devices(self):
                raise IncompleteDiscoveryError(1, 3)
            async def list_devices_response(self):
                return {"data": {"page": {"total": 3, "pages": 1, "records": [
                    {"did": "w", "model": "dreame.washer.r1111"},
                    {"did": "d", "model": "dreame.dryer.unknown"},
                    {"did": "v", "model": "dreame.vacuum.unknown"},
                ]}}}
            async def get_device_info(self, did):
                return {"did": did}
        result = await account_scan.scan(FakeApi())
        self.assertTrue(result["discovery_complete"])
        self.assertEqual([r["did"] for r in result["devices"]], ["w", "d", "v"])
        self.assertEqual(len(result["warnings"]), 1)

    async def test_auth_failure_does_not_attempt_bodyless_fallback(self):
        class FakeApi:
            region, account_type = "eu", "dreame"
            async def list_devices(self):
                raise AuthenticationError("Rejected")
            async def list_devices_response(self):
                raise AssertionError("Fallback should not run")
        with self.assertRaises(AuthenticationError):
            await account_scan.scan(FakeApi())


if __name__ == "__main__":
    unittest.main()
