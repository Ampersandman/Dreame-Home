# DreameHome API reference

Evidence date: **2026-10-04**. Main source: [Tasshack/dreame-vacuum, revision `9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb`](https://github.com/Tasshack/dreame-vacuum/tree/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb), released as v2.0.1. This is an unofficial protocol reference supplemented by exact L9 app-plugin extraction. Verified login, complete account discovery and metadata reads succeeded on the user's EU account. Combined property reads and MQTT supplied values for 27 washer coordinates, 22 dryer coordinates and 15 vacuum coordinates; all three MQTT sessions authenticated with verified TLS. See [live coverage](live-coverage.md) for model/firmware limits and null RPC replies. No setting writes or appliance actions were executed during validation.

Version `0.3.0b1` uses this transport through exact named L9/vacuum encoders. The new controls and five additional vacuum read candidates have no hardware acceptance yet; see [appliance controls](appliance-controls.md). CLI capture and discovery remain read-only.

## Where the API lives

- [`dreame/protocol.py`](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/protocol.py): the `DreameVacuumDreameHomeCloudProtocol` class contains the DreameHome transport, authentication, signing and MQTT client. The separate MiHome class uses a different Xiaomi API.
- [`dreame/types.py`](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/types.py): property/action addresses, enums, availability functions, polling groups and capability logic.
- [`dreame/device.py`](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/device.py): initialization, model-dependent remapping, packed/JSON settings, command encoders and computed status.
- [`dreame/const.py`](https://github.com/Tasshack/dreame-vacuum/blob/9857362d37fa6a1788a0ce2eb6e1290b3ec7d6fb/custom_components/dreame_vacuum/dreame/const.py): compressed `DEVICE_INFO` table with model, capability and map-key data.
- Platform files (`sensor.py`, `switch.py`, `select.py`, etc.) and `entity.py`: Home Assistant descriptions and their default existence/value/availability rules.
- `dreame/map.py`: map frames, object files, encryption, photos and history decoding. All original source remains in the pinned checkout; key decoder methods are also preserved as text in the extracted implementation catalog.

The compressed `DREAME_STRINGS` array is base64/gzip JSON. It conceals endpoint names and static app constants through array indices; it is not an encrypted per-account secret. The extractor decodes it into [protocol_strings.json](../src/dreamehome/data/protocol_strings.json) and translates the relevant settings into [api.json](../src/dreamehome/data/api.json).

## Servers and account profiles

The base URL is `https://{region}{domain_suffix}:13267`.

| Account | Domain suffix | Regions offered by upstream setup | Default tenant |
| --- | --- | --- | --- |
| DreameHome | `.iot.dreame.tech` | eu, cn, us, ru, sg, kr, by | `000000` |
| MOVAhome | `.iot.mova-tech.com` | eu, cn, us, sg, kr | `000002` |
| TROUVER | `.iot.trouver-tech.com` | eu, us, ru, sg | `000005` |

These region codes select account servers. A returned country such as `DE` is separate metadata used in the region header and subsequent password login. Server lists come from the pinned setup code, not from live availability tests.

Each account profile has its own app Basic authorization, user agent, signing/AES key, app version and tenant. Exact constants are stored in `api.json`. Dreame uses `Dart/3.9 (dart:io)` in this revision; legacy iPhone user-agent strings also remain in the string table.

## Authentication and renewal

Login is `POST /dreame-auth/oauth/token`, content type `application/x-www-form-urlencoded`.

The password digest is the lowercase hexadecimal MD5 of UTF-8 `password + password_salt`. The salt is the static app value in `api.json`. The form is:

```text
grant_type=password&scope=all&platform=ANDROID&type=account&username={percent_encoded_username}&password={digest}
```

If already known, append `country` and `lang`. A refresh login uses:

```text
grant_type=refresh_token&scope=all&platform=ANDROID&type=account&refresh_token={refresh_token}
```

Expected response fields: `access_token`, `refresh_token`, `expires_in`, `uid`, and optionally `tenant_id`, `domain`, `region`, `lang`, `country`. The returned refresh token may rotate. Store the newest one in the eventual HA config entry. The returned `domain` is recorded by upstream but does not automatically replace the region URL.

The client refreshes under a shared lock when the access token expires or has at most 600 seconds remaining. An invalid refresh token can fall back to password login if credentials were supplied. Raw login bodies and tokens are never printed by the new client.

An HTTP 401 with absent/401 JSON `code` receives one refresh attempt. A different 401 JSON `code` is treated as an invalidated session requiring reauthentication, matching the distinction in upstream. HTTP 429 produces a rate-limit error with the `Retry-After` header. HTTP 200 with nonzero envelope `code` is an API error. Individual property errors remain in the result list so callers can identify unsupported or unavailable properties.

The source implements password/refresh login for DreameHome. Its CAPTCHA and two-factor code logic belongs to the separate Xiaomi client. No DreameHome verification-code or MFA flow has been established by this extraction.

## Headers and signing

Normal API calls retain Basic `authorization` and add `dreame-auth: {access_token}`. The access token is not sent as an Authorization Bearer token. Other headers are `tenant-id`, `content-type`, `user-agent`, optional `dreame-meta`, and optional `dreame-rlc`.

For Dreame and MOVA, `dreame-meta` contains `cv=a_{app_version}` plus:

```text
canvasHash = first 8 hex characters of MD5(username + "c")
webglHash = first 8 hex characters of MD5(username + "w")
visitorIdHash = generated 32-character visitor ID
```

TROUVER includes only the version. MOVA adds `dreame-psd: new`. Dreame's Korean region omits `dreame-meta` and `dreame-rlc`.

When region/language/country metadata is present, `dreame-rlc` is base64 of AES-ECB encryption of the PKCS#7-padded UTF-8 string `region|lang|country`, using the profile's 16-byte signing key.

Dictionary request bodies add:

```text
timestamp = integer Unix milliseconds
sign = MD5(canonicalized_parameters + decimal_timestamp + signing_key)
```

Canonicalization is unusual and needs exact reproduction:

1. Sort dictionary keys lexicographically and join fields with `&`.
2. Top-level arrays become compact sorted-key JSON, preserving non-ASCII characters.
3. Nested dictionaries become `key=[{recursive_contents}]`.
4. Empty nested dictionaries become `key=]`.
5. Arrays inside nested dictionaries are omitted from the signature string, while remaining in the transmitted JSON.
6. Booleans become `true`/`false`; null becomes `null`.
7. Nested scalar values use JSON quoting; top-level scalar values use their string value.

The signature contains neither endpoint nor HTTP method. [`signing.py`](../src/dreamehome/signing.py) is tested against the pure functions extracted from the pinned source. JSON HTTP bodies are compact serialized separately; signature canonicalization is not the JSON body itself.

## All extracted routes

The twelve Tasshack routes below use POST. Additional app-plugin routes use GET and are documented separately. Storage downloads use GET on the URL returned by a file endpoint.

| Purpose | Path | Main request fields / response |
| --- | --- | --- |
| Login/refresh | `/dreame-auth/oauth/token` | Form data; session fields at response root |
| Device listing | `/dreame-user-iot/iotuserbind/device/listV2` | Tasshack sends no body; `data.page.records` |
| Bound device metadata | `/dreame-user-iot/iotuserbind/device/info` | `did`; `data` |
| OTC information | `/dreame-user-iot/iotstatus/devOTCInfo` | `did`; typically `data.otcInfo.params` |
| Device command | `/dreame-iot-com{broker_suffix}/device/sendCommand` | Outer `did`, `id`, nested `data`; `data.result` |
| Cached cloud properties | `/dreame-user-iot/iotstatus/props` | `did`, `keys`; `data` |
| Property/event/action history | `/dreame-user-iot/iotstatus/history` | `uid`, `did`, `from`, `limit`, `siid`, `region`, `type:3`, `piid`/`eiid`/`aiid`; `data.list` |
| Cloud userdata read | `/dreame-user-iot/iotuserdata/getDeviceData` | `did`, `model` holding requested keys; `data` |
| Cloud userdata write | `/dreame-user-iot/iotuserdata/setDeviceData` | `did`, `model` holding supplied values; root `result` |
| Interim file URL | `/dreame-user-iot/iotfile/getDownloadUrl` | `did`, `model`, `filename`, `region`; `data` |
| OSS file URL | `/dreame-user-iot/iotfile/getOss1dDownloadUrl` | Also `uid`; filename is upstream's `object_name[1:]`; `data` |
| Device binary file | `/file-bridge/user/getDeiviceFile` | `did`, `uid`, JSON string `fileinfo` with `filename` and `type`; binary bytes |

The spelling `getDeiviceFile` is intentional: it is the spelling present in the source. `getDeviceData` has a misleading request key `model`; preserve its wire name.

In history requests, service/property/event/action identifiers are strings split from `SIID.IID`. The default history start is `1687019188`. Upstream accepts a `time_end` argument but never sends it to the Dreame endpoint, so this client does not advertise an end-time filter. The fixed `type: 3` is source behavior; its underlying server semantics have not been verified.

## Device discovery and pagination

The cloud listing returns records before model filtering. Upstream's `get_supported_devices()` selects records against its decoded vacuum model table; other categories therefore do not appear in its HA setup. The extracted client retains all listed categories.

Useful fields include `did`, `model`, `customName`, `masterUid`, `bindDomain`, `property` (often JSON), `deviceInfo`, firmware data and product identifiers. Shared devices may have a device owner UID different from the logged-in account UID.

Tasshack reads one listing response. [TA2k/ioBroker.dreame at revision `cdfe78ce448d14a5181cfff4c962160fd4d92075`](https://github.com/TA2k/ioBroker.dreame/blob/cdfe78ce448d14a5181cfff4c962160fd4d92075/main.js#L842) supplies a listing body with `sharedStatus:1`, `current:1`, `size:100`, `lang` and `timestamp`. This additional source supports the new client's paginated requests; they are signed using the extracted Dreame signing function.

`list_devices()` follows pages, deduplicates by device ID, and checks `total`, `pages`, `current`, repeated pages and a bounded page limit. It raises `IncompleteDiscoveryError` if the server returns inconsistent/incomplete pagination. `list_devices_response()` without `current` retains Tasshack's bodyless behavior for comparison. A signed request returned the complete three-device EU account list without fallback or warnings. Multiple pages and shared-device visibility still need live validation.

Cloud metadata and OTC data are available independently. Upstream uses bound metadata even if OTC data is unavailable, and sometimes falls back to the listing. The new client exposes both raw results so appliance-specific differences can be inspected.

## Device RPC and identifiers

For `bindDomain` beginning `10000.mt...`, `broker_suffix` is `-10000`. With no broker field it is empty. The cloud envelope is:

```json
{
  "did": "DEVICE_ID",
  "id": 101,
  "data": {
    "did": "DEVICE_ID",
    "id": 101,
    "method": "get_properties",
    "params": [{"did": "CORRELATION_ID", "siid": 2, "piid": 1}]
  },
  "sign": "CALCULATED_DIGEST",
  "timestamp": 1700000000000
}
```

`siid` is a service instance; `piid` is a property; `aiid` is an action; `eiid` is an event. These coordinates only acquire meaning within a model's schema. Upstream's vacuum enum numeric IDs are local bookkeeping, not a universal device schema.

Methods extracted from the source:

- `get_properties`: a list of addressed properties. Source polling batches at most 15 cloud properties. Each result preserves `siid`, `piid`, `code` and any `value`.
- `set_properties`: a list containing the real device `did`, `siid`, `piid` and `value` for each item.
- `action`: a dictionary containing the real device `did`, `siid`, `aiid` and `in` arguments.

Upstream uses its numeric vacuum enum IDs in each read item's `did` field as request/response correlation. The generic client uses `SIID.PIID` strings, which succeeded on `dreame.vacuum.r5023a`. For the exact models `dreame.washer.l9nacn` and `dreame.dryer.l9nacn`, it instead uses the actual device DID inside each read item, matching both extracted plugins. These L9 reads succeeded live. `rpc()` also accepts an exact raw payload for other model-specific conventions; untested products do not inherit L9 semantics.

The new client performs one authentication renewal on a rejected session. It does not automatically replay a command after a network timeout or a successful envelope with a missing result, because command execution is ambiguous. The original source retries some of those calls. Controls and actions must be mapped and verified by model before exposure in HA.

## MQTT device updates

Source metadata supplies the broker through `bindDomain` and the device owner through `masterUid`. MQTT authentication uses the login response's account `uid` as username and the access token as password. Device topic routing uses the device's owner UID.

```text
client_id = "p_" + MD5(device_id + "mqtt" + visitor_id)
topic = /status/{device_id}/{owner_uid}/{model}/{region}/
```

Keepalive is 60 seconds. The source reconnect delay is 1–15 seconds. Korea replaces `10100` with `10000` in the broker hostname and subscribes to both `sg` and `kr` topics. A per-device client is retained initially; broker grouping can be designed later once it is verified.

The source also sets bit `0x08` in the MQTT CONNECT flags. This is a proprietary compatibility behavior, not a standard MQTT recommendation. The optional adapter retains it and is tested against actual paho-mqtt packet construction.

Typical payloads wrap a `data` dictionary containing `method` and `params`. Known source methods are `properties_changed` and `_otc.info`. The extracted adapter retains every JSON method and every service/property identifier, including unfamiliar appliance values. It does not drop unknown L9 messages. Event method names and payload formats for L9 still need observation.

MQTT access credentials are updated when HTTP token refresh rotates the access token. Callbacks are transferred from paho's thread to the asyncio event loop, and stopping the subscription stops its refresh task and MQTT loop.

## Vacuum schemas, packed settings and files

The 370 property mappings and 45 action mappings are fully extracted, as are polling groups, 79 enums, subproperties for AutoSwitch settings and AI bitfields, and the compressed capability table. Polling group labels such as `READ_WRITE_PROPERTIES` are upstream implementation groupings; they do not independently prove all access rights on all firmware.

Many HA values are derived from packed integers, JSON objects, multiple properties, map frames, or model-specific accessors. The 245 entity templates include `exists_fn`, `value_fn`, `available_fn`, units, ranges, icons and other constructor fields as static data or source expressions. Expressions are retained for review; the new client never evaluates them. Base defaults are in `entity_defaults.json`, and accessor/encoder implementations are in `implementations.json`.

Robot maps require the existing frame decoder and per-model key/capability behavior, not just a file download. Upstream's default object prefix is `{model}/{owner_uid}/{did}/0`. Device photos use file type `obstacle` and extra decoding in `map.py`. Map rendering assets and full source remain in the checkout. No washer/dryer map or camera feature is inferred from vacuum features.

## Transport differences and validation limits

The pinned upstream implements its own TLS 1.2/1.3 handshakes and MQTT socket behavior. Inspection found no certificate chain/hostname validation or verification of the peer's signed handshake authentication in that custom transport. Its exact source is preserved for analysis.

The new HTTPS and MQTT transports use verified TLS. The HTTP backend runs blocking stdlib requests in a worker and advertises `Accept-Encoding: identity`; it refuses authenticated redirects. The HA component uses its managed aiohttp session. Credentials are never attached to a storage download. Login, listing, metadata, addressed property reads and authenticated MQTT were tested against the user's EU account; other regions remain untested live.

The exact EU broker `10000.mt.eu.iot.dreame.tech:19973` needs a vendor CA rather than the system public CA store alone. [mqtt_tls.py](../src/dreamehome/mqtt_tls.py) adds the public root recovered from a signature-verified official APK only for the reviewed Dreame account/host/port. Certificate-chain, validity, signatures and hostname checks remain enabled (`CERT_REQUIRED`, `check_hostname=True`). For that host it clears `VERIFY_X509_STRICT`, because the vendor leaf omits the authority-key-identifier extension; this preserves ordinary certificate verification. Other hosts retain default trust settings. See [the trust provenance](mqtt-trust-research.md). No unverified or community-fingerprint fallback is used.

These differences are deliberate implementation decisions, not evidence that Dreame accepts every standard HTTPS/MQTT client. The transport interface is injectable so a HA-managed HTTP session or another verified transport can be added after live validation. A fingerprint rejection needs a verified compatible transport; it should not be diagnosed automatically as an incorrect user password.

No universal “list every property for every product” endpoint or Dreame plugin/schema download endpoint was found in Tasshack's cloud class. Full coverage for an unfamiliar product requires its exact model schema or plugin and observed values. Enumeration of connected devices and enumeration of a model's complete property definitions are separate operations.
## Additional app-plugin discovery

The source-derived Tasshack catalog above remains reproducible and contains its original routes. A separate mobile reverse-engineering source established `GET /dreame-product/upgrades/appplugin`; see [L9 app research](l9-schema-research.md) for its pinned origin. `DreameHomeClient.plugin_manifest(device)` sends unsigned query parameters `model`, `did`, numeric `os` and numeric `appVer`, using the authenticated account headers and the same renewal/error handling as POST requests.

The initial `os=2, appVer=102060300` request returned a vacuum HarmonyOS bundle and empty L9 records. Actual later downloads establish `os=0` as iOS and `os=1` as Android. Using the verified app version `102060603` returned exact RN plugins for both laundry models and the vacuum. The washer plugin is version 83, extension 2175; the dryer is version 130, extension 2186. Both L9 iOS bundles are plain JavaScript and were parsed without execution. Their definitions are in [l9_washer.json](../src/dreamehome/data/l9_washer.json) and [l9_dryer.json](../src/dreamehome/data/l9_dryer.json). Assets downloaded from returned HTTPS URLs receive no account headers. Proprietary plugins and APKs remain local and are excluded from releases.

For Dreame accounts, both plugin helpers now default to `os_code=0` and `appVer=102060603`, matching the successful iOS lookup. Pass `os_code=1` for Android or an explicit numeric `app_version` to reproduce another request. The pinned main authentication/profile constants remain unchanged.

The signature-verified base app also contains `GET /dreame-product/upgrades/h5plugin`. `h5_plugin_manifest(device, os_code=0, app_version=102060603)` uses the same four authenticated query arguments. All six tested iOS/Android requests for these three devices returned successful envelopes with empty `data`; the complete H5 request semantics remain unresolved. Neither GET route includes a POST JSON signature.

## Exact L9 model contracts

The washer plugin defines 27 properties, 22 programs and four actions; the dryer defines 22 properties, 31 programs and four actions. Initial read candidates come from their notification lists: 24 washer and 17 dryer coordinates. Only network authorization `3.14` has a direct `get_properties` call in each static plugin. Notification membership therefore supplies a bounded validation plan, rather than formal read-access rights. Subsequent live reads and notifications established additional coordinates separately. The dryer returned `null` for `3.11` even with code 0, so a success code alone does not establish usable sensor data.

Program tables, default settings and filters are retained for future control implementation. Defaults are app configuration, not current appliance values. Codes such as washer spin speed must be decoded through explicit source value lists rather than assigned measurement units directly. Source-inferred booleans, unknown enum codes and unknown dryer field `4.7` remain raw in the beta. The dryer plugin's subscription label for `3.11` conflicts with its night-mode UI setter at `3.13`; the two coordinates remain separate.

Both L9 plugins additionally use cloud userdata key `prop.s_auto_upgrade` for automatic firmware updates. This is distinct from local `AsyncStorage` program history and reminder preferences. Existing `get_device_data`/`set_device_data` client methods preserve the cloud route and wire key; controls are not enabled by the beta. Exact action payloads are retained for later testing. Passive collection does not automatically invoke the app's `reportAll` action `2.4`.
