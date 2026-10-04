"""Private-CA provenance/scope and real-paho credential-gating boundaries."""

import hashlib
import ssl
import unittest
from unittest.mock import Mock, patch

import paho.mqtt.client as mqtt

from dreamehome.mqtt_tls import ROOT_CA_PEM, ROOT_DER_SHA256, mqtt_tls_context

HOST = "10000.mt.eu.iot.dreame.tech"
ROUTE = HOST, 19973, "eu", "dreame"


class TlsContextTests(unittest.TestCase):
    def test_embedded_certificate_matches_vendor_authenticated_root(self):
        self.assertEqual(hashlib.sha256(ssl.PEM_cert_to_DER_cert(ROOT_CA_PEM)).hexdigest(),
                         "6db9ea84c7e4c9aec692cd540ff52381f5e37dae47df8ebeb948a4461aeae425")
        self.assertEqual(ROOT_DER_SHA256, hashlib.sha256(ssl.PEM_cert_to_DER_cert(ROOT_CA_PEM)).hexdigest())

    def test_scoped_root_preserves_validation_and_every_other_flag(self):
        context = ssl.create_default_context()
        # Emulate Python 3.14 defaults while testing on local Python 3.12.
        before = int(context.verify_flags) | int(ssl.VERIFY_X509_STRICT) | int(ssl.VERIFY_X509_PARTIAL_CHAIN)
        context.verify_flags = before
        with patch("dreamehome.mqtt_tls.ssl.create_default_context", return_value=context):
            returned = mqtt_tls_context(*ROUTE)
        self.assertIs(returned, context)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(int(context.verify_flags), before & ~int(ssl.VERIFY_X509_STRICT))
        self.assertIn(ROOT_DER_SHA256,
                      {hashlib.sha256(der).hexdigest() for der in context.get_ca_certs(binary_form=True)})

    def test_other_hosts_ports_regions_and_brands_keep_system_trust(self):
        routes = [("10000.mt.us.iot.dreame.tech", 19973, "eu", "dreame"),
                  (HOST, 8883, "eu", "dreame"), (HOST, 19973, "us", "dreame"),
                  (HOST, 19973, "eu", "mova"), ("attacker.invalid", 19973, "eu", "dreame")]
        for route in routes:
            with self.subTest(route=route):
                context = ssl.create_default_context()
                before = int(context.verify_flags) | int(ssl.VERIFY_X509_STRICT)
                context.verify_flags = before
                with patch("dreamehome.mqtt_tls.ssl.create_default_context", return_value=context):
                    self.assertIs(mqtt_tls_context(*route), context)
                self.assertEqual(int(context.verify_flags), before)
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(context.check_hostname)
                self.assertNotIn(ROOT_DER_SHA256,
                                 {hashlib.sha256(der).hexdigest() for der in context.get_ca_certs(binary_form=True)})

    def test_modified_embedded_root_fails_closed(self):
        with patch("dreamehome.mqtt_tls.ROOT_DER_SHA256", "0" * 64):
            with self.assertRaisesRegex(RuntimeError, "integrity"):
                mqtt_tls_context(*ROUTE)


class FakeTlsSocket:
    def __init__(self, events, *, accepted):
        self.events, self.accepted = events, accepted
        self.verified = False
        self.writes = []

    def settimeout(self, value):
        pass

    def setblocking(self, value):
        pass

    def do_handshake(self):
        self.events.append("handshake")
        if not self.accepted:
            raise ssl.SSLCertVerificationError("test certificate rejected")
        self.verified = True
        self.events.append("verified")

    def send(self, packet):
        if not self.verified:
            raise AssertionError("MQTT bytes sent before TLS verification")
        self.events.append("mqtt_bytes")
        self.writes.append(bytes(packet))
        return len(packet)

    def close(self):
        self.events.append("close")


class PahoCredentialGateTests(unittest.TestCase):
    def setUp(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
        self.client.username_pw_set("test-user", "test-password")
        self.context = mqtt_tls_context(*ROUTE)
        self.client.tls_set_context(self.context)
        self.client._create_socket_connection = Mock(return_value=Mock())

    def test_certificate_rejection_prevents_connect_credentials(self):
        events = []
        socket = FakeTlsSocket(events, accepted=False)
        with patch.object(self.context, "wrap_socket", return_value=socket):
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.client.connect(HOST, 19973, 60)
        self.assertFalse(socket.writes)
        self.assertFalse(self.client._out_packet)
        self.assertNotIn("mqtt_bytes", events)

    def test_successful_connect_and_reconnect_repeat_the_verification_gate(self):
        events = []
        first = FakeTlsSocket(events, accepted=True)
        second = FakeTlsSocket(events, accepted=False)
        with patch.object(self.context, "wrap_socket", side_effect=[first, second]):
            self.client.connect(HOST, 19973, 60)
            self.assertTrue(first.writes)
            self.assertIn(b"test-password", b"".join(first.writes))
            self.assertLess(events.index("verified"), events.index("mqtt_bytes"))
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.client.reconnect()
        self.assertFalse(second.writes)
        self.assertFalse(self.client._out_packet)
        self.assertEqual(events.count("handshake"), 2)


if __name__ == "__main__":
    unittest.main()
