# Home Assistant / HACS implementation handoff

The HACS integration in [Ampersandman/Dreame-Home](https://github.com/Ampersandman/Dreame-Home) includes its extracted API. Version `0.3.0b1` adds exact L9 setting/action controls and a native vacuum entity. The earlier telemetry beta has successful HACS installation, account authentication, discovery and updating values confirmed on HA OS 18.3 / Core 2026.9.4. Supplied diagnostics prove complete discovery and MQTT connectivity for all three; see the [HA diagnostics review](ha-diagnostics-review.md). Genuine HACS, hassfest and Python 3.12/3.14 offline CI passed for that earlier revision. New control execution, detailed lifecycle acceptance and maps remain pending. See [appliance controls](appliance-controls.md), [verification](verification.md) and [live coverage](live-coverage.md) for the separate evidence.

## Current validated API coverage

| Appliance | Exact model | Firmware | Initial addressed read plan | Combined non-null observations |
| --- | --- | --- | --- | --- |
| L9 washer | `dreame.washer.l9nacn` | `3017` | 24 source-backed candidates | 27 coordinates |
| L9 Twin Inverter dryer | `dreame.dryer.l9nacn` | `3029` | 17 source-backed candidates | 22 coordinates |
| L10s Ultra Gen 3 | `dreame.vacuum.r5023a` | `1304` | 15 bounded vacuum properties | 15 coordinates |

All three MQTT connections passed TLS verification during the standalone capture. Initial L9 read items use the actual device ID, matching their exact plugins. Source definitions and successful runtime observations remain separate evidence: an app subscription establishes a candidate address, while a successful returned value establishes observed device support. These counts cover the captured state; they do not establish every program, phase, event or internal appliance sensor.

The later HA diagnostic snapshot from Core 2026.9.4 / Python 3.14.6 confirms 27 usable washer roots sourced from MQTT, 22 usable dryer roots sourced from MQTT among 23 recorded coordinates, and 15 vacuum roots sourced from RPC. All three devices were present, reported online and MQTT connected; account discovery and the API update succeeded, without metadata/read/cloud-data errors or reported drops/truncation. Dryer `3.11` has no observed value and `4.7` remains unknown. These are property counts, not HA entity totals. No compound property values occur in this snapshot; compound projection and leaf metadata therefore lack live acceptance. See the [HA diagnostics review](ha-diagnostics-review.md).

The washer's initial plan excludes three source write-only fields: `2.5`, `2.19` and `3.5`. All three appeared in live MQTT, so the beta can expose their observed state. The dryer's final RPC pass returned 23 successful property codes with 20 non-null values; `3.11`, `5.1` and `4.7` were null. Earlier MQTT supplied non-null `5.1` and `4.7` values, giving 22 combined observed coordinates. Only `3.11` remains without a non-null observation. Null RPC replies preserve earlier successful state without advancing its freshness; `last_reply_null` identifies the latest null reply.

The dryer plugin's subscription at `3.11` conflicts with the control UI's night-mode binding at `3.13`. Keep those addresses distinct, and preserve unknown `4.7` without inventing a meaning. Exact catalogs supply friendly names, explicit enum mappings and confirmed units. The pinned dryer plugin selects `ProgramMode_W` through its literal export flag; firmware-dependent default durations do not change enum IDs or labels. The beta does not apply related-model schemas, infer units from names or convert inferred numeric Boolean flags into binary sensors. Unknown enum codes retain their raw scalar state, and translated enums retain `raw_code`.

## Implemented account and device lifecycle

One config entry represents a Dreame Home account and region. An account coordinator performs complete paginated discovery, metadata retrieval and bounded property reads; per-device state and errors remain separate. Device and entity identities retain region and stable device ID, including negative laundry IDs. Metadata provides the exact model, device name and firmware.

Config flow validates local username/password entry and region selection, saves a refresh token rather than the password or access token, persists rotated refresh tokens and handles reauthentication. Home Assistant's managed HTTP session supplies the async transport. MQTT connection work stays outside the HA event loop; subscriptions, tasks and listeners have unload/shutdown paths. Offline tests cover protocol and isolated lifecycle boundaries. Initial authentication, discovery and updating telemetry have user-reported HA confirmation; reauthentication, token rotation and unload/reload still need runtime checks.

Account API availability, cloud-reported appliance online state and MQTT connectivity remain distinct. A working account listing or broker connection does not prove fresh appliance state. Discovery refreshes every ten minutes, so a stale cloud online flag can delay visibility of a physical power change by up to ten minutes. Property reads run about once a minute for appliances that are not reported offline. Authentication, rate limits and per-device transport failures have separate handling.

## Implemented telemetry entities

The first refresh validates the exact initial read plan. Only successful non-null observations create entities; failed per-property codes remain diagnostic information. Later polling uses successfully observed coordinates, bounded to 240 addresses per refresh, and dynamic MQTT discovery adds previously unseen addresses.

Actual Boolean observations produce `binary_sensor` entities. Other scalar values produce `sensor` entities, with model-specific labels and explicit enum translations where available. The known vacuum battery property receives the battery device class and percentage unit. Laundry state does not acquire guessed energy, water, temperature or recorder statistics classes.

Both exact L9 plugins identify the additional cloud userdata setting `prop.s_auto_upgrade`. The beta reads only this extracted key through `get_device_data` at discovery cadence. A returned value creates an **Automatic firmware updates** sensor, retaining raw wire strings such as `'0'` and `'1'`. Missing values remain absent; no default or write is sent. A setting-specific failure does not affect appliance telemetry availability. Diagnostics report the configured cloud-data allowlist and two cached keys per device, without identifying returned cache values. Neither those counts nor the absence of a cloud-data error confirms a returned firmware-update setting; live acceptance of that value remains separate.

Compound values retain their complete original representation in the private property store. Their entity-facing root attributes are redacted. Dictionary leaves and uniquely keyed setting lists receive stable paths; ordinary arrays remain on the root. Leaf expansion is bounded to 256 fields per property and reports truncation. Structured roots are disabled by default to limit duplicated recorder data. Sensitive cached keys and semantic credential values are filtered or redacted before entity projection.

Unknown MQTT messages remain in a bounded private observation store and generate a redacted `dreame_home_message` bus event. This preserves evidence for later event adapters; it is not yet a typed Home Assistant event interface. Diagnostics omit arbitrary text, credentials and raw account envelopes while retaining useful coordinates, codes and coverage gaps.

## Remaining model work

Validate labels, values and timing against the app throughout normal washer and dryer operation: standby, running, pause, completion, faults, dosing warnings and changes of program. Distinguish transient nulls, stale values, missing replies and unsupported fields. Verify the semantics of numeric Boolean flags before changing their platform. Keep unpublished or physically present but cloud-unexposed sensors as explicit coverage gaps.

Source command definitions remain separate from state telemetry. Version `0.3.0b1` implements 16 washer and 12 dryer named control descriptors, with exact codes, program null/filter restrictions, status/child-lock/fault/authorization checks and fresh successful context no older than180 seconds. Controls do not predict state, apply local remembered defaults, silently pause/resume or replay uncertain failures. Capture/discovery still never writes settings or invokes `reportAll`. The new controls need deliberate hardware acceptance; see [appliance controls](appliance-controls.md).

| Verified future capability | Candidate Home Assistant representation |
| --- | --- |
| Boolean setting with validated writes | `switch` |
| Enumerated setting with validated writes | `select`, preserving raw codes |
| Numeric setting with validated limits and units | `number` |
| Meaningful writable string | `text` |
| Action with no inputs | `button` after checking prerequisites |
| Action with inputs | Validated service/action interface |
| Native device events | `event` entity or documented integration event |
| Schedule/time data | `time` or a validated schedule interface |
| Proprietary compound data | Exact model parser and derived entities |

The exact `r5023a` vacuum entity now implements source-backed start, pause, stop, return to base and fan speed with task-specific guards. Its initial plan has20 read candidates; the earlier capture and HA snapshot establish15 successful coordinates, not acceptance of the five added context reads. This does not reproduce Tasshack's complete vacuum integration. Maps, room cleaning, richer commands and hardware control acceptance remain pending.

## Runtime and release acceptance

The beta has a manifest, config flow, translations, coordinator, telemetry platforms, switch/select/button controls, a native vacuum entity, diagnostics, self-contained API and `hacs.json`. A number platform exposes no controls without proven bounds. `tools/build_component.py --archive` produces local `dist/dreame_home.zip`. The `dreame_home` domain allows coexistence with upstream `dreame_vacuum`.

Metadata selects Home Assistant Core 2026.9.4 as the baseline. That release requires Python 3.14; Windows Python 3.12 runs protocol and isolated component checks. Genuine GitHub offline checks passed on Python 3.12/3.14, together with official hassfest and HACS validation. The user reports that HACS installation, account authentication, all three devices' discovery and updating values succeeded on HA OS 18.3 / Core 2026.9.4. Supplied diagnostics confirm Python 3.14.6, the current observed property roots and all three MQTT connections. No agent-operated HA test or full per-property semantic acceptance was performed.

The repository is [Ampersandman/Dreame-Home](https://github.com/Ampersandman/Dreame-Home), with publishing metadata and local brand assets. The user installed the telemetry beta through HACS; a release is optional. Reauth, shared-device access, token rotation, rate-limit handling, cycle transitions, dynamic entities, stale/offline behavior, reconnect, unload/reload and recorder effects remain unconfirmed. Controls are implemented but have no hardware execution evidence; maps remain unimplemented. Complete cloud coverage requires continued observation, exact adapters and verification of the resulting HA behavior.
