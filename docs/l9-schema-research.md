# Exact L9 schema and app-plugin research

Investigation date: 2026-10-04. Exact targets are `dreame.washer.l9nacn` (product `11528`, extension `2175`) and `dreame.dryer.l9nacn` (product `11554`, extension `2186`). Account device identifiers stay in the private identification report.

Paths under `private/`, `references/` and `upstream/` below identify local research inputs excluded from this repository. The factual catalogs, source hashes and extraction tools are published; proprietary app bundles and account records are not.

## Result

Both exact L9 model plugins have been recovered from the authenticated Dreame cloud. Washer plugin version `83` contains plain JavaScript with 24 state/subscription coordinates, 3 additional source-write-only coordinates, 22 named programs and 4 actions. Dryer plugin version `130` defines 17 state/subscription coordinates, 5 additional UI control coordinates, 31 programs and 4 actions. Factual catalogues are [l9_washer.json](../src/dreamehome/data/l9_washer.json) and [l9_dryer.json](../src/dreamehome/data/l9_dryer.json), reproduced offline by [extract_l9_washer.py](../tools/extract_l9_washer.py) and [extract_l9_dryer.py](../tools/extract_l9_dryer.py).

These are exact-model definitions rather than borrowed MIoT candidate schemas. The pinned vacuum integration and the public MIoT index do not define either L9 model; washer candidates `dreame.washer.r1111` and `dreame.washer.r1112` remain unrelated. The extracted app definitions establish coordinates and UI meanings, but do not guarantee every property can be polled or that the device reports every field on every firmware. Live verification is recorded separately. No device actions or setting writes were issued during this extraction.

A source-backed per-device app-plugin lookup route supplied the real laundry definitions. It is separate from device RPC:

| Route | Method and parameters | Evidence and limitation |
| --- | --- | --- |
| `/dreame-product/upgrades/appplugin` | GET; query `model`, `did`, numeric `os`, numeric `appVer` | The author's [probe script](https://github.com/consolesplayingconsoles/dreamehome-client/blob/562a7cb7a8a38336ff1387d02e7e1b4adae7c582/re/probe_plugin.py#L22) identified this RN plugin route. Exact-model authenticated requests with `appVer=102060603`, `os=0` or `os=1` returned the real washer and dryer plugin downloads. `project.json` proves `0=ios`, `1=android`. |
| `/dreame-product/public/common-plugin/getCommonPlugins` | POST according to the probe's server feedback; request body unresolved | Same recovered route list. No verified request DTO or L9 association, so do not add guessed requests to normal integration polling. |
| `/dreame-product/public/common-plugin` | POST according to the probe's server feedback; request body unresolved | Same recovered route list. No verified request DTO or L9 association. |
| `/dreame-product/upgrades/h5plugin` | GET using the same four query arguments tested above | Literal at byte offset `574901` in the signature-verified official Android app library. Authenticated `os=0/1` requests succeeded but returned empty `data` for these devices; the RN route supplied the laundry definitions. Complete H5 DTO semantics remain unresolved. |

The public probe's OS mapping was uncertain. Actual model downloads resolve it: `os=0` returns `index.ios.bundle`, and `os=1` returns `index.android.bundle`. The earlier `os=2` lookup returned no laundry bundle and a vacuum HarmonyOS bundle; treating OS 2 as Android was the reason the first laundry lookup failed. The numeric version `102060603` is verified against official Dreamehome `2.6.6.3`; dotted version strings triggered server format errors in the public probe. The lookup uses the standard app Basic authorization, tenant ID and session `Dreame-Auth` headers for GET. It does not add the POST JSON signature to the query.

A TLS-verified, unauthenticated GET on the EU endpoint for `model=dreame.washer.l9nacn`, `os=2`, `appVer=102060300` returned HTTP 401. That confirms this request requires authentication; it does not establish the correct complete parameter set or return schema. The request did not contain a device ID, credentials or tokens and issued no device command.

## Exact washer definitions and limits

The iOS ZIP is a cloud-provided file under extension `2175`; its SHA-256 is `33ea438c47b2c33572b08017c88fb7450bcd8157ba752673fac9f2ebae6fc9f8`. The source catalogue records the exact download URL. Its `dreame.washer.l9nacn/project.json` declares `projectName=dreame.washer.l9nacn`, `versionCode=83`, `plat=ios`; the JavaScript bundle SHA-256 is `8f235e237807137ffdb0674d61d622b0d8d7db6650328e473839d079d876ed90`. The Android ZIP independently declares the same exact model/version and `plat=android`, SHA-256 `d0753a36897a65a8db6fe02081d660cb67ec4326183acf60b7afa09cc1cbb269`.

Offline comparison of both platform bundles found identical notification coordinates and all 13 relevant literal tables: run status, faults, programs, wash phases, stains, default attributes/configurations, temperature, extra time, rinse count, water level, spin speed and dosing.

| Coordinates | Meaning from the exact washer plugin |
| --- | --- |
| `2.1`, `2.2`, `2.3`, `2.4` | Run status, fault code, selected program, wash phase |
| `2.8`, `2.14`, `2.15`, `2.16`, `2.18` | Temperature setting, extra-time setting, water-level setting, rinse count, spin-speed setting |
| `2.11`, `2.12`, `2.13` | Delay remaining time, program duration, remaining time; minutes are established by the actual rendering/date arithmetic |
| `2.24`, `2.25` | Detergent and softener dosing, with off/smart/low/medium/high codes |
| `3.4`, `3.6`, `3.7`, `3.8`, `3.9` | Child lock, fresh-air circulation, dynamic rinse, speed mode, night mode |
| `3.13`, `3.14`, `4.6`, `4.7`, `5.1` | Drum-clean recommendation, network authorization, low-detergent flag, low-softener flag, OTA status |
| `2.5`, `2.19`, `3.5` | Stain setting, delay setting in minutes, delay-enable setting; only writes are demonstrated in the plugin |

The catalogue preserves `notify`, `read` and `write` evidence independently. The plugin subscribes to the first 24 coordinates and uses cached message data; only `3.14` appears in a direct `get_properties` call. Source-derived polling candidates are therefore the 24 notification coordinates, with successful live RPC support determined separately. Three write-only definitions are excluded from normal read plans. All property reads include the **actual device ID** inside each `{did, siid, piid}` item. The app RPC methods are `get_properties`, `set_properties` and `action`.

Enum codes are meaningful device settings rather than measurements: spin speed `2` means `800` RPM, temperature `2` means `40℃`, and extra-time `2` means `+10` minutes. A Home Assistant sensor should decode these through the exact value lists. Units must not be attached directly to the raw enum codes. Boolean behavior is shown by `Boolean(value)` on received values and `Number(...)` on writes; read-only flag values have no formal type declaration. The catalogue marks inferred wire types and inferred binary value lists accordingly.

The washer's four action addresses are `2.1` power, `2.2` start/pause, `2.3` add clothes, and `2.4` request the current status report. The app starts subscriptions, then calls `action(2,4,1)` when opening an online device. Its wrapper sends `{did, siid:2, aiid:4, in:[{piid:4,value:1}]}`. This explains why an idle subscription can have no initial message. The extraction collector remains read-only and does not call that action automatically; the catalogue records action definitions separately.

Favorites, usage records, program memory and several notification/reminder settings are kept in the app's `AsyncStorage`; they are not evidence of a cloud history endpoint. The app does separately read/write the cloud data key `prop.s_auto_upgrade` for automatic firmware updates. Program defaults and option filters are extracted for all 22 programs: null means the app hides an unavailable setting; a `filter` removes listed enum codes for that program. These defaults must not be mistaken for live device values.

The first five-minute capture found both laundry appliances offline. A second read-only capture, after the user powered on the appliances, successfully read **all 24 washer polling candidates** through `get_properties`: every result code was `0`, using the actual device ID in each item. MQTT also reported **all 27 source-defined washer coordinates**, including `2.5`, `2.19` and `3.5`, whose notifications were not demonstrated by the static plugin subscription list. No device action was sent; the user opened the app to view status. Private evidence is in `private/device-api-online-validation-observations.json`. Source-only catalogues retain their source evidence and `live_verified=false`; live support is recorded independently so extraction remains reproducible.

## Exact dryer definitions and limits

The dryer catalogue contains 22 properties, including 13 writable coordinates, while its initial read plan contains only the 17 notification/direct-read candidates. The additional UI bindings are UV sterilization `3.3`, delay-start enable `3.5`, speed mode `3.10`, low-temperature drying `3.12` and night mode `3.13`. The subscription's night label instead points to `3.11`; these remain separate definitions. A hidden ModeSwitch path leaves its setter PIID at zero and is not treated as a valid property. Action inputs and explicit setting codes are retained for later control validation.

The plugin assigns `isExportSales=1` and its program-selection function therefore returns the 31-entry `ProgramMode_W` table. This is source evidence, not a country inference. Firmware selection alters a wool-program default duration, rather than the actual device's remaining time. Both domestic and selected program tables and option/default facts are retained. Device defaults are not substituted for observed values.

The final live capture returned 23 code-0 dryer RPC rows with 20 non-null values: `3.11`, `5.1` and unknown `4.7` were null. MQTT supplied values for `5.1` and `4.7`, yielding 22 combined observed coordinates. No exact source meaning for `4.7` was found. The dryer also uses cloud userdata key `prop.s_auto_upgrade`; reminder/history/favorite keys in its Constant module are local AsyncStorage. See [live coverage](live-coverage.md) and the source-hashed catalogue for the evidence boundary.

## Public official assets inspected

[`smarthome.dreame.tech`](https://smarthome.dreame.tech/) serves a login/account SPA. Its linked script `/static/js/main.012e52ca.chunk.js` was downloaded and searched for plugin, extension, key-definition and device-schema routes. It contains account/login routes, including `/dreame-smarthome/`, but no identified device plugin loader or exact L9 schema. This front end is therefore not sufficient to define the laundry properties.

[`smartlife.dreame.tech`](https://smartlife.dreame.tech/) serves the app download/deep-link front end. The inspected public source directs Android users to Google Play or regional stores; it does not reveal a direct APK URL or device plugin download route. The official [US download page](https://www.dreametech.com/pages/dreamehome-app-download/1000), [Canadian page](https://ca.dreametech.com/pages/app-download), [Danish page](https://dk.dreametech.com/pages/dreamehome-app-download) and [Irish page](https://ie.dreametech.com/pages/app-dreamehome) describe APK downloading but their visible Android download links currently lead to Google Play.

Downloaded public assets and adjacent `.meta.json` provenance records are under `references/l9-public`. Records include exact source URL, resolved URL, content type, length and SHA-256. The main SPA script has SHA-256 `164f1d1e603fdf88cdb9c5a52f6e25245012c864690214f05b5aa69094d59902`. Scripts were inspected as text, not executed; downloaded APKs were inspected offline without being installed or run by this investigation.

The official HTTPS [Android app-link declaration](https://app.dreame.tech/.well-known/assetlinks.json), also served by [smartlife](https://smartlife.dreame.tech/.well-known/assetlinks.json), identifies package `com.dreame.smartlife` and publishes these SHA-256 signing-certificate fingerprints:

- `6c37b0d6b0983a8e39955dfd85cbef4a50143728fa8215442e5e2a4325f2350c`
- `4a30175c6fddd90184bbb6c4f8aca8307da2af8fe4884bb25638f8cc8c20386c`
- `fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c`

These pins can authenticate an APK obtained from an app store or mirror after cryptographic APK signature verification. The saved declaration SHA-256 is `e901e96ec2ecebb66c10a9cbc2bbf7f0238178fc7af08cdd5fa5b31c5d3e4f61`. APKMirror reports the second certificate for Dreamehome `2.6.2.0`, but its package was not obtained: its download request returned HTTP 403. A reported certificate fingerprint alone does not verify a downloaded package. App signing pins are unrelated to the MQTT server certificate/CA.

The public APKPure alternate download host subsequently supplied Dreamehome `2.6.6.3` (`102060603`) as an XAPK archive. Its SHA-256 is `95c0dfaa27b25238ca799cfe0644fd2dc41635877eaab8a50743f5cd52addc82`, length `181781539` bytes. The locally installed Android SDK `apksigner` verified all three enclosed APKs using APK Signature Scheme v2 and v3. Every signer SHA-256 matches Dreame's official `4a30175c...` pin above. This authenticates the APK contents against the vendor-published app signing identity; the mirror itself is not the source of trust. Verification records are in `references/l9-public/dreamehome-apks/verification.json`; signed APKs are local research material and must not be distributed with the integration.

The verified base APK SHA-256 is `fbeeb15c93f3a12e52983a5ffdf9258556b82407a066203814d3a1db20269792`; ARM64 library split SHA-256 is `1e2b66e21623fa795261cad8e51f01e402faac2b633f654be19a002261c544f8`. The extracted app library SHA-256 is `a7364e7b1bcf27971b3e510115adf63d1a5a43892f6cbba3da571b1d175b4f6e`. Its strings reveal the H5 route and H5 response model names; the tested GET arguments returned empty H5 data, while the RN lookup returned the exact model bundles. The separately researched vendor MQTT certificate chain is described in [mqtt-trust-research.md](mqtt-trust-research.md).

The user's installed Android SDK has a running `Pixel_10a` AVD (`emulator-5554`), and read-only package inspection confirmed Dreamehome `2.6.6.3`/`102060603` already installed. This matched the signature-verified downloaded app version. No emulator launch, app navigation, local credentials inspection or appliance control was required for the static extraction.

`tools/l9_research_public.py` downloads official public HTTPS assets without authentication and retains certificate verification. `tools/l9_research_inspect.py` searches offline downloaded text or ZIP/APK contents without executing them. Some direct requests to official retail sites failed due to an expired certificate; certificate checks were not disabled. The Dreame `.tech` front ends above downloaded successfully.

`tools/l9_research_mirror.py` retains public APKMirror/APKPure/APKCombo responses for offline research and marks their authenticity as unresolved until signature verification against the official declaration. It sends no account credentials. `tools/l9_research_verify_apk.py` performs cryptographic APK signature checks and matches every signer against official pins. `tools/l9_research_apkstrings.py` inspects named ZIP entries with bounded output and restricts extracted libraries to the ignored private directory.

## Observed plugin platform evidence

The account's initial `os=2` lookup returned a vacuum bundle containing `dreame.vacuum.common/index.ohos.bundle.hbc`, while laundry responses were blank. This suggests OS 2 is HarmonyOS; its full enum mapping was not decompiled. Subsequent OS 0 and 1 responses directly establish iOS and Android from their exact-model `project.json` and bundle names. The successful OS 0/1 lookup resolved the laundry blocker without sending any device command.

The downloaded vacuum bundle is Hermes bytecode version `94`, containing `26162` functions and `160773` strings. Offline string-table and bytecode inspection identified `/dreame-product/plugin/config.json?` as a public resource configuration fetched by the vacuum plugin, not the base app's device-plugin download route. Its `getCommonPlugin` function calls the native `RNTFile` bridge; the cloud implementation resides in the base app. No exact L9 model strings or H5 lookup route were found in this vacuum bundle.

`tools/l9_research_hermes.py` uses the separately cloned P1sec parser (`references/hermes-dec`, commit `a0f18f97ab661eb8ed659c8c683a0d21ea619e69`) for offline string-table and targeted bytecode cross-reference inspection. Plugin bytecode is not executed, and the parser is not bundled into the API or integration.

## Other source findings

The [SF25 integration's pinned broker leaf fingerprint](https://github.com/maestrea76/HA-Dreame-SF25-WiFi-Integration/blob/main/custom_components/dreame_sf25/const.py) is `0a55ff4bbf5acbb52bfb1b7a941ea097c75f5ca58d0d5eb16464c1d255988200`. This is corroborating independent evidence about a broker certificate, not an official Dreame CA distribution or a laundry schema. Its transport approach must be evaluated separately before any credential-bearing MQTT connection.

Additional source clones used only for read-only research: `references/dreamehome-client` (commit `562a7cb7a8a38336ff1387d02e7e1b4adae7c582`), `references/dreame-hold` (commit `a75ec40628acdafc4b44493964421c4ad19cd27f`), `references/node-dreame` (commit `0345f0fb2c9ed89e36a08bd29a543b8d81de2ec4`), `references/dreame-mower`, and `references/dreame-sf25`. No code from these repositories was copied into the extracted API or integration by this investigation.

## Remaining evidence boundaries

The exact L9 lookup and both schemas are resolved; bounded property reads and authenticated MQTT have live evidence on both appliances. More captures during normal appliance use can show optional state values, phase-dependent settings and unknown enum codes. Additional fields reported over MQTT remain visible as raw state until labels and types are established. Controls and undocumented history endpoints are not inferred from these observations.

Reproduction is checked without network access or writes with `.\.venv\Scripts\python.exe tools\extract_l9_washer.py --check` and `.\.venv\Scripts\python.exe tools\extract_l9_dryer.py --check`. These require the locally retained pinned ZIPs; distribution contains factual JSON and extraction helpers, not signed APKs or vendor plugin code.
