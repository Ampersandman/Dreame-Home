# Confirmed device API coverage

Live validation on 2026-10-04 used the user's EU DreameHome account. The final 300-second capture began at `19:26:07Z` and completed at `19:31:09Z`. Discovery and metadata succeeded for all three owned devices. Exact DIDs, account identifiers and raw captures remain in ignored private files.

| Model | Firmware | Successful RPC property rows | Non-null RPC values | Combined non-null RPC/MQTT coordinates | Source initial read plan | MQTT messages | MQTT connected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dreame.washer.l9nacn` | `0.1.1_3017` | 27, all code 0 | 27 | 27 | 24 coordinates | 342 | Yes |
| `dreame.dryer.l9nacn` | `0.1.6_3029` | 23, all code 0 | 20 | 22 | 17 coordinates | 320 | Yes |
| `dreame.vacuum.r5023a` | `4.3.9_1304` | 15, all code 0 | 15 | 15 | 15 coordinates | 0 during this idle observation | Yes |

These counts describe the captured run and firmware, not every possible property, enum state or cycle phase. The user powered on the laundry appliances and viewed their status in the app. The collector made property reads and listened to notifications; it issued no cycles, actions or setting writes. No initial status-report action was sent by the collector.

The 24/17 laundry initial plans came from each exact model's official plugin. Subsequent MQTT observations established additional coordinates, which were then read individually. In particular, the washer's three source-write-only settings also reported values. The dryer's RPC results were null for `3.11`, `5.1` and `4.7`, leaving 20 non-null RPC values. Earlier MQTT values for `5.1` and `4.7` were retained in the observation store, yielding 22 combined usable coordinates; only `3.11` had no non-null observation. A code-0 null reply alone does not create a sensor or establish a usable value.

## Plugin and TLS blockers resolved

Subsequent Home Assistant diagnostics confirm all three appliances online and MQTT-connected, with the same 27/22/15 usable coordinate totals. Washer and dryer values originated from MQTT; vacuum values originated from RPC. No metadata/property-read/cloud-data errors, dropped observations or truncation are reported in that snapshot. See the [HA diagnostic review](ha-diagnostics-review.md) for the dryer null coordinate and coverage limits. These runtime findings are separate from the capture above.

`GET /dreame-product/upgrades/appplugin` with the actual account DID/model and `appVer=102060603` returned the exact model plugins: washer version `83`, dryer version `130`, vacuum version `31`. Their `project.json` and bundle names establish `os=0` as iOS and `os=1` as Android. The initial `os=2` request returned a vacuum HarmonyOS bundle and no laundry bundle; treating it as Android caused the first lookup failure. The tested H5 lookup returned empty data for these devices; the RN route supplied the definitions.

The factual catalogues contain 27 washer property definitions, 22 washer programs and 4 washer actions; the dryer catalogue contains 22 property definitions, 31 programs and 4 actions. Actions/writes were disabled in the validated telemetry revision. Version `0.3.0b1` adds named controls without changing this capture's evidence; none has hardware write acceptance. Signed APKs and vendor plugins remain excluded research material. See [appliance controls](appliance-controls.md), [exact L9 schema research](l9-schema-research.md) and [the dryer catalogue](../src/dreamehome/data/l9_dryer.json).

The EU MQTT trust path now uses a vendor CA recovered from an APK whose cryptographic signature matches Dreame's official HTTPS app-association declaration. Credential-bearing connections succeeded for all three devices with `CERT_REQUIRED` and hostname verification enabled. A narrowly scoped compatibility adjustment clears only strict X.509 extension conformance for the known EU endpoint; certificate-chain, signature, validity and hostname checks remain enabled. There is no network-derived trust enrollment or unverified-certificate fallback. See [MQTT trust research](mqtt-trust-research.md).

None of the devices supplied `keyDefine`, `liveKeyDefine` or `qaKeyDefine` links in the listing/metadata. The laundry cached `property` blobs contained MAC metadata rather than MIoT values; the vacuum also supplied `lwt`. Exact-model plugins plus RPC/MQTT established the telemetry instead. Credential-bearing cached fields and MACs are excluded from Home Assistant entity projection.

## Verified coordinates and unresolved semantics

The actual device ID inside each `{did, siid, piid}` read item was validated on the laundry appliances and matches their app wrappers. The coordinate-style item DID was accepted by the vacuum and remains its client contract.

Each of these vacuum addresses returned code 0 and a value:

```text
2.1  2.2  3.1  3.2
4.1  4.2  4.3  4.7  4.20  4.25  4.35  4.52  4.53
15.3  15.5
```

This verifies those vacuum reads on `4.3.9_1304`; it does not validate every upstream property, controls, writes or maps. Battery `3.1` supplied a numeric value. Zero MQTT messages during the idle capture does not imply MQTT failure: the vacuum's subscription connected successfully. The current20-candidate vacuum plan adds five control-context reads whose acceptance is not established by this15-coordinate evidence.

Laundry enum labels are applied only when an exact source mapping exists. Integer flags retain their wire values unless their Boolean meaning is independently established; unknown codes remain visible. Units are attached only to proven numeric quantities, not to setting codes such as temperature or spin-speed indices. The dryer reported an extra `4.7` coordinate over MQTT whose meaning is unresolved; it receives a neutral property name. Its night-mode UI references `3.13`, while the subscription table uses `3.11`; this contradiction is preserved rather than silently resolved. A null `3.11` value cannot establish its meaning.

The unrelated public debug candidates `dreame.washer.r1111` and `dreame.washer.r1112` are retained in [washer_candidates.json](../src/dreamehome/data/washer_candidates.json) for research. They are not used for either L9 appliance.

## Remaining validation and functionality

- The user confirmed installation and updating values; supplied HA diagnostics establish 27/22/15 valued property coordinates and MQTT connections for all three devices on Core 2026.9.4. Exact entity totals, additional operating states, reauthentication, reload/unload and stale behavior still need runtime checks.
- The repository is published with actual metadata, and official HACS/hassfest validation plus Python 3.12/3.14 offline checks passed. A tagged release is optional for custom-repository installation.
- Capture ordinary wash/dry cycles, door changes and completion to verify optional properties, phase-dependent values, stale behavior and unknown enums.
- Resolve dryer `4.7` and the night-mode coordinate contradiction from additional exact-model evidence.
- Validate the new named controls against actual acknowledgements and subsequent state. Vacuum maps, history, richer commands and further packed-setting decoders remain future work.

The extraction and live telemetry results cover the confirmed devices in the captured state. Version `0.3.0b1` extends that telemetry foundation with named controls, whose hardware execution remains untested. The broader goal of exposing everything supported by the cloud continues beyond these verified fields.
