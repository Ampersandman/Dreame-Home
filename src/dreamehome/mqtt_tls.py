"""Verified MQTT TLS with narrowly scoped, vendor-authenticated private CA trust.

The public root was extracted from assets/flutter_assets/assets/cert/cacert.pem
in the cryptographically verified com.dreame.smartlife APK. Its APK signer is
declared by Dreame's verified-HTTPS Android association file. This is private
vendor CA trust, not a GlobalSign public root despite its common name.

Provenance: docs/mqtt-trust-research.md and
references/l9-public/mqtt-certificates/provenance.json.
"""

import hashlib
import ssl

APP_ASSOCIATION_URL = "https://app.dreame.tech/.well-known/assetlinks.json"
APP_APK_SHA256 = "fbeeb15c93f3a12e52983a5ffdf9258556b82407a066203814d3a1db20269792"
APP_SIGNER_SHA256 = "4a30175c6fddd90184bbb6c4f8aca8307da2af8fe4884bb25638f8cc8c20386c"
ROOT_DER_SHA256 = "6db9ea84c7e4c9aec692cd540ff52381f5e37dae47df8ebeb948a4461aeae425"

ROOT_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIDDzCCAfegAwIBAgIJAPvMK3fFXUEgMA0GCSqGSIb3DQEBCwUAMB0xGzAZBgNV
BAMMEkdsb2JhbFNpZ24gUm9vdCBDQTAgFw02OTEyMzExNjAwMDBaGA8yOTY5MDUw
MjE2MDAwMFowHTEbMBkGA1UEAwwSR2xvYmFsU2lnbiBSb290IENBMIIBIjANBgkq
hkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtdVI+1rZpIpB8YlmnzWFnvJyGzlBbxEh
RwgSanox6OypwX27htEFFJzMxz5YGv9nABm3b3SUB+0zcAkJYw/Q9lZoT1w0m9Cr
5KJMxofpD8JjsZWFE5hvJ5NIyRS4tOgimGsIfvHGMzihZ9sLnq7kBtX7u5hIv/A5
eSvifaroS2NombTFMQrV6ZNIvpFALbMUbp02+mexm7P59c7OzJVupQAWJSFOepIu
UwhyYLe1oR/HTiKcIuzDSp49QxhSNYuLpSUOYo/YU4GTMoKEhXD7u+AyeOzuHrnV
H7+/U7TlXFtMkyt+ZwQw+s8+/jzi4v9jG5XL82uVbr2FN0EC0PEhrwIDAQABo1Aw
TjAdBgNVHQ4EFgQUQXiLQz2aun8vl2Hy1RCja8nZ4qMwHwYDVR0jBBgwFoAUQXiL
Qz2aun8vl2Hy1RCja8nZ4qMwDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQsFAAOC
AQEAaAuVj1RNRRXfV7wk2VtLr6aKPoi7mlG9OSijHxAbmwV1KMyGR6gUpqToBpe/
xQN+AjJK1Unex0hkN7+RZhpe8ajWqtniZ+oq9Xd+be0JW2KqZmA18r5arJj4DiCt
Asa557/RNxuiIMc/uwvPtVq2C9uPX562esS02e2bRODH+l+aKcFzeCKotccJGej7
NrfwypYpmoqrwko/4pe9cMBc3O1CLl2ZYy+YreHMFitmL6xGnC4a6HuTcZgK/ntj
zewB8u+e2dMQwnBclahtLtb8oMmCHCWlgMTVU1MrjlWldvULalpMnIE5gsHKNXeC
z0PJitlGIfun4TuQQhVCf5B2aA==
-----END CERTIFICATE-----
"""


def mqtt_tls_context(host: str, port: int, region: str, account_type: str) -> ssl.SSLContext:
    """Create a verified context; private root trust applies to one reviewed route.

    Run this factory in a worker because loading system trust can touch disk.
    The broker's leaf lacks Authority Key Identifier. Clearing strict extension
    conformance for this route preserves chain signatures, certificate validity,
    CERT_REQUIRED and hostname verification. Other contexts retain all defaults.
    """
    context = ssl.create_default_context()
    if (host, port, region, account_type) == ("10000.mt.eu.iot.dreame.tech", 19973, "eu", "dreame"):
        der = ssl.PEM_cert_to_DER_cert(ROOT_CA_PEM)
        if hashlib.sha256(der).hexdigest() != ROOT_DER_SHA256:
            raise RuntimeError("Embedded Dreame MQTT CA integrity check failed")
        context.load_verify_locations(cadata=ROOT_CA_PEM)
        context.verify_flags = int(context.verify_flags) & ~int(ssl.VERIFY_X509_STRICT)
    return context
