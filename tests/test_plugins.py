"""Source-backed plugin discovery requests and download URL filtering."""

from pathlib import Path
import sys
import unittest
import json
from urllib.parse import parse_qs, urlsplit

from test_contract import FakeTransport, api, device_record, login_response, response
from dreamehome import Device

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fetch_device_plugins import plugin_urls


class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_is_unsigned_authenticated_get_with_numeric_version(self):
        transport = FakeTransport(login_response(), response({"code": 0, "data": {"url": "https://example.test/plugin.zip"}}))
        client = api(transport)
        manifest = await client.plugin_manifest(Device.from_record(device_record(did="-123456", model="dreame.washer.l9nacn")))
        call = transport.calls[-1]
        self.assertEqual(call["method"], "GET")
        self.assertIsNone(call["body"])
        parsed = urlsplit(call["url"])
        self.assertEqual(parsed.path, "/dreame-product/upgrades/appplugin")
        self.assertEqual(parse_qs(parsed.query), {"model": ["dreame.washer.l9nacn"], "did": ["-123456"], "os": ["0"], "appVer": ["102060603"]})
        self.assertEqual(call["headers"]["dreame-auth"], "access")
        self.assertEqual(manifest["data"]["url"], "https://example.test/plugin.zip")

    async def test_manifest_renews_rejected_session_once(self):
        transport = FakeTransport(login_response(), response({"code": 401}, status=401),
                                  login_response(access="renewed"), response({"code": 0, "data": {}}))
        await api(transport).plugin_manifest(Device.from_record(device_record()))
        self.assertEqual([call["method"] for call in transport.calls], ["POST", "GET", "POST", "GET"])
        self.assertEqual(transport.calls[-1]["headers"]["dreame-auth"], "renewed")

    async def test_h5_lookup_uses_apk_route_and_preserves_distinct_response(self):
        transport = FakeTransport(login_response(), response({"code": 0, "data": {"androidPluginUrl": "https://example.test/l9.zip"}}))
        manifest = await api(transport).h5_plugin_manifest(Device.from_record(device_record(model="dreame.dryer.l9nacn")),
                                                         os_code=0, app_version=102060603)
        call = transport.calls[-1]
        self.assertEqual(urlsplit(call["url"]).path, "/dreame-product/upgrades/h5plugin")
        self.assertEqual(parse_qs(urlsplit(call["url"]).query)["os"], ["0"])
        self.assertEqual(manifest["data"]["androidPluginUrl"], "https://example.test/l9.zip")

    def test_h5_platform_download_fields_are_retained(self):
        self.assertEqual(plugin_urls({"data": {"androidPluginUrl": "https://example.test/android.zip",
                                                "iosPluginUrl": "https://example.test/ios.zip"}}),
                         ["https://example.test/android.zip", "https://example.test/ios.zip"])

    async def test_invalid_numeric_version_does_not_send_credentials(self):
        transport = FakeTransport()
        client = api(transport)
        with self.assertRaises(ValueError):
            await client.plugin_manifest(Device.from_record(device_record()), app_version="2.6.3")
        self.assertFalse(transport.calls)

    async def test_exact_l9_reads_match_device_id_correlation_in_own_plugin(self):
        transport = FakeTransport(login_response(), response({"code": 0, "data": {"result": []}}))
        device = Device.from_record(device_record(did="-123456", model="dreame.washer.l9nacn"))
        await api(transport).read_properties(device, [(3, 14)])
        params = json.loads(transport.calls[-1]["body"])["data"]["params"]
        self.assertEqual(params, [{"did": "-123456", "siid": 3, "piid": 14}])

    def test_only_explicit_https_plugin_urls_are_downloaded(self):
        value = {"data": [{"url": "https://example.test/plugin.zip"},
                          {"downloadUrl": "https://example.test/plugin.zip"},
                          {"url": "http://example.test/insecure.zip"},
                          {"url": "https://user:password@example.test/embedded.zip"},
                          {"unrelated": "https://example.test/unrelated.zip"}]}
        self.assertEqual(plugin_urls(value), ["https://example.test/plugin.zip"])


if __name__ == "__main__":
    unittest.main()
