# L9 washing machine and Twin/Dual Inverter L9 investigation

The exact L9 washer and Twin Inverter L9 dryer are now identified, their official model plugins extracted, and their telemetry validated against the user's EU account and real Home Assistant installation. The read-only telemetry beta is published through [Ampersandman/Dreame-Home](https://github.com/Ampersandman/Dreame-Home). Genuine GitHub HACS, hassfest and Python 3.12/3.14 offline CI checks passed. After the user installed through HACS on HA OS 18.3 / Core 2026.9.4, the supplied diagnostics confirmed complete discovery, successful API updates and MQTT connectivity for all three appliances. Dreame's matching product page names the dryer [AI Dual Inverter Dryer L9](https://global.dreametech.com/products/l9-drayer); the cloud model, not the retail name, determines its schema.

The [official L9 washer page](https://global.dreametech.com/products/l9-washer) describes app control, parameter adjustment, cloud programs, OTA and notifications. It also describes detergent/softener alerts in the app. That establishes useful investigation targets; it does not publish their API coordinates, ranges or access rights.

The dryer page describes built-in temperature/humidity sensing. Physical sensors described in product material are not proof that their raw values are exposed through the cloud.

## Verified account identities

A read-only EU DreameHome account scan on 2026-10-04 returned all three registered devices. Verified TLS, login, signed listing and device metadata requests succeeded, with no pagination warnings. Exact device IDs remain in a local private identification report excluded from this repository, without passwords, access/refresh tokens or raw property blobs.

| Appliance | Cloud model | Product ID | Extension ID | Firmware |
| --- | --- | --- | --- | --- |
| Washing Machine L9 | `dreame.washer.l9nacn` | `11528` | `2175` | `0.1.1_3017` |
| Twin Inverter Dryer L9 | `dreame.dryer.l9nacn` | `11554` | `2186` | `0.1.6_3029` |
| L10s Ultra Gen 3 | `dreame.vacuum.r5023a` | `11080` | `1961` | `4.3.9_1304` |

All three devices are owned devices rather than shared devices. The vacuum model matches the pinned upstream model catalog. Neither L9 matches the earlier public washer candidates, and none of these exact model codes appears in the saved public MIoT index. The exact laundry definitions were instead recovered from cloud-provided app plugins. The `l9nacn` suffix is part of the identifier; the confirmed account server is EU.

## What the repository establishes

The original Tasshack repository supplies vacuum protocol/model evidence, not the L9 laundry tables. The extracted API now retrieves the complete account device list, inspects metadata, reads addressed properties and listens to notifications. Exact L9 definitions come from the official model plugins, without assigning vacuum or unrelated public washer coordinates to the laundry devices.

The normalized catalogues are [l9_washer.json](../src/dreamehome/data/l9_washer.json) and [l9_dryer.json](../src/dreamehome/data/l9_dryer.json). The washer has 27 property definitions, 22 programs and 4 actions; the dryer has 22 property definitions, 31 programs and 4 actions. Source access evidence, English labels, enums, program settings and action/write encoders are retained separately from live support. For example, washer `2.1` is run status, whereas the unrelated `r1111` candidate calls `2.1` left time. Exact model matching prevents that incorrect assignment.

## Completed exact-model extraction and live validation

Authenticated `GET /dreame-product/upgrades/appplugin` requests with exact DID/model and numeric `appVer=102060603` returned washer plugin `83` and dryer plugin `130`. Their `project.json` and bundle names prove `os=0` is iOS and `os=1` is Android. The first `os=2` attempt returned HarmonyOS vacuum material and no laundry plugin; it was the wrong platform for those lookups. A tested H5 lookup returned empty data, while the RN route supplied both exact L9 bundles. See [L9 schema research](l9-schema-research.md) for reproducible extraction and source hashes. Vendor plugins and signed APKs are local research material and are not included in the integration distribution.

The initial capture found the laundry devices offline. After the user powered them on and viewed app status, a fresh capture established these results without issuing cycles, actions or setting writes:

| Exact model | Source initial read plan | Successful RPC rows | Non-null RPC values | Combined non-null RPC/MQTT coordinates | MQTT messages |
| --- | --- | --- | --- | --- | --- |
| `dreame.washer.l9nacn` | 24 coordinates | 27, all code 0 | 27 | 27 | 342 |
| `dreame.dryer.l9nacn` | 17 coordinates | 23, all code 0 | 20 | 22 | 320 |
| `dreame.vacuum.r5023a` | 15 coordinates | 15, all code 0 | 15 | 15 | 0 while idle |

This 300-second capture ran from `2026-10-04T19:26:07Z` to `19:31:09Z`. Dryer RPC coordinates `3.11`, `5.1` and `4.7` returned null despite code 0. Earlier MQTT values for `5.1` and `4.7` remained in the observation store, so combined coverage is 22 non-null coordinates; `3.11` had no usable observation. RPC success counts and usable-value counts must remain distinct.

All three MQTT subscriptions connected successfully. Their trust path uses a CA extracted from an APK whose cryptographic signature was verified against Dreame's official HTTPS app-association declaration. Credential-bearing MQTT retained `CERT_REQUIRED` and hostname verification. A scoped compatibility adjustment for the EU broker clears only strict X.509 extension conformance; chain, signature, validity and hostname checks remain enabled. The prior certificate failure is resolved. Details are in [MQTT trust research](mqtt-trust-research.md).

The exact app wrapper and successful laundry RPC reads use the actual device ID in every `{did, siid, piid}` item. Additional coordinates observed over MQTT were subsequently read, accounting for the larger final RPC counts. The washer's three source-write-only fields also supplied notifications and readable values. Source catalogues retain source-only verification flags; the private live capture and sanitized support evidence establish actual firmware support independently. Exact IDs and account details remain private.

The dryer reported `4.7` in addition to its 22 source-defined coordinates. Its meaning remains unknown, so it receives a neutral coordinate name. The app's night-mode UI points to `3.13`, while its subscription table points to `3.11`; this conflict remains documented. The captured null `3.11` cannot establish a usable value or resolve the mapping. Unknown enum codes and fields remain visible without guessed labels.

The collector did not send the app's initial status-report action. Viewing status in the official app supplied updates during the read-only observation. Favorites, program memory, usage records and several reminder settings are held in the app's local storage; this is not proof of corresponding cloud history APIs. Product pages' physical temperature/humidity sensors likewise do not prove raw cloud telemetry exposure.

## Verified Home Assistant telemetry snapshot

The subsequently supplied Home Assistant diagnostic confirms complete account discovery and a successful last API update. All three appliances are present, cloud-online and connected to MQTT. No metadata, property-read or cloud-userdata errors are reported. The [Home Assistant diagnostic review](ha-diagnostics-review.md) records the sanitized findings and their limits.

| Exact model | Tracked property coordinates | Coordinates with a usable value | Last usable value source |
| --- | --- | --- | --- |
| `dreame.washer.l9nacn` | 27 | 27 | MQTT for all 27 |
| `dreame.dryer.l9nacn` | 23 | 22 | MQTT for all 22 |
| `dreame.vacuum.r5023a` | 15 | 15 | RPC for all 15 |

These are property-coordinate counts, not Home Assistant entity totals. Every usable property root in this snapshot is an integer; no compound property values or expanded compound fields were present. All recorded last result codes are zero, and no observations were dropped or reported as truncated. A connected vacuum MQTT client does not establish vacuum pushes when the retained values came from RPC.

The washer covers all 27 source-defined coordinates. The dryer covers 21 of its 22 source-defined coordinates plus source-unknown `4.7`. Its code-zero `3.11` row still has no usable value, so its initial read result correctly remains partial at 16 of 17 candidates. Runtime labels match the exact source definitions; the `3.11` subscription versus `3.13` night-mode UI conflict remains unresolved. Nothing in this snapshot requires changing the property mappings or manufacturing a state for the missing value.

Cloud-userdata key lists and cache counts do not establish which requested settings were accepted or their returned values. The automatic firmware-update setting is therefore not verified by this diagnostic. No appliance cycles, actions or writes were issued during the extraction and read-only validation.

## Public schema candidates found

Additional evidence came from [TA2k/ioBroker.dreame's public MIoT schema lookup](https://github.com/TA2k/ioBroker.dreame/blob/cdfe78ce448d14a5181cfff4c962160fd4d92075/main.js#L1173). The public [MIoT instance index](https://miot-spec.org/miot-spec-v2/instances?status=all), downloaded on 2026-10-04, listed:

| Exact model | Schema | Registry status | Properties / actions / events | Marketing identity |
| --- | --- | --- | --- | --- |
| `dreame.washer.r1111` | `urn:miot-spec-v2:device:washer:0000A01F:dreame-r1111:1` | debug | 92 / 13 / 7 | Unconfirmed |
| `dreame.washer.r1112` | `urn:miot-spec-v2:device:washer:0000A01F:dreame-r1112:1` | debug | 92 / 13 / 7 | Unconfirmed |

Complete public responses were retained as local research inputs excluded from this repository. The normalized [washer_candidates.json](../src/dreamehome/data/washer_candidates.json) includes provenance, types, access rights, units, enum values, ranges, action inputs/outputs, events and suggested HA platforms. These suggestions are prospective mappings, not verified entities on the appliances.

The exact L9 schema is now resolved from its own plugin, independently of these candidates. The older debug model `dreame.dry.p2011`, a hand-dryer entry and drying-related settings in candidate washer schemas provide no evidence of standalone L9 support. Neither `r1111` nor `r1112` applies to either confirmed `l9nacn` appliance; the integration does not use these candidate definitions for them.

Examples from the `r1111` candidate, conditional on an exact model match and successful live reads:

| Address | Defined property | Access | Defined unit |
| --- | --- | --- | --- |
| 2.1 | Left Time | read, notify | minutes |
| 2.2 | Target Temperature | read, write, notify | Celsius |
| 2.3 | Temperature | read, notify | Celsius |
| 2.8 | Door State | read, notify | unspecified |
| 2.14 | Spin Speed | read, write, notify | unspecified |
| 2.15 | Water Consumption | read, notify | unspecified |
| 2.16 | Power Consumption | read, notify | unspecified |
| 2.18 | Mode | read, write, notify | unspecified |
| 2.20 | Run Status | read, notify | unspecified |
| 2.24 | Status | read, notify | unspecified |
| 2.26 | Device Fault | read, notify | unspecified |
| 2.45 | Filter Need Cleaning | read, notify | unspecified |
| 3.1 | Physical Control Locked | read, write, notify | unspecified |
| 7.1 | Fabric Softener Left Level | read, notify | percent |
| 8.1 | Specialized Detergent Left Level | read, notify | percent |
| 9.1 | Detergent Left Level | read, notify | unspecified |

The candidates also define washing completion, lock and low-detergent events. A missing unit must remain unresolved until live values establish the scale. In particular, do not assign liters, kWh or RPM just from a property's label.

## Reproduction and remaining work

Device discovery can be repeated with hidden local credential entry through `tools/scan_cloud_account.ps1`. `tools/fetch_device_plugins.ps1` obtains exact-model plugin metadata and downloads only HTTPS URLs supplied by the cloud, without sending account headers to object storage. `tools/capture_device_api.ps1` performs read-only live capture. The final validation is retained privately in `private/device-api-online-validation-observations.json`; [live coverage](live-coverage.md) records public counts and evidence boundaries.

Further passive observation during ordinary washer/dryer use can establish phase-dependent settings, optional values, door changes, completion events, stale behavior and additional enum states. It must retain complete compound/event payloads and unknown coordinates without guessing property ranges, units or meanings. A null or failed property response must not become a manufactured sensor value. Shared-device behavior is untested because this account's devices are owned.

Initial HACS installation, authentication, discovery and updating values for all three appliances have user-reported confirmation on HA OS 18.3 / Core 2026.9.4. The supplied diagnostic additionally establishes the per-coordinate coverage and real HA MQTT connectivity described above. It does not establish ordinary-cycle behavior, compound-value expansion or lifecycle fault handling. Reauthentication, token rotation, stored-token restart, reload/unload, stale/offline availability and detailed app-to-entity comparisons remain pending. Controls, vacuum maps/history and more packed-setting decoding belong to later verified extensions; no appliance control is enabled in the telemetry beta. A GitHub release remains optional for HACS source installation.

Passwords and tokens remain in local prompts/session handling, not shared captures or documentation. Local captures may contain stable device identifiers and stay private. The source catalogues and verified live results establish substantial L9 telemetry support while preserving the remaining limits of the broader goal to expose everything the cloud supports.
