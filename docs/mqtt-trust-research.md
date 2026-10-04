# MQTT broker trust investigation

Research date: 2026-10-04. No account credentials were transmitted during the certificate probe or this public-source investigation.

Paths under `references/` and `private/` below identify excluded local research material. The public repository contains the recovered trust certificate in the API and this factual provenance summary; it does not redistribute APKs or private captures.

**The broker CA has now been recovered from a cryptographically verified Dreame APK.** Loading its private root authenticated the actual EU MQTT endpoint with certificate-chain, validity and hostname verification. The implementation uses this vendor-authenticated CA; the community fingerprint described below remains corroborating research evidence and is not used as a fallback.

The EU endpoint `10000.mt.eu.iot.dreame.tech:19973` failed normal certificate-chain validation with OpenSSL verification code 19 (`self-signed certificate in certificate chain`). The saved unauthenticated probe is `references/mqtt-tls.json`; `references/mqtt-tls.untrusted.pem` is an **untrusted observation**, not an approved CA file. Its leaf SHA-256 is:

```text
0a55ff4bbf5acbb52bfb1b7a941ea097c75f5ca58d0d5eb16464c1d255988200
```

The leaf issuer's `GlobalSign Organization Validation CA` common name does not establish that this certificate chains to a genuine public GlobalSign root. The observed validity spans 1969-2969, and the recorded SAN includes the EU MQTT host pattern.

## Independent public corroboration

An independently published integration contains the same certificate fingerprint in a committed constant. The checkout is saved unchanged under `references/sf25-tls-research/`:

- Repository: [maestrea76/HA-Dreame-SF25-WiFi-Integration](https://github.com/maestrea76/HA-Dreame-SF25-WiFi-Integration).
- Pinned commit: `6dfb9aaa4f77088731ac97c526d56584612c3ac7`, committed 2026-09-05.
- [const.py at that commit](https://github.com/maestrea76/HA-Dreame-SF25-WiFi-Integration/blob/6dfb9aaa4f77088731ac97c526d56584612c3ac7/custom_components/dreame_sf25/const.py) declares `MQTT_CERT_SHA256` with the identical leaf fingerprint. File SHA-256: `d632b8cfb0d7cfab3e9a8a3baac5aead53b27ba6fb4846b4fb9fbf56a6354b3f`.
- [mqtt.py at that commit](https://github.com/maestrea76/HA-Dreame-SF25-WiFi-Integration/blob/6dfb9aaa4f77088731ac97c526d56584612c3ac7/custom_components/dreame_sf25/mqtt.py) checks the leaf fingerprint after the TLS handshake and before allowing MQTT credentials. File SHA-256: `62b3f286ff53ca55f5b11d117844a6d05168f252b9a8488a117f27b675fba51a`.

This is primary evidence of that author's independently published trust decision. It corroborates the observed leaf without deriving the expected pin from our current network connection. It is **community provenance**, not a Dreame-issued statement binding this certificate to its broker. Neither the pinned source nor the network probe supplies an independently authenticated broker CA. The upstream Tasshack protocol does not supply such a CA either, and the inspected ioBroker MQTT code uses `rejectUnauthorized: false`.

A hardcoded pin from the reviewed source can authenticate continuity with that exact certificate. Restrict any such trust decision to the exact reviewed EU hostname and port; reject missing or mismatched certificates, and never update the expected fingerprint from the peer's current certificate automatically. A peer certificate change should disable MQTT while HTTP polling remains usable. Describe this accurately as leaf pinning, not ordinary public-CA validation or vendor-authenticated CA trust.

## Stronger vendor-authenticated APK path

The official [smartlife.dreame.tech Android association file](https://smartlife.dreame.tech/.well-known/assetlinks.json) was fetched successfully over normal verified HTTPS. It names `com.dreame.smartlife` and publishes these allowed APK signing-certificate SHA-256 fingerprints:

```text
6c37b0d6b0983a8e39955dfd85cbef4a50143728fa8215442e5e2a4325f2350c
4a30175c6fddd90184bbb6c4f8aca8307da2af8fe4884bb25638f8cc8c20386c
fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c
```

Saved response: `references/l9-public/smartlife.dreame.tech-eecf4433cbda.json`, SHA-256 `e901e96ec2ecebb66c10a9cbc2bbf7f0238178fc7af08cdd5fa5b31c5d3e4f61`, with its source and HTTP metadata alongside it. The official `app.dreame.tech` association file independently returned the same declarations during the parallel investigation.

This provides a vendor-authenticated way to establish an APK's publisher even when its download is served through a third-party mirror: cryptographically verify its APK signature with Android's `apksigner`, compare the actual signer certificate to one of the vendor declarations, and only then inspect any embedded certificate/CA material as vendor-authenticated application data. A website's displayed signer fingerprint or a `.RSA` file extracted without verification is insufficient. A bundled CA must also be tied to the MQTT implementation, rather than merely assumed relevant because it appears somewhere in the app.

The local Android SDK includes build-tools 35.0.0 and 36.0.0 and their `apksigner` implementation; Java 17 is available. Public official download pages currently lead to Google Play. The subsequent APKPure download was cryptographically verified before this certificate investigation, as described below.

## Recovered vendor-authenticated CA and successful live verification

The downloaded application bundle SHA-256 is `95c0dfaa27b25238ca799cfe0644fd2dc41635877eaab8a50743f5cd52addc82`. Android's `apksigner` accepted v2/v3 signatures for every extracted APK, and their actual signer certificate SHA-256 was `4a30175c6fddd90184bbb6c4f8aca8307da2af8fe4884bb25638f8cc8c20386c`, matching the official Dreame association declarations. Results and paths are recorded in `references/l9-public/dreamehome-apks/verification.json`.

The base APK SHA-256 is `fbeeb15c93f3a12e52983a5ffdf9258556b82407a066203814d3a1db20269792`. Its asset `assets/flutter_assets/assets/cert/cacert.pem` contains a private root and intermediate. The original asset SHA-256 is `ea9476cdff506070b1169a989a115502a5bc21bdd9d3e4364587257615a220b5`. The certificates were extracted to `references/l9-public/mqtt-certificates/` with their provenance; application private keys were not extracted or used.

| Certificate | SHA-256 of DER certificate |
| --- | --- |
| Private root, named GlobalSign Root CA | `6db9ea84c7e4c9aec692cd540ff52381f5e37dae47df8ebeb948a4461aeae425` |
| Private intermediate, named GlobalSign Organization Validation CA | `5bc61787c9e2a730161a7e388580dec09aaca27e4eccd7b720867a8b431ab770` |

Both the complete asset bundle and the root alone authenticated `10000.mt.eu.iot.dreame.tech:19973` through ordinary OpenSSL certificate verification, with `CERT_REQUIRED` and hostname verification enabled. Their live credential-free results are `references/mqtt-ca-preflight-sandbox.json` and `references/mqtt-ca-root-only-preflight.json`. The verified leaf matched the earlier `0a55ff...` observation. Thus this application root is directly tied to the production broker by a successful cryptographic chain check, rather than guessed from an asset filename.

Enabling `VERIFY_X509_STRICT` reproduced failure code 85, `Missing Authority Key Identifier`, recorded in `references/mqtt-ca-strict-preflight.json`. Python 3.14 enables this stricter extension-conformance behavior by default. The scoped helper in `src/dreamehome/mqtt_tls.py` loads the authenticated root and clears only `VERIFY_X509_STRICT` for the exact tuple `(10000.mt.eu.iot.dreame.tech, 19973, eu, dreame)`. It retains certificate signature and chain verification, certificate validity checks, required certificates and hostname checks. Other hosts, ports, regions and account brands receive an unchanged system-default context. This is a narrow accommodation for the vendor's nonconforming certificate extension, not disabled TLS authentication.

The helper embeds only the public root and its APK/signer/DER provenance constants; it validates the embedded DER hash before loading it. It contains no credential-bearing connection logic, network-derived trust enrollment, community-pin fallback, or app client-private-key use. Call the context factory in a worker to keep system trust-store reads outside Home Assistant's event loop.

## Credential-gating hook in paho 2.1.0

The actual installed implementation and [paho's tagged primary source](https://github.com/eclipse-paho/paho.mqtt.python/blob/v2.1.0/src/paho/mqtt/client.py) agree: `reconnect()` obtains its socket through `_create_socket()`, which invokes `_ssl_wrap_socket()` before returning. `reconnect()` calls `_send_connect()` only after socket creation succeeds. Therefore, an exception raised by a certificate/pin check inside `_ssl_wrap_socket()` prevents MQTT CONNECT credentials on the initial connection and every reconnect.

The default wrapper performs its handshake and may call `ssl.match_hostname` when the context does not check hostnames. That function is unavailable in Python 3.12+, so a deliberately pinned branch needs its own completed-handshake/DER-check wrapper rather than passing a nonchecking context into the default implementation. Exact-host restrictions remain mandatory. A failed normal TLS handshake cannot safely reuse its TCP socket; close it and create a new socket if an explicitly reviewed pin fallback is attempted.

For the implemented CA path, boundary tests must establish exact trust scope, required certificate and hostname checks, failure before credential-bearing CONNECT, and repeated verification on reconnect. They must cover the real paho hook ordering as well as the CA helper's configuration. Unknown hosts retain system trust and have no fallback.

The implemented six offline tests cover root DER identity and integrity, exact route scope, required certificate/hostname settings, preservation of every verification flag except scoped STRICT, and the actual paho 2.1.0 connect/reconnect ordering with mocked TLS handshakes. Rejected handshakes produce neither MQTT credential bytes nor a queued CONNECT packet. A successful fake handshake permits the real paho CONNECT encoder, and a rejected reconnect repeats the gate.

A subsequent authenticated, read-only EU capture successfully connected all three device MQTT clients through this verified CA path. During the five-minute online observation, the washer supplied 342 messages and the dryer 320; the idle vacuum supplied no messages but its MQTT client remained connected. The allowlisted [verification summary](live-verification.json) records these counts without device/account identifiers or values. This establishes live account authentication and laundry pushes for the reported firmware; a real Home Assistant runtime test remains pending.
