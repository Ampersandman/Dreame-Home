"""Offline protocol contracts. No Dreame credentials or physical commands."""

from __future__ import annotations

import asyncio
import ast
import base64
import hashlib
import json
from pathlib import Path
import ssl
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from dreamehome import Device, DreameHomeClient, decode_push
from dreamehome.catalog import load_catalog, vacuum_property_pairs
from dreamehome.cli import pair, parser
from dreamehome.discovery import capture_inventory
from dreamehome.exceptions import ApiError, AuthenticationError, IncompleteDiscoveryError, RateLimitError, SchemaRequiredError, TransportError
from dreamehome.miot import schema_for_model
from dreamehome.mqtt import DeviceSubscription, connect_packet, device_topics
from dreamehome.privacy import redactor
from dreamehome.signing import region_header, sign, splice
from dreamehome.transport import HttpsTransport, Response, _NoRedirects, validate_https_url

NOW = 1_700_000_000.123


def response(data, status=200, headers=None):
    return Response(status, json.dumps(data).encode(), headers or {})


def login_response(access="access", refresh="refresh", expires=7200):
    return response({"access_token": access, "refresh_token": refresh, "uid": "account", "expires_in": expires, "tenant_id": "000000", "region": "eu", "lang": "en", "country": "DE"})


def device_record(did="washer", model="dreame.washer.r1111", **extra):
    return {"did": did, "model": model, "masterUid": "owner", "customName": "Laundry", "bindDomain": "10000.mt.eu.iot.dreame.tech:19973", **extra}


def page(records, current=1, pages=1, total=None):
    return response({"code": 0, "data": {"page": {"records": records, "current": current, "pages": pages, "total": len(records) if total is None else total}}})


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def request(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body, "timeout": timeout})
        if not self.responses:
            raise AssertionError("Unexpected request")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def api(fake, **options):
    return DreameHomeClient("user+test@example.test", "pass word", transport=fake, clock=lambda: NOW, visitor_id="v" * 32, **options)


class SigningContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Extract only pure signing/header methods from the pinned source, to
        # validate nonstandard canonicalization against upstream itself.
        upstream = ROOT / "upstream/custom_components/dreame_vacuum/dreame/protocol.py"
        names = {"_spliced", "_signed", "_base_headers", "_s"}
        if upstream.is_file():
            tree = ast.parse(upstream.read_text(encoding="utf-8"))
            cloud = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DreameVacuumDreameHomeCloudProtocol")
            functions = [n for n in cloud.body if isinstance(n, ast.FunctionDef) and n.name in names]
        else:
            # Clean publication excludes research checkouts. The factual catalog
            # preserves these exact source methods and their pinned provenance.
            methods = load_catalog("implementations")["DreameVacuumDreameHomeCloudProtocol"]
            functions = []
            for method in methods:
                if method["name"] in names:
                    parsed = ast.parse(method["implementation"])
                    for node in parsed.body:
                        if isinstance(node, ast.FunctionDef):
                            node.decorator_list = [ast.parse(decorator, mode="eval").body
                                                   for decorator in method.get("decorators", [])]
                    functions.extend(n for n in parsed.body if isinstance(n, ast.FunctionDef))
        if {node.name for node in functions} != names:
            raise ValueError("Pinned signing reference methods are incomplete")
        stub = ast.ClassDef(name="UpstreamSigning", bases=[], keywords=[], body=functions, decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[stub], type_ignores=[]))
        scope = {"Dict": dict, "Any": object, "hashlib": hashlib, "json": json, "base64": base64, "AES": AES, "pad": pad, "time": SimpleNamespace(time=lambda: NOW)}
        exec(compile(module, "<upstream-pure-signing-methods>", "exec"), scope)
        cls.original = scope["UpstreamSigning"]

    def test_nonstandard_nested_signatures_match_source(self):
        original = self.original()
        original._cid = b"EETjszu*XI5znHsI"
        original._strings = load_catalog("protocol_strings")
        cases = [
            {"did": "123", "keys": "2.1"},
            {"did": "x", "data": {"method": "get_properties", "params": [{"siid": 2, "piid": 1}], "did": "x", "id": 101}, "id": 101},
            {"nested": {"empty": {}, "arr": [1, 2], "bool": True, "missing": None, "unicode": "wäsche"}, "list": [{"b": 2, "a": 1}], "flag": False},
        ]
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(splice(value), original._spliced(value, True))
                self.assertEqual(sign(value, original._cid.decode(), int(NOW * 1000)), original._signed(value))
                self.assertNotIn("timestamp", value)

    def test_empty_dictionary_and_nested_array_quirk(self):
        self.assertEqual(splice({"data": {"empty": {}, "arr": [1], "v": "ß"}}), 'data=[empty=]&v="ß"]')

    def test_region_header_and_headers_match_source_except_encoding(self):
        for brand in ("dreame", "mova", "trouver"):
            for region in ("eu", "kr") if brand != "trouver" else ("eu",):
                with self.subTest(brand=brand, region=region):
                    client = DreameHomeClient("user", "password", account_type=brand, region=region, visitor_id="v" * 32)
                    original = self.original()
                    original._strings = load_catalog("protocol_strings")
                    p = client.profile
                    original._country, original._account_type = region, brand
                    original._ua, original._vid = p["user_agent"], p["app_version"]
                    original._mt, original._username, original._vs = p["browser_metadata"], "user", "v" * 32
                    original._region = original._lang = original._ccode = None
                    original._cid = p["signing_key"].encode()
                    original._ti, original._au = p["tenant_id"], p["basic_authorization"].split()[1]
                    expected = original._base_headers("application/json")
                    actual = client._headers("application/json")
                    actual["accept-encoding"] = "gzip"
                    self.assertEqual(actual, expected)
        decoded = AES.new(b"EETjszu*XI5znHsI", AES.MODE_ECB).decrypt(base64.b64decode(region_header("eu", "en", "DE", "EETjszu*XI5znHsI")))
        self.assertTrue(decoded.startswith(b"eu|en|DE"))


class ClientContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_password_form_encoding_and_headers(self):
        fake = FakeTransport(login_response())
        client = api(fake)
        session = await client.login()
        call = fake.calls[0]
        self.assertEqual(call["url"], "https://eu.iot.dreame.tech:13267/dreame-auth/oauth/token")
        digest = hashlib.md5(b"pass wordRAylYC%fmSKp7%Tq").hexdigest()
        self.assertEqual(call["body"].decode(), f"grant_type=password&scope=all&platform=ANDROID&type=account&username=user%2Btest%40example.test&password={digest}")
        self.assertNotIn("pass word", repr(call))
        self.assertNotIn("access", repr(session))
        self.assertNotIn("refresh", repr(session))

    async def test_refresh_and_password_fallback(self):
        fake = FakeTransport(response({"error_description": "invalid refresh token"}, 400), login_response())
        client = api(fake, refresh_token="expired+token")
        await client.login()
        self.assertIn(b"refresh_token=expired%2Btoken", fake.calls[0]["body"])
        self.assertIn(b"grant_type=password", fake.calls[1]["body"])

    async def test_invalid_refresh_without_password_is_auth_error(self):
        fake = FakeTransport(response({"error_description": "invalid refresh token"}, 400))
        client = DreameHomeClient(refresh_token="expired", transport=fake)
        with self.assertRaises(AuthenticationError):
            await client.login()
        self.assertIsNone(client.session)

    async def test_paginated_discovery_keeps_washer_dryer_shared_unknown(self):
        records = [device_record("w"), device_record("d", "dreame.dryer.unknown"), device_record("s", "other.device.unknown", master=False)]
        fake = FakeTransport(login_response(), page(records[:2], 1, 2, 3), page(records[2:], 2, 2, 3))
        devices = await api(fake).list_devices(size=2)
        self.assertEqual([d.did for d in devices], ["w", "d", "s"])
        self.assertTrue(all(json.loads(call["body"])["sharedStatus"] == 1 for call in fake.calls[1:]))
        self.assertEqual(json.loads(fake.calls[2]["body"])["current"], 2)

    async def test_bodyless_upstream_discovery(self):
        fake = FakeTransport(login_response(), page([]))
        await api(fake).list_devices_response()
        self.assertIsNone(fake.calls[1]["body"])

    async def test_server_ignoring_pagination_is_explicit(self):
        first = page([device_record()], 1, 2, 2)
        fake = FakeTransport(login_response(), first, first)
        with self.assertRaises(IncompleteDiscoveryError):
            await api(fake).list_devices()
        self.assertEqual(len(fake.calls), 3)

    async def test_missing_second_page_records_is_incomplete(self):
        fake = FakeTransport(login_response(), page([device_record()], 1, 2, 2), page([], 2, 2, 2))
        with self.assertRaises(IncompleteDiscoveryError):
            await api(fake).list_devices()

    async def test_concurrent_read_calls_share_login(self):
        fake = FakeTransport(login_response(), page([]), page([]))
        api_client = api(fake)
        await asyncio.gather(api_client.list_devices_response(), api_client.list_devices_response())
        self.assertEqual(sum(call["url"].endswith("/oauth/token") for call in fake.calls), 1)

    async def test_rpc_routing_batching_and_nonzero_property_errors(self):
        values = [{"siid": 2, "piid": 1, "code": 0, "value": 1}, {"siid": 2, "piid": 2, "code": -1}]
        fake = FakeTransport(login_response(), response({"code": 0, "data": {"result": values}}), response({"code": 0, "data": {"result": []}}))
        client = api(fake)
        device = Device.from_record(device_record())
        result = await client.read_properties(device, [(2, n) for n in range(1, 17)])
        self.assertEqual(result, values)
        first = json.loads(fake.calls[1]["body"])
        self.assertEqual(len(first["data"]["params"]), 15)
        self.assertEqual(first["data"]["params"][0], {"did": "2.1", "siid": 2, "piid": 1})
        self.assertTrue(fake.calls[1]["url"].endswith("/dreame-iot-com-10000/device/sendCommand"))
        self.assertEqual(first["did"], device.did)
        self.assertEqual(first["id"], first["data"]["id"])
        self.assertEqual(fake.calls[1]["headers"]["dreame-auth"], "access")
        self.assertIn("dreame-rlc", fake.calls[1]["headers"])

    async def test_writes_and_actions_explicit_did_and_input(self):
        fake = FakeTransport(login_response(), response({"data": {"result": []}}), response({"data": {"result": {"code": 0}}}))
        client, device = api(fake), Device.from_record(device_record())
        await client.write_properties(device, [(3, 1, False)])
        await client.action(device, 2, 1, [{"piid": 3, "value": 5}])
        self.assertEqual(json.loads(fake.calls[1]["body"])["data"]["params"][0]["did"], "washer")
        self.assertEqual(json.loads(fake.calls[2]["body"])["data"]["params"]["in"], [{"piid": 3, "value": 5}])

    async def test_401_refresh_rebuilds_headers(self):
        fake = FakeTransport(login_response(), response({"code": 401}, 401), login_response("new-access", "new-refresh"), page([]))
        client = api(fake)
        await client.list_devices_response()
        self.assertEqual(fake.calls[-1]["headers"]["dreame-auth"], "new-access")
        self.assertIn(b"grant_type=refresh_token", fake.calls[2]["body"])

    async def test_unauthorized_mutations_are_never_replayed_after_refresh(self):
        device = Device.from_record(device_record())
        for operation in ("action", "properties", "userdata"):
            with self.subTest(operation=operation):
                fake = FakeTransport(login_response(), response({"code": 401}, 401))
                client = api(fake)
                with self.assertRaises(AuthenticationError):
                    if operation == "action":
                        await client.action(device, 2, 1)
                    elif operation == "properties":
                        await client.write_properties(device, [(3, 1, 1)])
                    else:
                        await client.set_device_data(device.did, {"prop.s_auto_upgrade": "1"})
                self.assertEqual(len(fake.calls), 2)
                self.assertIsNone(client.session)

    async def test_session_invalidation_code_is_not_password_retry(self):
        fake = FakeTransport(login_response(), response({"code": 100100}, 401))
        client = api(fake)
        with self.assertRaises(AuthenticationError):
            await client.list_devices_response()
        self.assertEqual(len(fake.calls), 2)
        self.assertIsNone(client.session)

    async def test_rate_limit_does_not_replay_action(self):
        fake = FakeTransport(login_response(), response({}, 429, {"retry-after": "60"}))
        with self.assertRaises(RateLimitError) as caught:
            await api(fake).action(Device.from_record(device_record()), 2, 1)
        self.assertEqual(caught.exception.retry_after, "60")
        self.assertEqual(len(fake.calls), 2)

    async def test_no_replay_for_ambiguous_result_or_transport_failure(self):
        for result in (response({"code": 0, "success": True}), TransportError("timeout")):
            fake = FakeTransport(login_response(), result)
            with self.assertRaises(TransportError):
                await api(fake).action(Device.from_record(device_record()), 2, 1)
            self.assertEqual(len(fake.calls), 2)

    async def test_history_cloud_userdata_and_download_routes(self):
        fake = FakeTransport(login_response(), response({"data": {"list": []}}), response({"data": {"2.1": 7}}), response({"data": {"prop.test": "value"}}), response({"result": True}), response({"data": {"url": "https://storage.test/example"}}), Response(200, b"file", {}), Response(200, b"download", {}))
        client, device = api(fake), Device.from_record(device_record())
        await client.history(device, "2.7", kind="event", time_start=123)
        payload = json.loads(fake.calls[-1]["body"])
        self.assertEqual(payload["eiid"], "7")
        self.assertEqual(payload["uid"], "owner")
        self.assertEqual(payload["type"], 3)
        self.assertEqual(payload["from"], 123)
        self.assertEqual(await client.cloud_properties(device.did, "2.1"), {"2.1": 7})
        self.assertEqual(await client.get_device_data(device.did, ["prop.test"]), {"prop.test": "value"})
        self.assertTrue(await client.set_device_data(device.did, {"prop.test": "value"}))
        await client.download_url(device, "/file", interim=False)
        self.assertEqual(json.loads(fake.calls[-1]["body"])["filename"], "file")
        self.assertEqual(await client.device_file(device, "a.jpg", "obstacle"), b"file")
        self.assertEqual(await client.download("https://storage.test/file?signature=private"), b"download")
        self.assertNotIn("authorization", fake.calls[-1]["headers"])
        self.assertNotIn("dreame-auth", fake.calls[-1]["headers"])

    async def test_capture_no_schema_reads_or_write_commands_by_default(self):
        record = device_record("d", "dreame.dryer.unknown")
        fake = FakeTransport(login_response(), page([record]), response({"data": record}), response({"data": {}}))
        report = await capture_inventory(api(fake))
        self.assertTrue(report["discovery_complete"])
        self.assertEqual(report["devices"][0]["record"]["model"], "dreame.dryer.unknown")
        self.assertEqual(len(fake.calls), 4)
        self.assertFalse(any("sendCommand" in call["url"] for call in fake.calls))

    async def test_expired_session_is_refreshed_before_api_request(self):
        fake = FakeTransport(login_response(expires=100), login_response("renewed"), page([]))
        client = api(fake)
        await client.login()
        await client.list_devices_response()
        self.assertEqual(fake.calls[-1]["headers"]["dreame-auth"], "renewed")

    async def test_nonzero_envelope_code_and_invalid_json_are_errors(self):
        for item, error_type in ((response({"code": 9}), ApiError), (Response(200, b"not JSON", {}), TransportError)):
            fake = FakeTransport(login_response(), item)
            with self.assertRaises(error_type):
                await api(fake).list_devices_response()

    async def test_real_paho_connect_packet_and_subscription_lifecycle_offline(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.skipTest("Optional paho-mqtt dependency not installed")
        fake = FakeTransport(login_response())
        client = api(fake)
        delivered = []
        subscription = DeviceSubscription(client, Device.from_record(device_record()), delivered.append)
        with patch.object(mqtt.Client, "connect", return_value=0) as connect, patch.object(mqtt.Client, "loop_start"), patch.object(mqtt.Client, "disconnect"), patch.object(mqtt.Client, "loop_stop"), patch.object(mqtt.Client, "subscribe") as subscribe:
            await subscription.start()
            mqtt_client = subscription._client
            try:
                connect.assert_called_once_with("10000.mt.eu.iot.dreame.tech", 19973, 60)
                self.assertTrue(mqtt_client._ssl_context.check_hostname)
                self.assertEqual(mqtt_client._username, b"account")
                self.assertEqual(mqtt_client._password, b"access")
                mqtt_client._send_connect(60)
                packet = mqtt_client._out_packet[-1]["packet"]
                offset = 1
                while packet[offset] & 0x80:
                    offset += 1
                self.assertTrue(packet[offset + 8] & 0x08)
                mqtt_client.on_connect(mqtt_client, None, None, 0, None)
                subscribe.assert_called_once_with("/status/washer/owner/dreame.washer.r1111/eu/")
                mqtt_client.on_message(mqtt_client, None, SimpleNamespace(payload=b'{"data":{"method":"unknown","params":[1]}}'))
                await asyncio.sleep(0)
                self.assertTrue(subscription.connected)
                self.assertEqual(delivered, [{"method": "unknown", "params": [1]}])
            finally:
                await subscription.stop()
            self.assertIsNone(subscription._client)
            self.assertIsNone(subscription._refresh_task)


class CatalogAndSecurityTests(unittest.TestCase):
    def test_no_washer_vacuum_fallback_and_debug_schema_gate(self):
        with self.assertRaises(SchemaRequiredError):
            vacuum_property_pairs("dreame.washer.r1111")
        with self.assertRaises(SchemaRequiredError):
            schema_for_model("dreame.washer.r1111")
        schema = schema_for_model("dreame.washer.r1111", allow_debug=True)
        self.assertEqual(len(schema["properties"]), 92)
        self.assertFalse(schema["live_verified"])
        self.assertIsNone(schema["marketing_name"])
        with self.assertRaises(SchemaRequiredError):
            schema_for_model("dreame.dryer.unknown", allow_debug=True)

    def test_catalog_cardinality_and_mapping_uniqueness(self):
        properties = load_catalog("properties")
        self.assertEqual(len(properties), 370)
        self.assertEqual(len({p["name"] for p in properties}), 370)
        self.assertEqual(len(load_catalog("actions")), 45)
        self.assertEqual(len(load_catalog("models")), 762)
        self.assertTrue(all(p["source"]["url"].startswith("https://github.com/Tasshack/dreame-vacuum/blob/9857362") for p in properties))

    def test_verified_tls_and_redirect_policy(self):
        transport = HttpsTransport()
        self.assertEqual(transport._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(transport._context.check_hostname)
        self.assertIsNone(_NoRedirects().redirect_request(None, None, 302, "", {}, "https://other.test"))
        for url in ("http://example.test", "https://name:password@example.test", "file:///tmp/data"):
            with self.assertRaises(ValueError):
                validate_https_url(url)

    def test_common_secret_redaction_nested_json_and_model_retention(self):
        record = {"model": "dreame.washer.r1111", "did": "account-device", "siid": 2, "piid": 1, "refresh_token": "refresh-secret", "property": '{"iotId":"stream-secret","lwt":1}', "url": "https://storage.test/private?token=secret", "value": 17}
        redact = redactor()
        value = redact(record)
        encoded = json.dumps(value)
        for secret in ("account-device", "refresh-secret", "stream-secret", "token=secret"):
            self.assertNotIn(secret, encoded)
        self.assertEqual(value["model"], record["model"])
        self.assertEqual(value["siid"], 2)
        self.assertEqual(value["value"], 17)
        self.assertEqual(redact(record), value)

    def test_mqtt_topics_owner_uid_korean_alias_and_unknown_properties(self):
        device = Device.from_record(device_record())
        self.assertEqual(device_topics(device, "eu", "account"), ["/status/washer/owner/dreame.washer.r1111/eu/"])
        self.assertEqual(len(device_topics(device, "kr", "account")), 2)
        value = {"data": {"method": "properties_changed", "params": [{"siid": 99, "piid": 42, "value": "unrecognized"}]}}
        self.assertEqual(decode_push(json.dumps(value)), value["data"])
        self.assertEqual(decode_push('{"method":"unknown_event","params":{"x":1}}')["method"], "unknown_event")

    def test_upstream_mqtt_connect_flag_quirk(self):
        packet = bytes([0x10, 12, 0, 4, 77, 81, 84, 84, 4, 0xC2, 0, 60, 0, 0])
        altered = connect_packet(packet)
        self.assertEqual(altered[9], 0xCA)
        self.assertEqual(packet[9], 0xC2)
        self.assertEqual(connect_packet(b"\x30\x01\x00"), b"\x30\x01\x00")

    def test_cli_property_validation_and_read_only_commands(self):
        self.assertEqual(pair("2.1"), (2, 1))
        for value in ("0.1", "2.1.3", "hello"):
            with self.assertRaises(Exception):
                pair(value)
        self.assertEqual(parser().parse_args(["catalog"]).command, "catalog")


if __name__ == "__main__":
    unittest.main()
